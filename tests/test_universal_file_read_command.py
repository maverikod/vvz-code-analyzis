"""
Focused tests for universal_file_read routing and response shape.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_read_command import UniversalFileReadCommand

_PID = "550e8400-e29b-41d4-a716-446655440000"


def _assert_universal_ok_fields(d: dict) -> None:
    assert d.get("success") is True
    assert d.get("handler_id")
    assert d.get("operation") == "read"
    assert d.get("file_path")
    assert d.get("project_id") == _PID


@pytest.mark.asyncio
class TestUniversalFileReadRouting:
    async def test_toml_unsupported_before_file_access(self) -> None:
        cmd = UniversalFileReadCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="cfg/app.toml",
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "UNSUPPORTED_FILE_EXTENSION"

    async def test_unknown_suffix_unsupported(self) -> None:
        cmd = UniversalFileReadCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="dir/blob.unknownext",
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "UNSUPPORTED_FILE_EXTENSION"

    async def test_md_text_handler(self, tmp_path: Path) -> None:
        f = tmp_path / "README.md"
        f.write_text("# Hi\n\nbody\n", encoding="utf-8")
        mock_db = MagicMock()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
        ):
            cmd = UniversalFileReadCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="README.md",
                start_line=1,
                end_line=1,
            )
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_ok_fields(d)
        assert d["handler_id"] == "text"
        assert d["lines"] == ["# Hi"]

    async def test_txt_text_handler(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("a\nb\n", encoding="utf-8")
        mock_db = MagicMock()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
        ):
            cmd = UniversalFileReadCommand()
            result = await cmd.execute(project_id=_PID, file_path="notes.txt")
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_ok_fields(d)
        assert d["handler_id"] == "text"
        assert d["lines"] == ["a", "b"]
        assert d["total_lines"] == 2

    async def test_json_handler_tree_shape(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text('{"hello": "world"}\n', encoding="utf-8")
        mock_db = MagicMock()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
        ):
            cmd = UniversalFileReadCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="data.json",
                start_line=99,
                end_line=1,
            )
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_ok_fields(d)
        assert d["handler_id"] == "json"
        assert "tree_id" in d
        assert "nodes" in d
        assert "lines" not in d

    async def test_yaml_handler(self, tmp_path: Path) -> None:
        f = tmp_path / "conf.yaml"
        f.write_text("a: 1\n", encoding="utf-8")
        mock_db = MagicMock()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
        ):
            cmd = UniversalFileReadCommand()
            result = await cmd.execute(project_id=_PID, file_path="conf.yaml")
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_ok_fields(d)
        assert d["handler_id"] == "yaml"
        assert d.get("document") == {"a": 1}

    async def test_python_delegates_get_file_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("def x():\n    return 1\n", encoding="utf-8")
        mock_db = MagicMock()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
        ):
            cmd = UniversalFileReadCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="mod.py",
                start_line=1,
                end_line=2,
            )
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_ok_fields(d)
        assert d["handler_id"] == "python"
        assert d["lines"] == ["def x():", "    return 1"]

    async def test_partial_line_range_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "n.txt"
        f.write_text("a\n", encoding="utf-8")
        mock_db = MagicMock()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
        ):
            cmd = UniversalFileReadCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="n.txt",
                start_line=1,
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"
