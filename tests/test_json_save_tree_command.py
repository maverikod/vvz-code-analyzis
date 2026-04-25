"""
Tests for json_save_tree MCP command path safety.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.json_save_tree_command import JsonSaveTreeCommand
from code_analysis.core.json_tree.tree_builder import build_tree_from_data

_PID = "900fe94a-1d93-41be-bba1-0ebddbd1e5d1"


class _FakeDatabase:
    def __init__(self, root_path: Path) -> None:
        self._project = SimpleNamespace(root_path=str(root_path))

    def get_project(self, project_id: str):
        return self._project if project_id == _PID else None

    def disconnect(self) -> None:
        return None

    def select(self, *args, **kwargs):
        return []

    def begin_transaction(self):
        return "tx-1"

    def commit_transaction(self, tx_id):
        return None

    def rollback_transaction(self, tx_id):
        return None

    def create_file(self, file_obj):
        created = MagicMock()
        created.id = 1
        return created

    def update_file(self, file_obj):
        return None


@pytest.mark.asyncio
class TestJsonSaveTreeCommandPathSafety:
    async def test_json_save_tree_rejects_parent_traversal(self, tmp_path: Path) -> None:
        cmd = JsonSaveTreeCommand()
        cmd._open_database_from_config = MagicMock(return_value=_FakeDatabase(tmp_path))

        result = await cmd.execute(
            tree_id="missing-tree",
            project_id=_PID,
            file_path="../escape.json",
            backup=False,
            auto_reload=False,
            dry_run=True,
        )

        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_FILE_PATH"

    async def test_json_save_tree_rejects_nested_parent_traversal(
        self, tmp_path: Path
    ) -> None:
        cmd = JsonSaveTreeCommand()
        cmd._open_database_from_config = MagicMock(return_value=_FakeDatabase(tmp_path))

        result = await cmd.execute(
            tree_id="missing-tree",
            project_id=_PID,
            file_path="json_cases/../../escape.json",
            backup=False,
            auto_reload=False,
            dry_run=True,
        )

        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_FILE_PATH"

    async def test_json_save_tree_rejects_absolute_path(self, tmp_path: Path) -> None:
        cmd = JsonSaveTreeCommand()
        cmd._open_database_from_config = MagicMock(return_value=_FakeDatabase(tmp_path))

        result = await cmd.execute(
            tree_id="missing-tree",
            project_id=_PID,
            file_path="/tmp/escape.json",
            backup=False,
            auto_reload=False,
            dry_run=True,
        )

        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_FILE_PATH"

    async def test_json_save_tree_rejects_resolved_escape_symlink(
        self, tmp_path: Path
    ) -> None:
        outside_dir = tmp_path.parent / "outside-json-save"
        outside_dir.mkdir(exist_ok=True)
        link = tmp_path / "json_cases" / "link"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside_dir, target_is_directory=True)

        cmd = JsonSaveTreeCommand()
        cmd._open_database_from_config = MagicMock(return_value=_FakeDatabase(tmp_path))

        result = await cmd.execute(
            tree_id="missing-tree",
            project_id=_PID,
            file_path="json_cases/link/escape.json",
            backup=False,
            auto_reload=False,
            dry_run=True,
        )

        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_FILE_PATH"

    async def test_json_save_tree_non_json_extension_still_rejected(
        self, tmp_path: Path
    ) -> None:
        txt_target = tmp_path / "json_cases" / "file.txt"
        txt_target.parent.mkdir(parents=True, exist_ok=True)
        txt_target.write_text("{}", encoding="utf-8")

        cmd = JsonSaveTreeCommand()
        cmd._open_database_from_config = MagicMock(return_value=_FakeDatabase(tmp_path))

        result = await cmd.execute(
            tree_id="missing-tree",
            project_id=_PID,
            file_path="json_cases/file.txt",
            backup=False,
            auto_reload=False,
            dry_run=True,
        )

        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_FILE"

    async def test_json_save_tree_dry_run_validates_path(self, tmp_path: Path) -> None:
        cmd = JsonSaveTreeCommand()
        cmd._open_database_from_config = MagicMock(return_value=_FakeDatabase(tmp_path))

        result = await cmd.execute(
            tree_id="missing-tree",
            project_id=_PID,
            file_path="../escape.json",
            backup=False,
            auto_reload=False,
            dry_run=True,
        )

        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_FILE_PATH"

    async def test_json_save_tree_valid_relative_path_still_works(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "json_cases" / "valid.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
        tree = build_tree_from_data(str(target), {"ok": True}, register=True)

        monkeypatch.setattr(
            "code_analysis.core.json_tree.json_saver.update_file_data_atomic_batch",
            lambda **kwargs: {"success": True},
        )

        cmd = JsonSaveTreeCommand()
        cmd._open_database_from_config = MagicMock(return_value=_FakeDatabase(tmp_path))

        result = await cmd.execute(
            tree_id=tree.tree_id,
            project_id=_PID,
            file_path="json_cases/valid.json",
            backup=False,
            auto_reload=False,
            dry_run=False,
        )

        assert isinstance(result, SuccessResult)
        assert result.data["success"] is True
