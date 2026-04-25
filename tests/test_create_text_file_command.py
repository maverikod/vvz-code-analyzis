"""
Tests for create_text_file MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.file_management_mcp_commands import CreateTextFileMCPCommand
from code_analysis.hooks_register_part2 import register_commands_part2

_PID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.asyncio
class TestCreateTextFileCommand:
    async def test_create_empty_file(self, tmp_path: Path) -> None:
        cmd = CreateTextFileMCPCommand()
        cmd._resolve_project_root = MagicMock(return_value=tmp_path)

        result = await cmd.execute(project_id=_PID, file_path="notes.txt")

        assert isinstance(result, SuccessResult)
        assert (tmp_path / "notes.txt").exists()
        assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == ""
        assert result.data["created"] is True
        assert result.data["overwritten"] is False
        assert result.data["bytes_written"] == 0

    async def test_create_file_with_content(self, tmp_path: Path) -> None:
        cmd = CreateTextFileMCPCommand()
        cmd._resolve_project_root = MagicMock(return_value=tmp_path)

        result = await cmd.execute(
            project_id=_PID,
            file_path="notes.txt",
            content="alpha\nbeta\n",
        )

        assert isinstance(result, SuccessResult)
        assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "alpha\nbeta\n"
        assert result.data["bytes_written"] == len("alpha\nbeta\n".encode("utf-8"))

    async def test_create_nested_parent_dirs(self, tmp_path: Path) -> None:
        cmd = CreateTextFileMCPCommand()
        cmd._resolve_project_root = MagicMock(return_value=tmp_path)

        result = await cmd.execute(
            project_id=_PID,
            file_path="notes/a/b/sample.txt",
            create_dirs=True,
        )

        assert isinstance(result, SuccessResult)
        assert (tmp_path / "notes" / "a" / "b" / "sample.txt").exists()
        assert result.data["parent_created"] is True

    async def test_parent_missing_and_create_dirs_false(self, tmp_path: Path) -> None:
        cmd = CreateTextFileMCPCommand()
        cmd._resolve_project_root = MagicMock(return_value=tmp_path)

        result = await cmd.execute(
            project_id=_PID,
            file_path="notes/a/b/sample.txt",
            create_dirs=False,
        )

        assert isinstance(result, ErrorResult)
        assert result.code == "DIRECTORY_NOT_FOUND"

    async def test_existing_file_overwrite_false(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.txt"
        target.write_text("old", encoding="utf-8")
        cmd = CreateTextFileMCPCommand()
        cmd._resolve_project_root = MagicMock(return_value=tmp_path)

        result = await cmd.execute(
            project_id=_PID,
            file_path="notes.txt",
            content="new",
            overwrite=False,
        )

        assert isinstance(result, ErrorResult)
        assert result.code == "FILE_ALREADY_EXISTS"
        assert target.read_text(encoding="utf-8") == "old"

    async def test_existing_file_overwrite_true(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.txt"
        target.write_text("old", encoding="utf-8")
        cmd = CreateTextFileMCPCommand()
        cmd._resolve_project_root = MagicMock(return_value=tmp_path)

        result = await cmd.execute(
            project_id=_PID,
            file_path="notes.txt",
            content="new",
            overwrite=True,
        )

        assert isinstance(result, SuccessResult)
        assert result.data["created"] is False
        assert result.data["overwritten"] is True
        assert target.read_text(encoding="utf-8") == "new"

    async def test_absolute_file_path_rejected(self, tmp_path: Path) -> None:
        cmd = CreateTextFileMCPCommand()
        cmd._resolve_project_root = MagicMock(return_value=tmp_path)

        result = await cmd.execute(project_id=_PID, file_path="/tmp/outside.txt")

        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_FILE_PATH"

    async def test_traversal_path_rejected(self, tmp_path: Path) -> None:
        cmd = CreateTextFileMCPCommand()
        cmd._resolve_project_root = MagicMock(return_value=tmp_path)

        result = await cmd.execute(project_id=_PID, file_path="../outside.txt")

        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_FILE_PATH"

    async def test_path_points_to_directory(self, tmp_path: Path) -> None:
        (tmp_path / "notes").mkdir()
        cmd = CreateTextFileMCPCommand()
        cmd._resolve_project_root = MagicMock(return_value=tmp_path)

        result = await cmd.execute(project_id=_PID, file_path="notes")

        assert isinstance(result, ErrorResult)
        assert result.code == "PATH_IS_DIRECTORY"


def test_command_registration() -> None:
    class _DummyRegistry:
        def __init__(self) -> None:
            self.names: list[str] = []

        def register(self, command_cls: type, source: str) -> None:
            self.names.append(getattr(command_cls, "name", ""))

    reg = _DummyRegistry()
    register_commands_part2(reg)

    assert "create_text_file" in reg.names
