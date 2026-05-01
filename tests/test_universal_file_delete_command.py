"""
Focused tests for universal_file_delete routing, explicit delete_mode, ordering.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_delete_command import (
    UniversalFileDeleteCommand,
)

_PID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.asyncio
class TestUniversalFileDeleteRouting:
    async def test_toml_unsupported_before_db(self) -> None:
        cmd = UniversalFileDeleteCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="cfg/app.toml",
                delete_mode="file",
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "UNSUPPORTED_FILE_EXTENSION"

    async def test_empty_delete_mode_before_db(self) -> None:
        cmd = UniversalFileDeleteCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="README.md",
                delete_mode=" ",
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_text_wrong_mode_yaml_path_before_db(self) -> None:
        cmd = UniversalFileDeleteCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="README.md",
                delete_mode="yaml_path",
                yaml_path="/a",
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_json_wrong_mode_range_before_db(self) -> None:
        cmd = UniversalFileDeleteCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="data/config.json",
                delete_mode="range",
                start_line=1,
                end_line=1,
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_yaml_wrong_mode_node_before_db(self) -> None:
        cmd = UniversalFileDeleteCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="cfg/x.yaml",
                delete_mode="node",
                operations=[{"action": "delete", "path": "/a"}],
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_python_wrong_mode_range_before_db(self) -> None:
        cmd = UniversalFileDeleteCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="src/m.py",
                delete_mode="range",
                start_line=1,
                end_line=2,
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_python_cst_selector_missing_ops_before_db(self) -> None:
        cmd = UniversalFileDeleteCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="src/m.py",
                delete_mode="cst_selector",
                ops=None,
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_python_node_id_missing_tree_before_db(self) -> None:
        cmd = UniversalFileDeleteCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="src/m.py",
                delete_mode="node_id",
                node_id="550e8400-e29b-41d4-a716-446655440099",
                tree_id=None,
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_json_missing_operations_before_db(self) -> None:
        cmd = UniversalFileDeleteCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="data/x.json",
                delete_mode="json_pointer",
                operations=None,
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_range_missing_lines_before_db(self) -> None:
        cmd = UniversalFileDeleteCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes/README.md",
                delete_mode="range",
                start_line=1,
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_file_not_found_after_resolve(self, tmp_path: Path) -> None:
        missing = tmp_path / "gone.md"
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)
        mock_db.get_project.return_value = mock_project
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=missing,
            ),
        ):
            cmd = UniversalFileDeleteCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="gone.md",
                delete_mode="file",
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "FILE_NOT_FOUND"
