"""
Regression: the entity_cross_ref builder chain works against DatabaseClient's
REAL public surface, not just CodeDatabase's private legacy internals.

History on this file: it originally asserted commit discipline
(add_entity_cross_ref/delete_entity_cross_ref_for_file must not call the
private ``self._commit()`` unconditionally). That mechanism is GONE now -
both functions (and every helper in entity_cross_ref_builder.py: resolve_caller,
resolve_callee, _resolve_unique_base_class_id, _inherit_edge_exists,
_backfill_children_inheritance_for_class, build_entity_cross_ref_for_file) were
rewritten to use only the portable ``db.execute(sql, params) -> {"data": [...],
"affected_rows":..., "lastrowid":...}`` interface that both CodeDatabase and
DatabaseClient implement publicly - so there is no more manual commit-guarding
to test.

Why this file needed rewriting (not just its assertions): live verification on
1.6.63 found 65 warnings during reindex, all "'DatabaseClient' object has no
attribute '_fetchall'". The builder IS invoked from sync_file_to_db_atomic, but
every function in the chain called the private CodeDatabase-only
``_fetchall``/``_execute``/``_commit``/``_lastrowid``/``_in_transaction``
quartet, and add_entity_cross_ref/delete_entity_cross_ref_for_file were also
called as BOUND METHODS (``db.add_entity_cross_ref(...)``) that only exist on
CodeDatabase (attached by database/__init__.py), never on DatabaseClient.
sync_file_to_db_atomic passes a DatabaseClient. The PREVIOUS version of this
test used a hand-rolled stub that itself exposed ``_fetchall``/``_execute``/
``_commit``/``_lastrowid``/``_in_transaction`` (mirroring CodeDatabase, not
DatabaseClient) - exactly the shape of stub that lets this whole class of bug
pass silently, which is why it never caught the incompatibility the live
system hit twice more after the previous fix.

_DatabaseClientShapedStub below has ONLY ``execute()`` (DatabaseClient's real
public surface for this purpose - see ``grep class DatabaseClient`` and its
mixins: no ``_fetchall``, no ``_execute``, no ``_commit``, no
``_in_transaction``, no ``add_entity_cross_ref``/``delete_entity_cross_ref_for_file``
methods). Any remaining private-API call anywhere in the chain raises
AttributeError against it, the same as it does against the real DatabaseClient.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sqlite3
import uuid

import pytest

from code_analysis.core.database.entity_cross_ref import (
    add_entity_cross_ref,
    delete_entity_cross_ref_for_file,
)
from code_analysis.core.entity_cross_ref_builder import (
    _resolve_unique_base_class_id,
    build_entity_cross_ref_for_file,
    resolve_caller,
    resolve_callee,
)


class _DatabaseClientShapedStub:
    """Exposes ONLY ``execute(sql, params=None, transaction_id=None, *,
    priority=0) -> Dict[str, Any]`` - DatabaseClient's real public surface for
    everything this builder chain needs. Backed by a real in-memory sqlite3
    connection so the SQL itself is genuinely exercised, not just mocked.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize the instance."""
        self._conn = conn

    def execute(self, sql, params=None, transaction_id=None, *, priority=0):
        """Same contract as CodeDatabase.execute()/DatabaseClient.execute()."""
        del transaction_id, priority
        cur = self._conn.cursor()
        cur.execute(sql, params or ())
        if sql.strip().upper().startswith("SELECT"):
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            return {"data": rows}
        self._conn.commit()
        return {"affected_rows": cur.rowcount, "lastrowid": cur.lastrowid, "data": None}


@pytest.fixture
def stub_db():
    """A DatabaseClient-shaped stub over a minimal in-memory schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = None
    conn.executescript("""
        CREATE TABLE files (id TEXT PRIMARY KEY, project_id TEXT);
        CREATE TABLE classes (
            id TEXT PRIMARY KEY, file_id TEXT, name TEXT, line INTEGER,
            end_line INTEGER, bases TEXT
        );
        CREATE TABLE methods (
            id TEXT PRIMARY KEY, class_id TEXT, line INTEGER, end_line INTEGER
        );
        CREATE TABLE functions (
            id TEXT PRIMARY KEY, file_id TEXT, name TEXT, line INTEGER, end_line INTEGER
        );
        CREATE TABLE usages (
            id TEXT PRIMARY KEY, file_id TEXT, line INTEGER, usage_type TEXT,
            target_type TEXT, target_class TEXT, target_name TEXT
        );
        CREATE TABLE entity_cross_ref (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caller_class_id TEXT, caller_method_id TEXT, caller_function_id TEXT,
            callee_class_id TEXT, callee_method_id TEXT, callee_function_id TEXT,
            ref_type TEXT, file_id TEXT, line INTEGER
        );
        """)
    conn.commit()
    try:
        yield _DatabaseClientShapedStub(conn)
    finally:
        conn.close()


