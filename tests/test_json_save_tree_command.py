"""
Tests for json_save_tree MCP command path safety.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.json_save_tree_command import JsonSaveTreeCommand
from code_analysis.core.json_tree.tree_builder import build_tree_from_data

_PID = "900fe94a-1d93-41be-bba1-0ebddbd1e5d1"


class _FakeDatabase:
    """Represent FakeDatabase."""

    def __init__(self, root_path: Path) -> None:
        """Initialize the instance."""
        self._project = SimpleNamespace(root_path=str(root_path))
        self._sessions: set[str] = set()
        self._leases: List[Dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None, **kwargs: Any) -> Dict[str, Any]:
        """Execute the command."""
        text = " ".join(sql.split()).lower()
        params = tuple(params or ())
        if "create table" in text or "create index" in text:
            return {"affected_rows": 0}
        if "select session_id from runtime_lock_sessions where pid" in text:
            return {"data": []}
        if "select session_id from runtime_lock_sessions where session_id" in text:
            sid = str(params[0])
            return {"data": [{"session_id": sid}] if sid in self._sessions else []}
        if "insert into runtime_lock_sessions" in text:
            self._sessions.add(str(params[0]))
            return {"affected_rows": 1}
        if "delete from runtime_lock_sessions" in text:
            if params and isinstance(params[0], int):
                self._sessions.clear()
            elif params:
                self._sessions.discard(str(params[0]))
            return {"affected_rows": 1}
        if "select refcount from file_advisory_lock_leases" in text:
            return {"data": []}
        if "select lock_mode, refcount from file_advisory_lock_leases" in text:
            rows = [
                {"lock_mode": row["lock_mode"], "refcount": 1}
                for row in self._leases
                if row["session_id"] == params[0]
                and row["project_id"] == params[1]
                and row["file_path"] == params[2]
            ]
            return {"data": rows}
        if "insert into file_advisory_lock_leases" in text:
            self._leases.append(
                {
                    "session_id": params[0],
                    "project_id": params[1],
                    "file_path": params[2],
                    "lock_mode": params[3],
                }
            )
            return {"affected_rows": 1}
        if "delete from file_advisory_lock_leases" in text:
            before = len(self._leases)
            if len(params) >= 3:
                self._leases = [
                    row
                    for row in self._leases
                    if not (
                        row["session_id"] == params[0]
                        and row["project_id"] == params[1]
                        and row["file_path"] == params[2]
                        and (len(params) < 4 or row["lock_mode"] == params[3])
                    )
                ]
            return {"affected_rows": before - len(self._leases)}
        if "select editing_pid from files" in text:
            return {"data": []}
        if "update files set editing_pid" in text:
            return {"affected_rows": 1}
        if text.startswith("select") or "pragma" in text:
            return {"data": []}
        return {"affected_rows": 0}

    def commit(self) -> None:
        """Return commit."""
        return None

    def get_project(self, project_id: str):
        """Return get project."""
        return self._project if project_id == _PID else None

    def disconnect(self) -> None:
        """Return disconnect."""
        return None

    def select(self, *args, **kwargs):
        """Return select."""
        return []

    def begin_transaction(self):
        """Return begin transaction."""
        return "tx-1"

    def commit_transaction(self, tx_id):
        """Return commit transaction."""
        return None

    def rollback_transaction(self, tx_id):
        """Return rollback transaction."""
        return None

    def create_file(self, file_obj):
        """Return create file."""
        created = MagicMock()
        created.id = 1
        return created

    def update_file(self, file_obj):
        """Return update file."""
        return None


@pytest.mark.asyncio
class TestJsonSaveTreeCommandPathSafety:
    """Represent TestJsonSaveTreeCommandPathSafety."""

    async def test_json_save_tree_rejects_parent_traversal(
        self, tmp_path: Path
    ) -> None:
        """Verify test json save tree rejects parent traversal."""
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
        """Verify test json save tree rejects nested parent traversal."""
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
        """Verify test json save tree rejects absolute path."""
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
        """Verify test json save tree rejects resolved escape symlink."""
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
        """Verify test json save tree non json extension still rejected."""
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
        """Verify test json save tree dry run validates path."""
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
        """Verify test json save tree valid relative path still works."""
        target = tmp_path / "json_cases" / "valid.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
        tree = build_tree_from_data(str(target), {"ok": True}, register=True)

        monkeypatch.setattr(
            "code_analysis.core.file_handlers.text_handler.persist_plain_text_file_metadata",
            lambda **kwargs: {
                "success": True,
                "file_id": "53094b18-b8a3-482f-a73d-3a102ecb1fd1",
            },
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
