"""
Regression: inheritance edges from classes.bases for dependents and class hierarchy.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

from code_analysis.commands.ast.entity_dependencies_helpers import (
    get_entity_dependents_via_execute,
)
from code_analysis.commands.ast.hierarchy import GetClassHierarchyMCPCommand
from code_analysis.commands.base_mcp_command import BaseMCPCommand


def _uuid4() -> str:
    """Return uuid4."""
    return str(uuid.uuid4())


@pytest.fixture
def temp_dir():
    """Return temp dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_id():
    """Return project id."""
    return str(uuid.uuid4())


@pytest.fixture
def test_db(temp_dir):
    """Verify test db."""
    facade, raw_client = make_sqlite_in_process_legacy_facade(temp_dir)
    try:
        yield facade
    finally:
        raw_client.disconnect()


@pytest.fixture
def test_project(test_db, temp_dir, project_id):
    """Verify test project."""
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(temp_dir), temp_dir.name),
    )
    test_db._commit()
    return project_id


@pytest.fixture
def inheritance_fixture(test_db, temp_dir, test_project):
    """Parent in base.py, Child in other.py inheriting from qualified base name."""
    root = temp_dir
    (root / "base.py").write_text("", encoding="utf-8")
    (root / "other.py").write_text("", encoding="utf-8")

    f1_id = str(uuid.uuid4())
    test_db._execute(
        """INSERT INTO files (id, project_id, path, lines, last_modified, has_docstring)
           VALUES (?, ?, ?, 0, 0, 0)""",
        (f1_id, test_project, "base.py"),
    )
    test_db._commit()
    file1_id = f1_id

    f2_id = str(uuid.uuid4())
    test_db._execute(
        """INSERT INTO files (id, project_id, path, lines, last_modified, has_docstring)
           VALUES (?, ?, ?, 0, 0, 0)""",
        (f2_id, test_project, "other.py"),
    )
    test_db._commit()
    file2_id = f2_id

    p_cst = _uuid4()
    parent_uuid = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (parent_uuid, file1_id, "Parent", 1, 10, None, "[]", p_cst),
    )
    test_db._commit()
    parent_id = parent_uuid

    c_cst = _uuid4()
    bases_json = '["some_pkg.module.Parent"]'
    child_uuid = str(uuid.uuid4())
    test_db._execute(
        "INSERT INTO classes (id, file_id, name, line, end_line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (child_uuid, file2_id, "Child", 1, 20, None, bases_json, c_cst),
    )
    test_db._commit()
    child_id = child_uuid

    return {
        "parent_id": parent_id,
        "child_id": child_id,
        "file1_id": file1_id,
        "file2_id": file2_id,
    }


def test_dependents_include_subclasses_from_bases_without_cross_ref(
    test_db, test_project, inheritance_fixture
):
    """``get_entity_dependents_via_execute`` reads entity_cross_ref only; subclasses from ``bases``
    JSON are discovered by find_dependencies-like SQL (same pattern as MCP dependencies path).
    """
    import json

    ids = inheritance_fixture
    deps = get_entity_dependents_via_execute(test_db, "class", ids["parent_id"])
    assert deps == []

    rows = (
        test_db.execute(
            "SELECT c.bases FROM classes c WHERE c.id = ?", (ids["child_id"],)
        ).get("data")
        or []
    )
    assert len(rows) == 1
    bases = json.loads(rows[0]["bases"])
    assert bases == ["some_pkg.module.Parent"]


def test_dependents_dedupe_cross_ref_and_bases(
    test_db, test_project, inheritance_fixture
):
    """Same subclass from cross-ref and bases yields one row."""
    ids = inheritance_fixture
    test_db.add_entity_cross_ref(
        caller_class_id=ids["child_id"],
        caller_method_id=None,
        caller_function_id=None,
        callee_class_id=ids["parent_id"],
        callee_method_id=None,
        callee_function_id=None,
        ref_type="inherit",
        file_id=ids["file2_id"],
        line=1,
    )
    deps = get_entity_dependents_via_execute(test_db, "class", ids["parent_id"])
    assert len(deps) == 1


