"""
Regression: find_dependencies / get_entity_dependents no longer drop rows that
lack a valid cst_node_id (cards 3540f30e / ac831d35).

``cst_node_id`` is NULL for many indexed entities (the indexer does not always
populate it -- see TZ-CA-INDEX-INTEGRITY-001). Dropping the row on a missing
cst_node_id silently hid real dependency/inheritance edges. The fix keeps the
row and includes ``cst_node_id`` only when it is present and a valid UUID4
(the ``hierarchy.py`` pattern), instead of ``continue``-ing past the row.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

from code_analysis.commands.ast.dependencies import FindDependenciesMCPCommand
from code_analysis.commands.ast.entity_dependencies_helpers import (
    get_entity_dependents_via_execute,
)
from code_analysis.commands.ast.hierarchy import GetClassHierarchyMCPCommand
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from mcp_proxy_adapter.commands.result import SuccessResult


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
def parent_child_no_cst_node_id(test_db, tmp_path, project_id):
    """Parent/Child(Parent) classes; neither row has a cst_node_id (NULL)."""
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
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        (parent_id, file_id, "Parent", 1, 2, None, "[]"),
    )
    child_id = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        (child_id, file_id, "Child", 4, 5, None, '["Parent"]'),
    )
    test_db._commit()

    test_db.add_entity_cross_ref(
        caller_class_id=child_id,
        caller_method_id=None,
        caller_function_id=None,
        callee_class_id=parent_id,
        callee_method_id=None,
        callee_function_id=None,
        ref_type="inherit",
        file_id=file_id,
        line=4,
    )
    test_db._commit()

    return {"parent_id": parent_id, "child_id": child_id}


@pytest.mark.asyncio
async def test_find_dependencies_inheritance_row_kept_without_cst_node_id(
    test_db, tmp_path, project_id, parent_child_no_cst_node_id
):
    """find_dependencies(entity_type=class) still returns the inheritance row.

    cst_node_id is absent from the row (not present -> not a required key),
    but the row itself is not dropped, and the count matches
    get_class_hierarchy's "Parent" -> children count.
    """
    # Both commands call db.disconnect() on success; keep the shared facade
    # (and its in-process RPC client) alive across the two calls in this test.
    test_db.disconnect = MagicMock()
    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=test_db
        ),
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=tmp_path),
    ):
        dep_cmd = FindDependenciesMCPCommand()
        dep_result = await dep_cmd.execute(
            project_id=project_id, entity_name="Parent", entity_type="class"
        )

        hierarchy_cmd = GetClassHierarchyMCPCommand()
        hierarchy_result = await hierarchy_cmd.execute(
            project_id=project_id, class_name="Parent"
        )

    assert isinstance(dep_result, SuccessResult), getattr(
        dep_result, "message", dep_result
    )
    deps = dep_result.data["dependencies"]
    inheritance_rows = [d for d in deps if d["type"] == "inheritance"]
    assert len(inheritance_rows) == 1, (
        "expected the Child(Parent) inheritance row to survive despite a "
        f"NULL cst_node_id; got {deps!r}"
    )
    assert "cst_node_id" not in inheritance_rows[0]
    assert inheritance_rows[0]["class_name"] == "Child"

    hierarchy_children = hierarchy_result.data["hierarchy"]["Parent"]["children"]
    assert len(inheritance_rows) == len(hierarchy_children) == 1
    assert hierarchy_children == ["Child"]


def test_get_entity_dependents_row_kept_without_cst_node_id(
    test_db, project_id, parent_child_no_cst_node_id
):
    """get_entity_dependents_via_execute keeps the cross_ref row when the
    callee's cst_node_id is NULL; cst_node_id key is simply absent."""
    test_db.disconnect = MagicMock()

    dependents = get_entity_dependents_via_execute(
        test_db, "class", parent_child_no_cst_node_id["parent_id"]
    )

    assert len(dependents) == 1
    assert "cst_node_id" not in dependents[0]
    assert dependents[0]["caller_entity_type"] == "class"
    assert dependents[0]["caller_entity_id"] == parent_child_no_cst_node_id["child_id"]
