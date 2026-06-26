"""
Regression tests for AST/entity lookup consistency in MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.commands.ast.entity_info import GetCodeEntityInfoMCPCommand
from code_analysis.commands.ast.get_ast import GetASTMCPCommand
from code_analysis.commands.ast.hierarchy import GetClassHierarchyMCPCommand
from code_analysis.commands.ast.imports import GetImportsMCPCommand
from code_analysis.commands.ast.list_entities import ListCodeEntitiesMCPCommand
from code_analysis.commands.ast.statistics import ASTStatisticsMCPCommand
from code_analysis.commands.base_mcp_command import BaseMCPCommand


@pytest.mark.asyncio
async def test_ast_statistics_file_path_uses_project_relative_resolution(
    tmp_path: Path,
) -> None:
    """Verify test ast statistics file path uses project relative resolution."""
    project_root = tmp_path / "proj"
    target = project_root / "ai_admin" / "commands" / "base.py"
    target.parent.mkdir(parents=True)
    target.write_text("class AIAdminCommand:\n    pass\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        {
            "data": [
                {
                    "id": 14,
                    "path": str(target),
                    "relative_path": "ai_admin/commands/base.py",
                }
            ]
        },
        {"data": [{"count": 1}]},
    ]
    mock_db.disconnect.return_value = None

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
    ):
        cmd = ASTStatisticsMCPCommand()
        result = await cmd.execute(
            project_id="p1", file_path="ai_admin/commands/base.py"
        )

    assert result.data["success"] is True
    assert result.data["ast_trees_count"] == 1


@pytest.mark.asyncio
async def test_list_code_entities_file_path_filter() -> None:
    """Verify test list code entities file path filter."""
    node_id_class = str(uuid.uuid4())
    node_id_method = str(uuid.uuid4())
    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        {
            "data": [
                {
                    "id": 14,
                    "path": "/tmp/proj/ai_admin/commands/base.py",
                    "relative_path": "ai_admin/commands/base.py",
                }
            ]
        },
        {"data": [{"cnt": 2}]},
        {
            "data": [
                {
                    "type": "class",
                    "name": "AIAdminCommand",
                    "line": 9,
                    "file_path": "ai_admin/commands/base.py",
                    "cst_node_id": node_id_class,
                },
                {
                    "type": "method",
                    "name": "execute",
                    "line": 11,
                    "class_name": "AIAdminCommand",
                    "file_path": "ai_admin/commands/base.py",
                    "cst_node_id": node_id_method,
                },
            ]
        },
    ]
    mock_db.disconnect.return_value = None

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=Path("/tmp/proj")
        ),
    ):
        cmd = ListCodeEntitiesMCPCommand()
        result = await cmd.execute(
            project_id="p1", file_path="ai_admin/commands/base.py", limit=20
        )

    names = {(e["type"], e["name"]) for e in result.data["entities"]}
    assert ("class", "AIAdminCommand") in names
    assert ("method", "execute") in names


@pytest.mark.asyncio
async def test_get_code_entity_info_method_target_class() -> None:
    """Verify test get code entity info method target class."""
    node_id = str(uuid.uuid4())
    mock_db = MagicMock()
    mock_db.execute.return_value = {
        "data": [
            {
                "name": "execute",
                "class_name": "AIAdminCommand",
                "line": 11,
                "file_path": "ai_admin/commands/base.py",
                "cst_node_id": node_id,
            }
        ]
    }
    mock_db.disconnect.return_value = None

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=Path("/tmp/proj")
        ),
    ):
        cmd = GetCodeEntityInfoMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            entity_type="method",
            entity_name="execute",
            target_class="AIAdminCommand",
        )

    sql = mock_db.execute.call_args[0][0]
    params = mock_db.execute.call_args[0][1]
    assert "c.name = ?" in sql
    assert "AIAdminCommand" in params
    assert result.data["count"] == 1
    assert result.data["entities"][0]["class_name"] == "AIAdminCommand"


@pytest.mark.asyncio
async def test_get_imports_import_from_filter_maps_to_stored_from() -> None:
    """Verify test get imports import from filter maps to stored from."""
    mock_db = MagicMock()
    mock_db.execute.return_value = {
        "data": [
            {"name": "ABC", "module": "abc", "import_type": "from", "line": 1},
            {
                "name": "abstractmethod",
                "module": "abc",
                "import_type": "from",
                "line": 1,
            },
        ]
    }
    mock_db.disconnect.return_value = None

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=Path("/tmp/proj")
        ),
    ):
        cmd = GetImportsMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            file_path=None,
            import_type="import_from",
            module_name="abc",
        )

    sql = mock_db.execute.call_args[0][0]
    params = mock_db.execute.call_args[0][1]
    assert "import_type IN (?, ?)" in sql
    assert "from" in params and "import_from" in params
    assert result.data["count"] == 2


@pytest.mark.asyncio
async def test_get_class_hierarchy_includes_leaf_class() -> None:
    """Verify test get class hierarchy includes leaf class."""
    mock_db = MagicMock()
    mock_db.execute.return_value = {
        "data": [
            {
                "name": "AIAdminCommand",
                "line": 9,
                "bases": '["Command"]',
                "file_path": "ai_admin/commands/base.py",
                "cst_node_id": None,
            }
        ]
    }
    mock_db.disconnect.return_value = None

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=Path("/tmp/proj")
        ),
    ):
        cmd = GetClassHierarchyMCPCommand()
        result = await cmd.execute(project_id="p1", class_name="AIAdminCommand")

    assert "AIAdminCommand" in result.data["hierarchy"]
    assert result.data["hierarchy"]["AIAdminCommand"]["bases"] == ["Command"]


@pytest.mark.asyncio
async def test_get_class_hierarchy_project_level_includes_all_classes() -> None:
    """Verify test get class hierarchy project level includes all classes."""
    mock_db = MagicMock()
    mock_db.execute.return_value = {
        "data": [
            {
                "name": "Command",
                "line": 1,
                "bases": "[]",
                "file_path": "a.py",
                "cst_node_id": None,
            },
            {
                "name": "AIAdminCommand",
                "line": 9,
                "bases": '["Command"]',
                "file_path": "ai_admin/commands/base.py",
                "cst_node_id": None,
            },
        ]
    }
    mock_db.disconnect.return_value = None

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=Path("/tmp/proj")
        ),
    ):
        cmd = GetClassHierarchyMCPCommand()
        result = await cmd.execute(project_id="p1")

    assert "AIAdminCommand" in result.data["hierarchy"]
    assert "Command" in result.data["hierarchy"]
    assert "AIAdminCommand" in result.data["hierarchy"]["Command"]["children"]


@pytest.mark.asyncio
async def test_get_ast_existing_file_without_ast_returns_ast_not_indexed(
    tmp_path: Path,
) -> None:
    """Verify test get ast existing file without ast returns ast not indexed."""
    project_root = tmp_path / "proj"
    target = project_root / "code_analysis" / "commands" / "json_save_tree_command.py"
    target.parent.mkdir(parents=True)
    target.write_text("def f():\n    return 1\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.execute.return_value = {"data": []}
    mock_db.disconnect.return_value = None

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
    ):
        cmd = GetASTMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            file_path="code_analysis/commands/json_save_tree_command.py",
            include_json=False,
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "AST_NOT_INDEXED"
