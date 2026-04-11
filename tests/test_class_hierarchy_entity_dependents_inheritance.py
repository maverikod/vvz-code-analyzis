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

from code_analysis.commands.ast.entity_dependencies_helpers import (
    get_entity_dependents_via_execute,
)
from code_analysis.commands.ast.hierarchy import GetClassHierarchyMCPCommand
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker


def _uuid4() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_id():
    return str(uuid.uuid4())


@pytest.fixture
def test_db(temp_dir):
    db_path = temp_dir / "test.db"
    driver_config = create_driver_config_for_worker(
        db_path, driver_type="sqlite", backup_dir=temp_dir / "backups"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    yield db
    db.close()


@pytest.fixture
def test_project(test_db, temp_dir, project_id):
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

    test_db._execute(
        """INSERT INTO files (project_id, path, lines, last_modified, has_docstring)
           VALUES (?, ?, 0, 0, 0)""",
        (test_project, "base.py"),
    )
    test_db._commit()
    file1_id = test_db._lastrowid()

    test_db._execute(
        """INSERT INTO files (project_id, path, lines, last_modified, has_docstring)
           VALUES (?, ?, 0, 0, 0)""",
        (test_project, "other.py"),
    )
    test_db._commit()
    file2_id = test_db._lastrowid()

    p_cst = _uuid4()
    test_db._execute(
        "INSERT INTO classes (file_id, name, line, end_line, docstring, bases, cst_node_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (file1_id, "Parent", 1, 10, None, "[]", p_cst),
    )
    test_db._commit()
    parent_id = test_db._lastrowid()

    c_cst = _uuid4()
    bases_json = '["some_pkg.module.Parent"]'
    test_db._execute(
        "INSERT INTO classes (file_id, name, line, end_line, docstring, bases, cst_node_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (file2_id, "Child", 1, 20, None, bases_json, c_cst),
    )
    test_db._commit()
    child_id = test_db._lastrowid()

    return {
        "parent_id": parent_id,
        "child_id": child_id,
        "file1_id": file1_id,
        "file2_id": file2_id,
    }


def test_dependents_include_subclasses_from_bases_without_cross_ref(
    test_db, test_project, inheritance_fixture
):
    """When entity_cross_ref has no rows, subclasses still appear as dependents."""
    ids = inheritance_fixture
    deps = get_entity_dependents_via_execute(
        test_db, "class", ids["parent_id"], project_id=test_project
    )
    assert len(deps) == 1
    assert deps[0]["caller_entity_type"] == "class"
    assert deps[0]["caller_entity_id"] == ids["child_id"]
    assert deps[0]["ref_type"] == "inherit"


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
    deps = get_entity_dependents_via_execute(
        test_db, "class", ids["parent_id"], project_id=test_project
    )
    assert len(deps) == 1


@pytest.mark.asyncio
async def test_class_hierarchy_single_class_name_includes_cross_file_children(
    test_db, test_project, inheritance_fixture, temp_dir
):
    """class_name filter must still load subclasses defined in other files."""
    test_db.disconnect = MagicMock()

    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=test_db,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_project_root",
        return_value=temp_dir,
    ):
        cmd = GetClassHierarchyMCPCommand()
        result = await cmd.execute(
            project_id=test_project,
            class_name="Parent",
        )

    assert result.data["success"] is True
    h = result.data["hierarchy"]
    assert h.get("name") == "Parent"
    assert "Child" in h.get("children", [])
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
        test_db._execute(
            """INSERT INTO files (project_id, path, lines, last_modified, has_docstring)
               VALUES (?, ?, 0, 0, 0)""",
            (test_project, p),
        )
        test_db._commit()
        file_ids.append(test_db._lastrowid())

    name = "AIAdminBaseException"
    for fid in file_ids:
        cid = _uuid4()
        test_db._execute(
            "INSERT INTO classes (file_id, name, line, end_line, docstring, bases, cst_node_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fid, name, 1, 5, None, "[]", cid),
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

    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=test_db,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_project_root",
        return_value=temp_dir,
    ):
        cmd = GetClassHierarchyMCPCommand()
        for p in fx["paths"]:
            result = await cmd.execute(
                project_id=test_project,
                class_name=fx["name"],
                file_path=p,
            )
            assert result.data["success"] is True
            h = result.data["hierarchy"]
            assert h.get("name") == fx["name"]
            assert h.get("file_path") == p
            assert result.data["count"] == 1


@pytest.mark.asyncio
async def test_class_hierarchy_duplicate_name_without_file_path_is_deterministic(
    test_db, test_project, duplicate_class_name_fixture, temp_dir
):
    """If several classes share a name, class_name-only query picks a stable row."""
    fx = duplicate_class_name_fixture
    test_db.disconnect = MagicMock()

    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=test_db,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_project_root",
        return_value=temp_dir,
    ):
        cmd = GetClassHierarchyMCPCommand()
        result = await cmd.execute(project_id=test_project, class_name=fx["name"])

    assert result.data["success"] is True
    h = result.data["hierarchy"]
    assert h.get("name") == fx["name"]
    # Lexicographically smallest file_path among duplicates
    assert h.get("file_path") == min(fx["paths"])


def test_base_string_references_class():
    from code_analysis.commands.ast import entity_dependencies_helpers as h

    assert h._base_string_references_class(
        "pkg.AIAdminBaseException", "AIAdminBaseException"
    )
    assert h._base_string_references_class(
        "AIAdminBaseException", "AIAdminBaseException"
    )
    assert not h._base_string_references_class("Other", "AIAdminBaseException")
