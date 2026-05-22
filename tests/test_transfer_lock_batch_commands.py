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
    ProjectFileTransferUploadSaveCommand,
    _validate_download_params,
    _validate_upload_selector_params,
)
from code_analysis.core.runtime_lock_sessions import get_session_id_for_current_pid
from code_analysis.core.transfer_lock_registry import release_transfer_lock
from code_analysis.core.exceptions import ValidationError
from mcp_proxy_adapter.commands.result import SuccessResult


class _FakeDatabase:
    def __init__(self, root: Path, indexed: Optional[set[str]] = None) -> None:
        self.root = root
        self.indexed = indexed or set()
        self._rows: Dict[str, Dict[str, Any]] = {}
        self.sessions: set[str] = set()
        self.client_sessions: set[str] = set()
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
        if "update client_sessions" in text and params:
            sid = str(params[0])
            if sid in self.client_sessions:
                return {"affected_rows": 1}
            return {"affected_rows": 0}
        if "from client_sessions" in text or "into client_sessions" in text:
            if "select" in text and params:
                sid = str(params[0])
                if sid in self.client_sessions:
                    return {
                        "data": [
                            {
                                "session_id": sid,
                                "comment": "test",
                                "created_at": 0.0,
                                "last_active_at": 0.0,
                            }
                        ]
                    }
                return {"data": []}
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
        row = self._rows.get(rel)
        if row and row.get("deleted") and not include_deleted:
            return None
        return row

    def add_file(
        self,
        path: str,
        lines: int,
        last_modified: float,
        has_docstring: bool,
        project_id: str,
    ) -> str:
        rel = str(Path(path).resolve().relative_to(self.root))
        file_id = f"id:{rel}"
        self._rows[rel] = {
            "id": file_id,
            "project_id": project_id,
            "relative_path": rel,
            "deleted": False,
        }
        self.indexed.add(rel)
        return file_id


def test_validate_upload_selector_allows_file_id_without_project_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    def _validate(pid: str) -> None:
        called.append(pid)

    monkeypatch.setattr(
        "code_analysis.commands.project_file_transfer_by_id_commands.BaseMCPCommand._validate_project_id_exists",
        _validate,
    )
    _validate_upload_selector_params({"file_id": "file-1", "compression": "identity"})
    assert called == []


def test_validate_upload_selector_requires_project_id_for_file_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "code_analysis.commands.project_file_transfer_by_id_commands.BaseMCPCommand._validate_project_id_exists",
        lambda pid: None,
    )
    with pytest.raises(ValidationError, match="project_id is required when file_id is omitted"):
        _validate_upload_selector_params(
            {"file_path": "src/app.py", "compression": "identity"}
        )


def test_validate_download_params_requires_file_id() -> None:
    with pytest.raises(ValidationError, match="file_id is required"):
        _validate_download_params({"compression": "identity"})


def test_validate_download_params_rejects_file_path() -> None:
    with pytest.raises(ValidationError, match="file_path is not supported"):
        _validate_download_params(
            {
                "file_id": "file-1",
                "file_path": "src/app.py",
                "compression": "identity",
            }
        )


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
    client_session = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    database.client_sessions.add(client_session)

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
        session_id=client_session,
        file_id="file-1",
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


@pytest.mark.asyncio
async def test_transfer_download_begin_fails_when_db_row_but_missing_on_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = _FakeDatabase(tmp_path)

    def _select(
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        if table_name == "files" and str((where or {}).get("id") or "") == "file-1":
            return [
                {
                    "id": "file-1",
                    "project_id": "project-1",
                    "relative_path": "src/missing.py",
                    "deleted": False,
                }
            ]
        return []

    database.select = _select  # type: ignore[method-assign]

    cmd = ProjectFileTransferDownloadBeginCommand()
    monkeypatch.setattr(
        cmd, "_open_database_from_config", lambda auto_analyze=False: database
    )

    result = await cmd.execute(
        project_id="project-1",
        file_id="file-1",
        compression="identity",
        include_backup_history=False,
        lock_mode="none",
    )

    from mcp_proxy_adapter.commands.result import ErrorResult

    assert isinstance(result, ErrorResult)
    assert result.code == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_transfer_upload_save_registers_and_returns_file_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = _FakeDatabase(tmp_path)
    target = tmp_path / "incoming.py"

    async def _fake_save(_self: Any, **kwargs: Any) -> SuccessResult:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(kwargs.get("content") or ""), encoding="utf-8")
        return SuccessResult(
            data={
                "success": True,
                "handler_id": "text",
                "operation": "save",
                "file_path": kwargs.get("file_path"),
                "project_id": kwargs.get("project_id"),
                "changed": True,
                "dry_run": False,
            }
        )

    monkeypatch.setattr(
        "code_analysis.commands.project_file_transfer_by_id_commands."
        "UniversalFileSaveCommand.execute",
        _fake_save,
    )
    monkeypatch.setattr(
        "code_analysis.commands.project_file_transfer_by_id_commands."
        "_read_completed_upload_text",
        lambda _tid: ("print('uploaded')\n", "identity"),
    )

    cmd = ProjectFileTransferUploadSaveCommand()
    monkeypatch.setattr(
        cmd, "_open_database_from_config", lambda auto_analyze=False: database
    )

    result = await cmd.execute(
        transfer_id="upload-1",
        project_id="project-1",
        file_path="incoming.py",
        lock_mode="none",
        unlock_after_write=False,
    )

    assert isinstance(result, SuccessResult)
    assert result.data["file_id"] == "id:incoming.py"
    assert target.is_file()
    assert database.get_file_by_path(str(target), "project-1") is not None
