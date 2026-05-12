"""
Tests for transfer advisory locks and project_file_advisory_lock_batch.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from code_analysis.commands.project_file_advisory_lock_batch_command import (
    ProjectFileAdvisoryLockBatchCommand,
)
from code_analysis.commands.project_file_transfer_by_id_commands import (
    ProjectFileTransferDownloadBeginCommand,
)
from code_analysis.core.runtime_lock_sessions import get_session_id_for_current_pid
from code_analysis.core.transfer_lock_registry import release_transfer_lock
from mcp_proxy_adapter.commands.result import SuccessResult


class _FakeDatabase:
    def __init__(self, root: Path, indexed: Optional[set[str]] = None) -> None:
        self.root = root
        self.indexed = indexed or set()
        self.sessions: set[str] = set()
        self.leases: List[Dict[str, Any]] = []

    def execute(self, sql: str, params: Any = None, **kwargs: Any) -> Dict[str, Any]:
        text = " ".join(sql.split()).lower()
        params = tuple(params or ())
        if "select session_id from runtime_lock_sessions where pid" in text:
            return {"data": []}
        if "select session_id from runtime_lock_sessions where session_id" in text:
            sid = str(params[0])
            return {"data": [{"session_id": sid}] if sid in self.sessions else []}
        if "insert into runtime_lock_sessions" in text:
            self.sessions.add(str(params[0]))
            return {"affected_rows": 1}
        if "delete from runtime_lock_sessions" in text:
            if params and isinstance(params[0], int):
                self.sessions.clear()
            elif params:
                self.sessions.discard(str(params[0]))
            return {"affected_rows": 1}
        if "select refcount from file_advisory_lock_leases" in text:
            return {"data": []}
        if "select lock_mode, refcount from file_advisory_lock_leases" in text:
            rows = [
                {"lock_mode": row["lock_mode"], "refcount": 1}
                for row in self.leases
                if row["session_id"] == params[0]
                and row["project_id"] == params[1]
                and row["file_path"] == params[2]
            ]
            return {"data": rows}
        if "insert into file_advisory_lock_leases" in text:
            self.leases.append(
                {
                    "session_id": params[0],
                    "project_id": params[1],
                    "file_path": params[2],
                    "lock_mode": params[3],
                    "transfer_id": None,
                }
            )
            return {"affected_rows": 1}
        if "delete from file_advisory_lock_leases" in text:
            before = len(self.leases)
            if len(params) >= 3:
                self.leases = [
                    row
                    for row in self.leases
                    if not (
                        row["session_id"] == params[0]
                        and row["project_id"] == params[1]
                        and row["file_path"] == params[2]
                    )
                ]
            return {"affected_rows": before - len(self.leases)}
        return {"affected_rows": 0}

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        if table_name == "runtime_lock_sessions":
            sid = str((where or {}).get("session_id") or "")
            return [{"session_id": sid}] if sid in self.sessions else []
        if table_name == "files":
            file_id = str((where or {}).get("id") or "")
            if file_id == "file-1":
                return [
                    {
                        "id": "file-1",
                        "project_id": "project-1",
                        "relative_path": "src/app.py",
                        "deleted": False,
                    }
                ]
        return []

    def get_project(self, project_id: str) -> Any:
        if project_id == "project-1":
            return SimpleNamespace(root_path=str(self.root))
        return None

    def get_file_by_path(
        self, abs_path: str, project_id: str, include_deleted: bool = False
    ) -> Optional[Dict[str, Any]]:
        rel = str(Path(abs_path).resolve().relative_to(self.root))
        if project_id == "project-1" and rel in self.indexed:
            return {"id": f"id:{rel}", "project_id": project_id, "relative_path": rel}
        return None


@pytest.mark.asyncio
async def test_project_file_advisory_lock_batch_partial_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("print('ok')\n", encoding="utf-8")
    database = _FakeDatabase(tmp_path, indexed={"src/app.py"})
    current_session = get_session_id_for_current_pid(database, role="daemon")

    cmd = ProjectFileAdvisoryLockBatchCommand()
    monkeypatch.setattr(
        cmd, "_open_database_from_config", lambda auto_analyze=False: database
    )

    result = await cmd.execute(
        items=[
            {
                "session_id": current_session,
                "project_id": "project-1",
                "file_path": "src/app.py",
                "action": "unlock",
            },
            {
                "session_id": current_session,
                "project_id": "project-1",
                "file_path": "src/missing.py",
                "action": "lock",
                "lock_mode": "full",
            },
            {
                "session_id": current_session,
                "project_id": "project-1",
                "file_path": "src/app.py",
                "action": "lock",
                "lock_mode": "block_write",
            },
            {
                "session_id": current_session,
                "project_id": "project-1",
                "file_path": "src/app.py",
                "action": "unlock",
            },
        ]
    )

    assert isinstance(result, SuccessResult)
    assert result.data["total"] == 4
    assert result.data["succeeded"] == 3
    assert result.data["failed"] == 1
    assert [item["ok"] for item in result.data["results"]] == [True, False, True, True]
    assert result.data["results"][1]["code"] in {"PATH_ERROR", "FILE_NOT_FOUND"}


@pytest.mark.asyncio
async def test_transfer_download_begin_accepts_and_binds_lock_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("print('ok')\n", encoding="utf-8")
    database = _FakeDatabase(tmp_path, indexed={"src/app.py"})

    async def _fake_create_download_session(payload: Dict[str, Any]) -> Dict[str, Any]:
        assert payload["source_path"] == str(target)
        return {
            "transfer_id": "transfer-1",
            "filename": "app.py",
            "size_bytes": target.stat().st_size,
            "checksum_algorithm": "sha256",
            "checksum_value": "a" * 64,
            "compression": payload["compression"],
            "chunk_size": 1024,
            "offset": 0,
            "status": "ready",
        }

    monkeypatch.setattr(
        "code_analysis.commands.project_file_transfer_by_id_commands.run_create_download_session",
        _fake_create_download_session,
    )
    cmd = ProjectFileTransferDownloadBeginCommand()
    monkeypatch.setattr(
        cmd, "_open_database_from_config", lambda auto_analyze=False: database
    )

    result = await cmd.execute(
        project_id="project-1",
        file_path="src/app.py",
        compression="identity",
        include_backup_history=False,
        lock_mode="block_write",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["transfer_id"] == "transfer-1"
    assert result.data["lock_mode"] == "block_write"
    assert result.data["lock_session_id"]
    assert database.leases[0]["lock_mode"] == "shared"
    release_transfer_lock("transfer-1")
