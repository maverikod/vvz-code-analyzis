"""
Tests: project-relative file_path for list_code_entities and get_code_entity_info.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.commands.ast.entity_info import GetCodeEntityInfoMCPCommand
from code_analysis.commands.ast.list_entities import ListCodeEntitiesMCPCommand
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.path_normalization import file_lookup_paths_for_project


def test_file_lookup_paths_relative_uses_project_root_not_cwd(tmp_path: Path) -> None:
    """Relative segments are resolved against project_root only."""
    root = tmp_path / "proj"
    root.mkdir()
    abs_keys, rel_keys = file_lookup_paths_for_project("pkg/mod.py", root)
    assert abs_keys == [str((root / "pkg" / "mod.py").resolve())]
    assert "pkg/mod.py" in rel_keys


def test_file_lookup_paths_absolute_under_root_includes_relative_variants(
    tmp_path: Path,
) -> None:
    """Absolute path under project yields keys for both path and relative_path columns."""
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "a" / "b.py"
    target.parent.mkdir(parents=True)
    target.touch()
    abs_keys, rel_keys = file_lookup_paths_for_project(str(target), root)
    assert str(target.resolve()) in abs_keys
    assert "a/b.py" in rel_keys or str(Path("a") / "b.py") in rel_keys


@pytest.mark.asyncio
async def test_list_code_entities_empty_when_file_not_in_project(
    tmp_path: Path,
) -> None:
    """Unresolvable file_path returns empty entities, not project-wide rows."""
    mock_db = MagicMock()
    mock_db.get_file_by_path.return_value = None
    mock_db.disconnect.return_value = None

    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_project_root",
        return_value=tmp_path,
    ):
        cmd = ListCodeEntitiesMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            file_path="_fix_ssl_type.py",
        )

    assert result.data["entities"] == []
    assert result.data["count"] == 0
    mock_db.get_file_by_path.assert_called_once_with("_fix_ssl_type.py", "p1")


@pytest.mark.asyncio
async def test_list_code_entities_filters_by_resolved_file_id(tmp_path: Path) -> None:
    """When file resolves, query is constrained to that file_id."""
    mock_db = MagicMock()
    mock_db.get_file_by_path.return_value = {"id": 42}
    mock_db.execute.return_value = {"data": []}
    mock_db.disconnect.return_value = None

    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_project_root",
        return_value=tmp_path,
    ):
        cmd = ListCodeEntitiesMCPCommand()
        await cmd.execute(
            project_id="p1",
            file_path="src/foo.py",
        )

    calls = [c.args[0] for c in mock_db.execute.call_args_list]
    for sql in calls:
        assert (
            "file_id = ?" in sql or "func.file_id = ?" in sql or "c.file_id = ?" in sql
        )


@pytest.mark.asyncio
async def test_get_code_entity_info_file_not_found_when_path_unresolved(
    tmp_path: Path,
) -> None:
    """Explicit file_path with no DB row returns FILE_NOT_FOUND, not broad match."""
    mock_db = MagicMock()
    mock_db.get_file_by_path.return_value = None
    mock_db.disconnect.return_value = None

    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_project_root",
        return_value=tmp_path,
    ):
        cmd = GetCodeEntityInfoMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            entity_type="function",
            entity_name="foo",
            file_path="_fix_ssl_type.py",
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "FILE_NOT_FOUND"
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_code_entity_info_queries_with_file_id_when_resolved(
    tmp_path: Path,
) -> None:
    mock_db = MagicMock()
    mock_db.get_file_by_path.return_value = {"id": 99}
    mock_db.execute.return_value = {"data": []}
    mock_db.disconnect.return_value = None

    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_project_root",
        return_value=tmp_path,
    ):
        cmd = GetCodeEntityInfoMCPCommand()
        await cmd.execute(
            project_id="p1",
            entity_type="class",
            entity_name="Bar",
            file_path="pkg/m.py",
        )

    mock_db.execute.assert_called_once()
    sql = mock_db.execute.call_args[0][0]
    assert "file_id = ?" in sql
