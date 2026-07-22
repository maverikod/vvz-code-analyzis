"""
Focused tests for universal_file_save routing, fail-before-write, dry_run/diff shape.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_save_command import UniversalFileSaveCommand

_PID = "550e8400-e29b-41d4-a716-446655440000"


def _assert_universal_save_ok_fields(d: dict) -> None:
    """Return assert universal save ok fields."""
    assert d.get("success") is True
    assert d.get("handler_id")
    assert d.get("operation") == "save"
    assert d.get("file_path")
    assert d.get("project_id") == _PID
    assert "dry_run" in d
    assert "changed" in d


@pytest.mark.asyncio
class TestUniversalFileSaveRouting:
    """Represent TestUniversalFileSaveRouting."""

    async def test_toml_unsupported_before_db(self) -> None:
        """Verify test toml unsupported before db."""
        cmd = UniversalFileSaveCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="cfg/app.toml",
                content="x",
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "UNSUPPORTED_FILE_EXTENSION"

    async def test_unknown_suffix_unsupported(self) -> None:
        """Verify test unknown suffix unsupported."""
        cmd = UniversalFileSaveCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="dir/blob.unknownext",
                content="x",
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "UNSUPPORTED_FILE_EXTENSION"

    async def test_missing_content_before_db(self) -> None:
        """Verify test missing content before db."""
        cmd = UniversalFileSaveCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="README.md",
                content=None,
            )
        odb.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_invalid_content_type_before_backup(self, tmp_path: Path) -> None:
        """Verify test invalid content type before backup."""
        f = tmp_path / "README.md"
        f.write_text("old\n", encoding="utf-8")
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command."
                "save_command.get_project",
                return_value=mock_project,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command.save_command.BackupManager"
            ) as bm_cls,
        ):
            cmd = UniversalFileSaveCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="README.md",
                content=123,  # type: ignore[arg-type]
            )
        bm_cls.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_json_invalid_content_before_backup(self, tmp_path: Path) -> None:
        """Verify test json invalid content before backup."""
        f = tmp_path / "data.json"
        f.write_text("{}\n", encoding="utf-8")
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command."
                "save_command.get_project",
                return_value=mock_project,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command.save_command.BackupManager"
            ) as bm_cls,
        ):
            cmd = UniversalFileSaveCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="data.json",
                content="not json {{{",
            )
        bm_cls.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "validation_failed"

    async def test_text_dry_run_no_write(self, tmp_path: Path) -> None:
        """Verify test text dry run no write."""
        f = tmp_path / "notes.txt"
        f.write_text("a\n", encoding="utf-8")
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command."
                "save_command.get_project",
                return_value=mock_project,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
        ):
            cmd = UniversalFileSaveCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes.txt",
                content="b\nc\n",
                dry_run=True,
                diff=True,
            )
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_save_ok_fields(d)
        assert d["handler_id"] == "text"
        assert d["dry_run"] is True
        assert d["changed"] is True
        assert "diff" in d
        assert f.read_text(encoding="utf-8") == "a\n"

    async def test_text_apply_with_diff(self, tmp_path: Path) -> None:
        """Verify test text apply with diff."""
        f = tmp_path / "notes.txt"
        f.write_text("a\n", encoding="utf-8")
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)
        mock_db.select.return_value = []
        mock_db.create_file.return_value = MagicMock(id="fid")

        def _fake_persist(**_: object) -> dict:
            """Return fake persist."""
            return {"success": True, "file_id": "fid"}

        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command."
                "save_command.get_project",
                return_value=mock_project,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command.save_command.persist_plain_text_file_metadata",
                side_effect=_fake_persist,
            ),
        ):
            cmd = UniversalFileSaveCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes.txt",
                content="z\n",
                dry_run=False,
                diff=True,
                backup=False,
            )
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_save_ok_fields(d)
        assert d["dry_run"] is False
        assert d["changed"] is True
        assert "diff" in d
        assert f.read_text(encoding="utf-8") == "z\n"

    async def test_text_create_missing_file(self, tmp_path: Path) -> None:
        """Verify test text create missing file."""
        target = tmp_path / "docs" / "new_note.md"
        assert not target.exists()
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)
        mock_db.select.return_value = []

        def _fake_persist(**_: object) -> dict:
            """Return fake persist."""
            return {"success": True, "file_id": "fid"}

        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command."
                "save_command.get_project",
                return_value=mock_project,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=target,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command.save_command.persist_plain_text_file_metadata",
                side_effect=_fake_persist,
            ),
        ):
            cmd = UniversalFileSaveCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="docs/new_note.md",
                content="# Title\n\nbody\n",
                backup=False,
            )
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_save_ok_fields(d)
        assert d["handler_id"] == "text"
        assert d["created"] is True
        assert target.read_text(encoding="utf-8") == "# Title\n\nbody\n"

    async def test_python_create_missing_file(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Verify test python create missing file."""
        target = tmp_path / "pkg" / "new_mod.py"
        assert not target.exists()
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)
        mock_db.select.return_value = []
        mock_db.begin_transaction.return_value = "txn-1"
        mock_db.commit_transaction.return_value = True
        created_file_mock = MagicMock()
        created_file_mock.id = "created-file-id"
        mock_db.create_file.return_value = created_file_mock
        # tree_saver.py calls the driver-direct create_file free function (stage 2
        # layer collapse) instead of database.create_file bound method; patch it at
        # its import site so mock_db.create_file above is still what gets exercised.
        monkeypatch.setattr(
            "code_analysis.core.cst_tree.tree_saver.create_file",
            lambda driver, file_obj: driver.create_file(file_obj),
        )

        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command."
                "save_command.get_project",
                return_value=mock_project,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=target,
            ),
            patch(
                "code_analysis.core.database.file_edit_lock.acquire_file_edit_lock_with_retry",
                return_value=True,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command.save_command.commit_after_write",
                return_value=(True, None),
            ),
        ):
            cmd = UniversalFileSaveCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="pkg/new_mod.py",
                content='"""New module."""\n\nanswer = 42\n',
                backup=False,
            )
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_save_ok_fields(d)
        assert d["handler_id"] == "python"
        assert d["created"] is True
        text = target.read_text(encoding="utf-8")
        assert "answer = 42" in text

    async def test_json_create_missing_file(self, tmp_path: Path) -> None:
        """Verify test json create missing file."""
        target = tmp_path / "cfg" / "app.json"
        assert not target.exists()
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)
        mock_db.select.return_value = []
        mock_db.begin_transaction.return_value = "txn-1"
        mock_db.commit_transaction.return_value = True
        mock_db.create_file.return_value = MagicMock(id=1)

        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command."
                "save_command.get_project",
                return_value=mock_project,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=target,
            ),
            patch(
                "code_analysis.core.file_handlers.text_handler.persist_plain_text_file_metadata",
                return_value={
                    "success": True,
                    "file_id": "978e605f-04a5-42f5-8fbc-0d29cab5718a",
                },
            ),
            patch(
                "code_analysis.commands.universal_file_save_command.save_command.commit_after_write",
                return_value=(True, None),
            ),
        ):
            cmd = UniversalFileSaveCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="cfg/app.json",
                content='{"enabled": true}\n',
                backup=False,
            )
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_save_ok_fields(d)
        assert d["handler_id"] == "json"
        assert d["created"] is True
        assert target.exists()
        assert '"enabled"' in target.read_text(encoding="utf-8")

    async def test_yaml_create_missing_file(self, tmp_path: Path) -> None:
        """Verify test yaml create missing file."""
        target = tmp_path / "deploy" / "svc.yaml"
        assert not target.exists()
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)

        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command."
                "save_command.get_project",
                return_value=mock_project,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=target,
            ),
            patch(
                "code_analysis.commands.universal_file_save_command.save_command.commit_after_write",
                return_value=(True, None),
            ),
        ):
            cmd = UniversalFileSaveCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="deploy/svc.yaml",
                content="replicas: 1\n",
                backup=False,
            )
        assert isinstance(result, SuccessResult)
        d = result.data
        _assert_universal_save_ok_fields(d)
        assert d["handler_id"] == "yaml"
        assert d["created"] is True
        assert "replicas: 1" in target.read_text(encoding="utf-8")
