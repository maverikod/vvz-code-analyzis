"""
Regression: sync_file_to_db_atomic (the ONLY write pipeline the update_indexes
command actually uses) builds entity_cross_ref rows for the file it just wrote.

Fourth root-layer finding in the entity_cross_ref saga: build_entity_cross_ref_for_file
was correctly wired into update_file_data_atomic (core/database/files/atomic.py) and
correctly transaction-guarded (commit c1abc8ae) - but update_file_data_atomic has NO
live caller anywhere in the codebase. update_indexes routes through
sync_file_to_db_atomic (core/database/file_tree_sync.py), which never referenced
entity_cross_ref at all: the entity_cross_ref writer was never invoked by any live
indexing path, consistent with every prior live-verification round
(1.6.60/1.6.61/1.6.62) and the 2026-07-18 card.

This test indexes a small project through sync_file_to_db_atomic exactly the way
update_indexes_analyzer.py does (classes/functions written by the sync call, a usage
row present the way a real second indexing pass would have it - sync_file_to_db_atomic
itself never writes to `usages`, that happens in a separate UsageTracker step in the
real update_indexes_analyzer.py caller) and asserts entity_cross_ref carries both the
inheritance edge and the usage edge afterward. It also re-runs the sync for the same
file and asserts entity_cross_ref does not accumulate duplicates (the clear-before-
rebuild idempotency step).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import time
import uuid

import pytest

from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

from code_analysis.commands.ast.entity_dependencies_helpers import (
    get_entity_dependents_via_execute,
)
from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic


@pytest.fixture
def test_db(tmp_path):
    """SQLite-backed DatabaseClient facade (in-process RPC), real schema.

    ``test_db._client`` is the plain ``DatabaseClient`` the facade wraps
    (same underlying connection/schema) - what ``sync_file_to_db_atomic``
    actually gets from its one real production caller
    (``update_indexes_analyzer.py`` passes a ``DatabaseClient``, never the
    facade). Passing ``test_db._client`` (not the facade, which happens to
    expose both the legacy private methods AND ``execute()``) to
    ``sync_file_to_db_atomic`` in these tests is what makes them faithfully
    reproduce the "'DatabaseClient' object has no attribute '_fetchall'" live
    bug pre-fix, instead of silently passing regardless (the facade's dual
    surface is exactly why earlier tests in this saga kept passing despite
    the incompatibility).
    """
    facade, raw_client = make_sqlite_in_process_legacy_facade(tmp_path)
    try:
        yield facade
    finally:
        raw_client.disconnect()


@pytest.fixture
def project_id():
    """Project UUID."""
    return str(uuid.uuid4())


def _insert_project(test_db, tmp_path, project_id):
    """Insert a project row."""
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path), tmp_path.name),
    )
    test_db._commit()


def _insert_file(test_db, project_id, tmp_path, name):
    """Insert a files row and return its id (does not require add_file's
    project-root resolution chain, which needs more setup than this test cares
    about; sync_file_to_db_atomic is given file_id directly so
    get_file_by_path is never consulted)."""
    file_id = str(uuid.uuid4())
    test_db._execute(
        """INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, has_docstring)
           VALUES (?, ?, ?, ?, 0, 0, 0)""",
        (file_id, project_id, str(tmp_path / name), name),
    )
    test_db._commit()
    return file_id


def _classes_by_name(test_db, file_id):
    """Return {name: id} for classes defined in file_id."""
    rows = test_db._fetchall(
        "SELECT id, name FROM classes WHERE file_id = ?", (file_id,)
    )
    return {r["name"]: r["id"] for r in rows}


def test_sync_file_to_db_atomic_builds_inheritance_and_usage_cross_ref(
    test_db, tmp_path, project_id
):
    """Index base.py (class Base) then child.py (class Child(Base) + a usage of
    Base) through sync_file_to_db_atomic and assert entity_cross_ref carries
    BOTH edges afterward - this is the wiring gap: pre-fix, entity_cross_ref
    stays completely empty no matter what gets indexed."""
    _insert_project(test_db, tmp_path, project_id)

    base_file_id = _insert_file(test_db, project_id, tmp_path, "base.py")
    base_source = "class Base:\n    pass\n"
    base_result = sync_file_to_db_atomic(
        database=test_db._client,
        project_id=project_id,
        absolute_path=str(tmp_path / "base.py"),
        source_code=base_source,
        file_mtime=time.time(),
        file_id=base_file_id,
        skip_file_edit_lock=True,
    )
    assert base_result["success"], base_result.get("error")
    base_id = _classes_by_name(test_db, base_file_id)["Base"]

    child_file_id = _insert_file(test_db, project_id, tmp_path, "child.py")
    # call_base is a one-liner: build_file_data_atomic_batches (this pipeline's
    # entity writer, unlike entities.py's add_function/add_class) never
    # populates end_line, so resolve_caller's span check collapses every
    # function/class to a single line (its own declaration line). A usage on
    # any other line inside a real multi-line body would not resolve to a
    # caller here - a separate, deeper gap in this pipeline, out of scope for
    # this wiring fix, but it means the usage in this test must sit on
    # call_base's own line to be resolvable at all.
    child_source = "class Child(Base):\n    pass\n\n\ndef call_base(): Base()\n"
    # Models a usage row already present for this file - real update_indexes_analyzer.py
    # writes usages via a separate UsageTracker step (sync_file_to_db_atomic itself never
    # touches the usages table); a usage from an earlier pass (or pre-seeded here) must
    # still surface as an entity_cross_ref edge once the wiring runs.
    test_db._execute(
        "INSERT INTO usages (id, file_id, line, usage_type, target_type, "
        "target_class, target_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), child_file_id, 5, "instantiation", "class", None, "Base"),
    )
    test_db._commit()

    child_result = sync_file_to_db_atomic(
        database=test_db._client,
        project_id=project_id,
        absolute_path=str(tmp_path / "child.py"),
        source_code=child_source,
        file_mtime=time.time(),
        file_id=child_file_id,
        skip_file_edit_lock=True,
    )
    assert child_result["success"], child_result.get("error")

    dependents = get_entity_dependents_via_execute(test_db, "class", base_id)
    ref_types = sorted(d["ref_type"] for d in dependents)
    assert ref_types == ["inherit", "instantiation"], (
        "expected both the Child(Base) inheritance edge and the Base() usage "
        f"edge as dependents of Base; got {dependents!r}"
    )

    child_classes = _classes_by_name(test_db, child_file_id)
    child_id = child_classes["Child"]
    inherit_rows = [d for d in dependents if d["ref_type"] == "inherit"]
    assert inherit_rows[0]["caller_entity_type"] == "class"
    assert inherit_rows[0]["caller_entity_id"] == child_id

    usage_rows = [d for d in dependents if d["ref_type"] == "instantiation"]
    assert usage_rows[0]["caller_entity_type"] == "function"


def test_sync_file_to_db_atomic_does_not_duplicate_cross_ref_on_reindex(
    test_db, tmp_path, project_id
):
    """Re-syncing the same file must not accumulate duplicate entity_cross_ref
    rows - the delete-before-rebuild idempotency step."""
    _insert_project(test_db, tmp_path, project_id)

    base_file_id = _insert_file(test_db, project_id, tmp_path, "base.py")
    sync_file_to_db_atomic(
        database=test_db._client,
        project_id=project_id,
        absolute_path=str(tmp_path / "base.py"),
        source_code="class Base:\n    pass\n",
        file_mtime=time.time(),
        file_id=base_file_id,
        skip_file_edit_lock=True,
    )
    base_id = _classes_by_name(test_db, base_file_id)["Base"]

    child_file_id = _insert_file(test_db, project_id, tmp_path, "child.py")
    child_source = "class Child(Base):\n    pass\n"

    for _ in range(2):
        result = sync_file_to_db_atomic(
            database=test_db._client,
            project_id=project_id,
            absolute_path=str(tmp_path / "child.py"),
            source_code=child_source,
            file_mtime=time.time(),
            file_id=child_file_id,
            skip_file_edit_lock=True,
        )
        assert result["success"], result.get("error")

    dependents = get_entity_dependents_via_execute(test_db, "class", base_id)
    assert (
        len(dependents) == 1
    ), f"expected exactly one inheritance edge after re-indexing twice; got {dependents!r}"
