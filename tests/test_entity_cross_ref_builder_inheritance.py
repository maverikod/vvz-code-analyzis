"""
Regression: build_entity_cross_ref_for_file writes inheritance edges from
classes.bases (card ac831d35, second half - the entity_cross_ref side).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid
from unittest.mock import MagicMock

import pytest

from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

from code_analysis.commands.ast.entity_dependencies_helpers import (
    get_entity_dependents_via_execute,
)
from code_analysis.core.entity_cross_ref_builder import build_entity_cross_ref_for_file


@pytest.fixture
def test_db(tmp_path):
    """SQLite-backed DatabaseClient facade (in-process RPC)."""
    facade, raw_client = make_sqlite_in_process_legacy_facade(tmp_path)
    try:
        yield facade
    finally:
        raw_client.disconnect()


@pytest.fixture
def project_id():
    """Project UUID."""
    return str(uuid.uuid4())


@pytest.fixture
def parent_child_fixture(test_db, tmp_path, project_id):
    """Parent class and Child(Parent) class, same file, both with cst_node_id."""
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path), tmp_path.name),
    )
    test_db._commit()

    file_id = str(uuid.uuid4())
    test_db._execute(
        """INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, has_docstring)
           VALUES (?, ?, ?, ?, 0, 0, 0)""",
        (file_id, project_id, str(tmp_path / "mod.py"), "mod.py"),
    )
    test_db._commit()

    parent_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (parent_id, file_id, "Parent", 1, 2, None, "[]", str(uuid.uuid4())),
    )
    child_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (child_id, file_id, "Child", 4, 5, None, '["Parent"]', str(uuid.uuid4())),
    )
    test_db._commit()

    return {"file_id": file_id, "parent_id": parent_id, "child_id": child_id}


def test_builder_writes_inheritance_row_for_child_to_parent(
    test_db, project_id, parent_child_fixture
):
    """build_entity_cross_ref_for_file adds a ref_type='inherit' row: Child -> Parent."""
    ids = parent_child_fixture

    added = build_entity_cross_ref_for_file(test_db, ids["file_id"], project_id, "")

    assert added >= 1
    rows = test_db._fetchall(
        "SELECT * FROM entity_cross_ref WHERE file_id = ? AND ref_type = 'inherit'",
        (ids["file_id"],),
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["caller_class_id"] == ids["child_id"]
    assert row["callee_class_id"] == ids["parent_id"]
    assert row["caller_method_id"] is None
    assert row["caller_function_id"] is None


def test_get_entity_dependents_returns_child_for_parent_after_builder(
    test_db, project_id, parent_child_fixture
):
    """get_entity_dependents(class, Parent) returns Child once the builder has run."""
    ids = parent_child_fixture
    test_db.disconnect = MagicMock()

    build_entity_cross_ref_for_file(test_db, ids["file_id"], project_id, "")

    dependents = get_entity_dependents_via_execute(test_db, "class", ids["parent_id"])

    assert len(dependents) == 1
    assert dependents[0]["caller_entity_type"] == "class"
    assert dependents[0]["caller_entity_id"] == ids["child_id"]
    assert dependents[0]["ref_type"] == "inherit"