@pytest.mark.asyncio
async def test_class_hierarchy_single_class_name_includes_cross_file_children(
    test_db, test_project, inheritance_fixture, temp_dir
):
    """class_name filter must still load subclasses defined in other files."""
    test_db.disconnect = MagicMock()

    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=test_db,
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=temp_dir,
        ),
    ):
        cmd = GetClassHierarchyMCPCommand()
        result = await cmd.execute(
            project_id=test_project,
            class_name="Parent",
        )

    assert result.data["success"] is True
    outer = result.data["hierarchy"]
    assert "Parent" in outer
    node = outer["Parent"]
    assert node.get("name") == "Parent"
    assert "Child" in node.get("children", [])
    assert result.data["count"] == 1


@pytest.fixture
def duplicate_class_name_fixture(test_db, temp_dir, test_project):
    """Same simple class name in two files (vast_srv-style duplicate)."""
    root = temp_dir
    (root / "pkg" / "core").mkdir(parents=True)
    (root / "pkg/core/custom_exceptions.py").write_text("", encoding="utf-8")
    (root / "pkg/core/custom_exceptions").mkdir(parents=True, exist_ok=True)
    (root / "pkg/core/custom_exceptions/base.py").write_text("", encoding="utf-8")

    paths = [
        "pkg/core/custom_exceptions.py",
        "pkg/core/custom_exceptions/base.py",
    ]
    file_ids = []
    for p in paths:
        fid = str(uuid.uuid4())
        test_db._execute(
            """INSERT INTO files (id, project_id, path, lines, last_modified, has_docstring)
               VALUES (?, ?, ?, 0, 0, 0)""",
            (fid, test_project, p),
        )
        test_db._commit()
        file_ids.append(fid)

    name = "AIAdminBaseException"
    for fid in file_ids:
        cid = _uuid4()
        class_id = str(uuid.uuid4())
        test_db._execute(
            "INSERT INTO classes (id, file_id, name, line, end_line, docstring, bases, cst_node_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (class_id, fid, name, 1, 5, None, "[]", cid),
        )
        test_db._commit()

    return {"file_ids": file_ids, "paths": paths, "name": name}


@pytest.mark.asyncio
async def test_class_hierarchy_duplicate_name_resolves_with_file_path(
    test_db, test_project, duplicate_class_name_fixture, temp_dir
):
    """class_name + file_path must return the class in that file, not another homonym."""
    fx = duplicate_class_name_fixture
    test_db.disconnect = MagicMock()

    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=test_db,
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=temp_dir,
        ),
    ):
        cmd = GetClassHierarchyMCPCommand()
        for p in fx["paths"]:
            result = await cmd.execute(
                project_id=test_project,
                class_name=fx["name"],
                file_path=p,
            )
            assert result.data["success"] is True
            outer = result.data["hierarchy"]
            assert fx["name"] in outer
            hn = outer[fx["name"]]
            assert hn.get("name") == fx["name"]
            assert hn.get("file_path") == p
            assert result.data["count"] == 1


@pytest.mark.asyncio
async def test_class_hierarchy_duplicate_name_without_file_path_is_deterministic(
    test_db, test_project, duplicate_class_name_fixture, temp_dir
):
    """If several classes share a name, class_name-only query returns one surviving row."""
    fx = duplicate_class_name_fixture
    test_db.disconnect = MagicMock()

    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=test_db,
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=temp_dir,
        ),
    ):
        cmd = GetClassHierarchyMCPCommand()
        result = await cmd.execute(project_id=test_project, class_name=fx["name"])

    assert result.data["success"] is True
    outer = result.data["hierarchy"]
    assert fx["name"] in outer
    hn = outer[fx["name"]]
    assert hn.get("name") == fx["name"]
    assert hn.get("file_path") in fx["paths"]


def test_base_string_references_class():
    """Regression strings for matching a base reference to a simple class name."""

    def _same_base_name(base_str: str, class_name: str) -> bool:
        """Return same base name."""
        if base_str == class_name:
            return True
        if "." in base_str and base_str.rsplit(".", 1)[-1] == class_name:
            return True
        return False

    assert _same_base_name("pkg.AIAdminBaseException", "AIAdminBaseException")
    assert _same_base_name("AIAdminBaseException", "AIAdminBaseException")
    assert not _same_base_name("Other", "AIAdminBaseException")
