"""
Tests for legacy delete_file: registry-first ordering and path guards.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.delete_file_command import DeleteFileMCPCommand

_PID = "550e8400-e29b-41d4-a716-446655440001"


@pytest.mark.asyncio
class TestDeleteFileRouting:
    async def test_unsupported_extension_before_db(self) -> None:
        cmd = DeleteFileMCPCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(project_id=_PID, file_path="cfg/app.toml")
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "UNSUPPORTED_FILE_EXTENSION"

    async def test_blocks_project_venv_path_before_trash(self, tmp_path: Path) -> None:
        proj_root = tmp_path / "proj"
        proj_root.mkdir()
        under = proj_root / ".venv" / "notes.txt"
        under.parent.mkdir(parents=True)
        under.write_text("x", encoding="utf-8")

        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        mock_db.get_project.return_value = MagicMock(root_path=str(proj_root.resolve()))

        cmd = DeleteFileMCPCommand()
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ):
            result = await cmd.execute(
                project_id=_PID,
                file_path=".venv/notes.txt",
            )

        mock_db.disconnect.assert_called_once()
        assert isinstance(result, ErrorResult)
        assert result.code == "PROJECT_VENV_WRITE_FORBIDDEN"

    async def test_blocks_site_packages_segment_before_trash(
        self, tmp_path: Path
    ) -> None:
        proj_root = tmp_path / "proj"
        sp = proj_root / "vendor" / "site-packages" / "pkg.txt"
        sp.parent.mkdir(parents=True)
        sp.write_text("x", encoding="utf-8")

        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        mock_db.get_project.return_value = MagicMock(root_path=str(proj_root.resolve()))

        cmd = DeleteFileMCPCommand()
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ):
            result = await cmd.execute(
                project_id=_PID,
                file_path="vendor/site-packages/pkg.txt",
            )

        assert isinstance(result, ErrorResult)
        assert result.code == "SITE_PACKAGES_DELETE_FORBIDDEN"


@pytest.mark.asyncio
class TestDeleteFileRegistryDiagnostics:
    async def test_python_path_success_includes_handler_and_note(
        self, tmp_path: Path
    ) -> None:
        proj_root = tmp_path / "proj"
        proj_root.mkdir()

        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        mock_db.get_project.return_value = MagicMock(root_path=str(proj_root.resolve()))

        trash = tmp_path / "trash"
        trash.mkdir()

        cmd = DeleteFileMCPCommand()
        mock_mfdc = MagicMock()
        mock_mfdc._normalize_relative_file_path.return_value = "src/m.py"
        mock_mfdc.execute = AsyncMock(
            return_value={
                "success": True,
                "file_path": "src/m.py",
                "message": "ok",
                "deleted": True,
            }
        )

        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                DeleteFileMCPCommand,
                "_resolve_config_path",
                return_value=str(tmp_path / "config.json"),
            ),
            patch(
                "code_analysis.core.storage_paths.load_raw_config",
                return_value={},
            ),
            patch(
                "code_analysis.core.storage_paths.resolve_storage_paths",
                return_value=MagicMock(trash_dir=str(trash)),
            ),
            patch(
                "code_analysis.commands.delete_file_command.MarkFileDeletedCommand",
                return_value=mock_mfdc,
            ),
        ):
            result = await cmd.execute(project_id=_PID, file_path="src/m.py")

        assert isinstance(result, SuccessResult)
        assert result.data.get("handler_id") == "python"
        assert result.data.get("legacy_full_file_delete") is True
        assert "registry_note" in result.data
