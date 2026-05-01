"""
Tests for create_text_file MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.create_text_file_command import CreateTextFileMCPCommand
from code_analysis.hooks_register_part2 import register_commands_part2

_PID = "550e8400-e29b-41d4-a716-446655440000"


def _persist_ok(**_: object) -> dict:
    """Patch target for persist_plain_text_file_metadata."""
    return {"success": True, "file_id": "stub-id", "metadata_only": True}


@pytest.mark.asyncio
class TestCreateTextFileCommand:
    async def test_create_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
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
                return_value=f,
            ),
            patch(
                "code_analysis.commands.create_text_file_command.persist_plain_text_file_metadata",
                side_effect=_persist_ok,
            ),
        ):
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(project_id=_PID, file_path="notes.txt")

        assert isinstance(result, SuccessResult)
        assert f.exists()
        assert f.read_text(encoding="utf-8") == ""
        assert result.data["created"] is True
        assert result.data["overwritten"] is False
        assert result.data["bytes_written"] == 0
        assert result.data["metadata_update"].get("success") is True

    async def test_create_file_with_content(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
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
                return_value=f,
            ),
            patch(
                "code_analysis.commands.create_text_file_command.persist_plain_text_file_metadata",
                side_effect=_persist_ok,
            ),
        ):
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes.txt",
                content="alpha\nbeta\n",
            )

        assert isinstance(result, SuccessResult)
        assert f.read_text(encoding="utf-8") == "alpha\nbeta\n"
        assert result.data["bytes_written"] == len("alpha\nbeta\n".encode("utf-8"))

    async def test_create_md_file(self, tmp_path: Path) -> None:
        f = tmp_path / "README.md"
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
                return_value=f,
            ),
            patch(
                "code_analysis.commands.create_text_file_command.persist_plain_text_file_metadata",
                side_effect=_persist_ok,
            ),
        ):
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(project_id=_PID, file_path="README.md")

        assert isinstance(result, SuccessResult)
        assert f.read_text(encoding="utf-8") == ""

    async def test_create_nested_parent_dirs(self, tmp_path: Path) -> None:
        f = tmp_path / "notes" / "a" / "b" / "sample.txt"
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
                return_value=f,
            ),
            patch(
                "code_analysis.commands.create_text_file_command.persist_plain_text_file_metadata",
                side_effect=_persist_ok,
            ),
        ):
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes/a/b/sample.txt",
                create_dirs=True,
            )

        assert isinstance(result, SuccessResult)
        assert f.exists()
        assert result.data["parent_created"] is True

    async def test_parent_missing_and_create_dirs_false(self, tmp_path: Path) -> None:
        f = tmp_path / "notes" / "a" / "b" / "sample.txt"
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
                return_value=f,
            ),
        ):
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes/a/b/sample.txt",
                create_dirs=False,
            )

        assert isinstance(result, ErrorResult)
        assert result.code == "DIRECTORY_NOT_FOUND"

    async def test_existing_file_overwrite_false(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("old", encoding="utf-8")
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
                return_value=target,
            ),
            patch(
                "code_analysis.commands.create_text_file_command.persist_plain_text_file_metadata",
                side_effect=_persist_ok,
            ),
        ):
            cmd = CreateTextFileMCPCommand()
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
                return_value=target,
            ),
            patch(
                "code_analysis.commands.create_text_file_command.persist_plain_text_file_metadata",
                side_effect=_persist_ok,
            ),
            patch(
                "code_analysis.commands.create_text_file_command.BackupManager"
            ) as bm_cls,
        ):
            bm = MagicMock()
            bm.create_backup.return_value = "bak-uuid"
            bm_cls.return_value = bm
            cmd = CreateTextFileMCPCommand()
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
        assert result.data.get("backup_uuid") == "bak-uuid"
        bm_cls.assert_called()
        bm.create_backup.assert_called_once()

    async def test_absolute_file_path_rejected(self, tmp_path: Path) -> None:
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(project_id=_PID, file_path="/tmp/outside.txt")

        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_FILE_PATH"

    async def test_traversal_path_rejected(self, tmp_path: Path) -> None:
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(project_id=_PID, file_path="../outside.txt")

        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_FILE_PATH"

    async def test_json_rejected_before_database(self, tmp_path: Path) -> None:
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(
                project_id=_PID, file_path="data.json", content="{}"
            )

        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "JSON_CREATE_USE_UNIVERSAL_FILE_SAVE"

    async def test_yaml_rejected_before_database(self, tmp_path: Path) -> None:
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(
                project_id=_PID, file_path="cfg.yaml", content="x: 1"
            )

        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "YAML_CREATE_USE_UNIVERSAL_FILE_SAVE"

    async def test_py_forbidden_before_database(self, tmp_path: Path) -> None:
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="module.py",
                content="print(1)",
            )

        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "PYTHON_FILE_FORBIDDEN"

    async def test_go_code_forbidden_before_database(self, tmp_path: Path) -> None:
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(project_id=_PID, file_path="main.go")

        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "CODE_FILE_FORBIDDEN"

    async def test_unsupported_suffix_before_database(self, tmp_path: Path) -> None:
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(project_id=_PID, file_path="x.toml")

        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "UNSUPPORTED_FILE_EXTENSION"

    async def test_directory_target_with_text_suffix(self, tmp_path: Path) -> None:
        d = tmp_path / "readme.md"
        d.mkdir(parents=False)
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)
        mock_db.get_project.return_value = mock_project
        assert d.is_dir()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=d,
            ),
            patch(
                "code_analysis.commands.create_text_file_command.persist_plain_text_file_metadata",
                side_effect=_persist_ok,
            ),
        ):
            cmd = CreateTextFileMCPCommand()
            result = await cmd.execute(project_id=_PID, file_path="readme.md")

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