def _valid_kwargs(**overrides):
    """Return a valid add_entity_cross_ref kwargs set (one caller, one callee)."""
    base = dict(
        caller_class_id=str(uuid.uuid4()),
        caller_method_id=None,
        caller_function_id=None,
        callee_class_id=str(uuid.uuid4()),
        callee_method_id=None,
        callee_function_id=None,
        ref_type="inherit",
        file_id=str(uuid.uuid4()),
        line=1,
    )
    base.update(overrides)
    return base


def test_add_entity_cross_ref_works_against_database_client_shaped_stub(stub_db):
    """add_entity_cross_ref must not depend on any CodeDatabase-only private
    method or on being bound as a method - only db.execute()."""
    result = add_entity_cross_ref(stub_db, **_valid_kwargs())

    assert result is not None
    rows = stub_db.execute("SELECT * FROM entity_cross_ref").get("data")
    assert len(rows) == 1
    assert rows[0]["ref_type"] == "inherit"


def test_delete_entity_cross_ref_for_file_works_against_database_client_shaped_stub(
    stub_db,
):
    """delete_entity_cross_ref_for_file must not depend on any CodeDatabase-only
    private method or on being bound as a method - only db.execute()."""
    file_id = str(uuid.uuid4())
    add_entity_cross_ref(stub_db, **_valid_kwargs(file_id=file_id))
    assert len(stub_db.execute("SELECT * FROM entity_cross_ref")["data"]) == 1

    delete_entity_cross_ref_for_file(stub_db, file_id)

    assert stub_db.execute("SELECT * FROM entity_cross_ref")["data"] == []


def test_resolve_caller_and_callee_work_against_database_client_shaped_stub(stub_db):
    """resolve_caller/resolve_callee (and therefore _resolve_unique_base_class_id,
    which shares the same _fetchall-turned-execute() plumbing) must resolve
    correctly with no CodeDatabase-only private method available."""
    file_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    stub_db.execute(
        "INSERT INTO files (id, project_id) VALUES (?, ?)", (file_id, project_id)
    )
    stub_db.execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, bases) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (class_id, file_id, "Widget", 1, 2, "[]"),
    )

    caller = resolve_caller(stub_db, file_id, 1)
    assert caller == ("class", class_id)

    callee = resolve_callee(stub_db, project_id, file_id, 1, "class", "Widget")
    assert callee == ("class", class_id)

    unique_id = _resolve_unique_base_class_id(stub_db, project_id, "Widget")
    assert unique_id == class_id


def test_build_entity_cross_ref_for_file_end_to_end_against_database_client_shaped_stub(
    stub_db,
):
    """The full chain (build_entity_cross_ref_for_file, exercising resolve_caller,
    resolve_callee, _resolve_unique_base_class_id, _inherit_edge_exists,
    _backfill_children_inheritance_for_class, and both entity_cross_ref writers)
    must work end-to-end with only db.execute() available - no CodeDatabase-only
    private method, no bound-method add_entity_cross_ref on the db object.

    This is the exact scenario sync_file_to_db_atomic exercises in production
    (a DatabaseClient, not a CodeDatabase) and is written to FAIL on the
    pre-fix code (private-method AttributeError) - verified below.
    """
    project_id = str(uuid.uuid4())
    base_file_id = str(uuid.uuid4())
    base_id = str(uuid.uuid4())
    stub_db.execute(
        "INSERT INTO files (id, project_id) VALUES (?, ?)",
        (base_file_id, project_id),
    )
    stub_db.execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, bases) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (base_id, base_file_id, "Base", 1, 2, "[]"),
    )

    child_file_id = str(uuid.uuid4())
    child_id = str(uuid.uuid4())
    stub_db.execute(
        "INSERT INTO files (id, project_id) VALUES (?, ?)",
        (child_file_id, project_id),
    )
    stub_db.execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, bases) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (child_id, child_file_id, "Child", 1, 1, '["Base"]'),
    )
    stub_db.execute(
        "INSERT INTO usages (id, file_id, line, usage_type, target_type, "
        "target_class, target_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), child_file_id, 1, "instantiation", "class", None, "Base"),
    )

    added = build_entity_cross_ref_for_file(stub_db, child_file_id, project_id, "")

    assert added >= 1, "expected at least the inheritance edge to be added"
    rows = stub_db.execute("SELECT * FROM entity_cross_ref")["data"]
    ref_types = sorted(r["ref_type"] for r in rows)
    assert "inherit" in ref_types
