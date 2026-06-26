"""
Focused tests for universal_file_replace routing, validation order, dry_run/diff.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_replace_command import (
    UniversalFileReplaceCommand,
)

_PID = "550e8400-e29b-41d4-a716-446655440000"


def _assert_universal_replace_ok_fields(d: dict) -> None:
    """Return assert universal replace ok fields."""
    assert d.get("success") is True
    assert d.get("handler_id")
    assert d.get("operation") == "replace"
    assert d.get("file_path")
    assert d.get("project_id") == _PID
    assert "dry_run" in d
    assert "changed" in d


@pytest.mark.asyncio
class TestUniversalFileReplaceRouting:
    """Represent TestUniversalFileReplaceRouting."""

    async def test_toml_unsupported_before_db(self) -> None:
        """Verify test toml unsupported before db."""
        cmd = UniversalFileReplaceCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="cfg/app.toml",
                start_line=1,
                end_line=1,
                new_lines=["x"],
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "UNSUPPORTED_FILE_EXTENSION"

    async def test_text_missing_payload_before_db(self) -> None:
        """Verify test text missing payload before db."""
        cmd = UniversalFileReplaceCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(project_id=_PID, file_path="README.md")
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_json_missing_operations_before_db(self) -> None:
        """Verify test json missing operations before db."""
        cmd = UniversalFileReplaceCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="data.json",
                operations=None,
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_yaml_missing_value_before_db(self) -> None:
        """Verify test yaml missing value before db."""
        cmd = UniversalFileReplaceCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="cfg/x.yaml",
                yaml_path="/a",
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_python_missing_ops_before_db(self) -> None:
        """Verify test python missing ops before db."""
        cmd = UniversalFileReplaceCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="src/m.py",
                ops=None,
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_file_not_found_after_db(self, tmp_path: Path) -> None:
        """Verify test file not found after db."""
        missing = tmp_path / "nope.txt"
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
            cmd = UniversalFileReplaceCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="nope.txt",
                start_line=1,
                end_line=1,
                new_lines=["a"],
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "FILE_NOT_FOUND"

    async def test_text_overlapping_replacements_no_write(self, tmp_path: Path) -> None:
        """Verify test text overlapping replacements no write."""
        f = tmp_path / "t.txt"
        f.write_text("l1\nl2\nl3\n", encoding="utf-8")
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
                "code_analysis.commands.universal_file_replace_command.BackupManager"
            ) as bm_cls,
        ):
            cmd = UniversalFileReplaceCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="t.txt",
                replacements=[
                    {"start_line": 1, "end_line": 1, "new_lines": ["a"]},
                    {"start_line": 1, "end_line": 2, "new_lines": ["b"]},
                ],
            )
        bm_cls.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_RANGE"
        assert f.read_text(encoding="utf-8") == "l1\nl2\nl3\n"

    async def test_text_dry_run_diff_shape(self, tmp_path: Path) -> None:
        """Verify test text dry run diff shape."""
        f = tmp_path / "notes.txt"
        f.write_text("a\nb\n", encoding="utf-8")
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
            cmd = UniversalFileReplaceCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes.txt",
                start_line=1,
                end_line=1,
                new_lines=["z"],
                dry_run=True,
                diff=True,
            )
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_replace_ok_fields(d)
        assert d["handler_id"] == "text"
        assert d["dry_run"] is True
        assert "diff" in d
        assert "changed_line_ranges" in d
        assert f.read_text(encoding="utf-8") == "a\nb\n"

    async def test_text_apply_metadata_restore_on_failure(self, tmp_path: Path) -> None:
        """Verify test text apply metadata restore on failure."""
        f = tmp_path / "notes.txt"
        f.write_text("a\n", encoding="utf-8")
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
                "code_analysis.commands.universal_file_replace_command.persist_plain_text_file_metadata",
                return_value={"success": False, "error": "db fail"},
            ),
            patch(
                "code_analysis.commands.universal_file_replace_command.BackupManager"
            ) as bm_cls,
        ):
            mock_bm = MagicMock()
            mock_bm.create_backup.return_value = "bu-1"

            def _do_restore(*_a: object, **_k: object) -> None:
                """Return do restore."""
                f.write_text("a\n", encoding="utf-8")

            mock_bm.restore_file.side_effect = _do_restore
            bm_cls.return_value = mock_bm

            cmd = UniversalFileReplaceCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes.txt",
                start_line=1,
                end_line=1,
                new_lines=["z"],
                dry_run=False,
                backup=True,
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "UPDATE_FILE_DATA_ERROR"
        mock_bm.restore_file.assert_called_once()
        assert f.read_text(encoding="utf-8") == "a\n"
