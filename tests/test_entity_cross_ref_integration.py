"""
Integration tests for entity cross-ref via usages + build_entity_cross_ref_for_file.

Exercises legacy DB helpers wired through DatabaseClient over in-process RPC (see
:class:`tests.sqlite_in_process_legacy_facade.SqliteLegacyRpcFacade`).

Note: ``update_file_data_atomic`` with an active SQLite RPC transaction is not used
here: that combination can deadlock; the asserted behavior is usages → cross-ref
resolution and cleanup via ``clear_file_data``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import uuid
from typing import Any, cast

import pytest

from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

from code_analysis.core.entity_cross_ref_builder import build_entity_cross_ref_for_file


def _nid() -> str:
    """Return UUID4 strings for CST node placeholders (must pass UUID validation)."""
    return str(uuid.uuid4())


@pytest.fixture
def temp_db(tmp_path):
    """SQLite + in-process RPC + DatabaseClient."""
    facade, raw_client = make_sqlite_in_process_legacy_facade(tmp_path)
    try:
        yield facade
    finally:
        raw_client.disconnect()


@pytest.fixture
def test_project(temp_db, tmp_path):
    """Create test project in database."""
    project_id = str(uuid.uuid4())
    temp_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path), tmp_path.name),
    )
    temp_db._commit()
    return project_id


@pytest.fixture
def test_file_with_call(temp_db, tmp_path, test_project):
    """File row plus ``foo`` / ``bar`` functions and one usage ``bar`` → ``foo``."""
    file_path = tmp_path / "mod.py"
    source_code = "def foo():\n" "    pass\n\n\n" "def bar():\n" "    foo()\n"
    file_path.write_text(source_code, encoding="utf-8")
    file_mtime = os.path.getmtime(file_path)
    lines = len(source_code.splitlines())
    file_id = temp_db.add_file(
        path=str(file_path),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=False,
        project_id=test_project,
    )
    fid = str(file_id)
    foo_id = str(uuid.uuid4())
    bar_id = str(uuid.uuid4())
    temp_db._execute(
        "INSERT INTO functions (id, file_id, name, line, end_line, args, docstring, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (foo_id, fid, "foo", 1, 2, "[]", None, _nid()),
    )
    temp_db._execute(
        "INSERT INTO functions (id, file_id, name, line, end_line, args, docstring, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (bar_id, fid, "bar", 4, 5, "[]", None, _nid()),
    )
    temp_db._execute(
        """INSERT INTO usages (file_id, line, usage_type, target_type, target_name, target_class)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (fid, 5, "call", "function", "foo", None),
    )
    temp_db._commit()

    added = build_entity_cross_ref_for_file(
        temp_db, cast(Any, fid), test_project, source_code
    )
    assert added >= 1

    return fid, foo_id, bar_id, file_path, test_project


def test_cross_ref_roundtrip_from_usages_clear_file_removes_cross_ref(
    temp_db, test_file_with_call
):
    """Rows exist after build; ``get_dependencies_by_caller`` / ``clear_file_data`` behave."""
    file_id, foo_id, bar_id, _path, _ = test_file_with_call

    rows = temp_db._fetchall(
        "SELECT * FROM entity_cross_ref WHERE file_id = ?", (file_id,)
    )
    assert len(rows) >= 1

    deps = temp_db.get_dependencies_by_caller("function", bar_id)
    callee_ids = [
        d["callee_entity_id"] for d in deps if d["callee_entity_type"] == "function"
    ]
    assert foo_id in callee_ids

    dependents = temp_db.get_dependents_by_callee("function", foo_id)
    caller_ids = [
        d["caller_entity_id"]
        for d in dependents
        if d["caller_entity_type"] == "function"
    ]
    assert bar_id in caller_ids

    temp_db.clear_file_data(file_id)

    rows_after = temp_db._fetchall(
        "SELECT COUNT(*) as c FROM entity_cross_ref WHERE file_id = ?", (file_id,)
    )
    count_after = rows_after[0]["c"] if rows_after else 0
    assert count_after == 0
