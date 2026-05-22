"""Tests for FileSessionClient workflow helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis_client import (
    ClientValidationError,
    CodeAnalysisAsyncClient,
    FileSessionClient,
    SessionNotFoundError,
)


@pytest.mark.asyncio
async def test_create_session_returns_session_id() -> None:
    mock_rpc = MagicMock()
    mock_rpc.execute_command = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "session_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "comment": "t",
            },
        }
    )
    mock_rpc.help = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "schema": {
                    "type": "object",
                    "properties": {"comment": {"type": "string"}},
                    "required": ["comment"],
                    "additionalProperties": False,
                }
            },
        }
    )
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        fs = FileSessionClient(client)
        sid = await fs.create_session("t")
    assert sid == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.mark.asyncio
async def test_assert_session_exists_raises_on_missing() -> None:
    mock_rpc = MagicMock()
    mock_rpc.execute_command = AsyncMock(
        return_value={
            "success": False,
            "code": "SESSION_NOT_FOUND",
            "message": "Session 'x' not found.",
        }
    )
    mock_rpc.help = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "schema": {
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                    "additionalProperties": False,
                }
            },
        }
    )
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        fs = FileSessionClient(client)
        with pytest.raises(SessionNotFoundError):
            await fs.assert_session_exists("missing-id")


@pytest.mark.asyncio
async def test_lock_file_without_transfer() -> None:
    calls: list[tuple[str, dict]] = []

    async def _exec(command: str, params: dict, **_: object) -> dict:
        calls.append((command, params))
        if command == "session_list_file_locks":
            return {"success": True, "data": {"locks": [], "count": 0}}
        if command == "session_open_file":
            return {
                "success": True,
                "data": {"acquired": True, "session_id": params["session_id"]},
            }
        raise AssertionError(command)

    mock_rpc = MagicMock()
    mock_rpc.execute_command = AsyncMock(side_effect=_exec)
    mock_rpc.help = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": True,
                }
            },
        }
    )
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        fs = FileSessionClient(client)
        out = await fs.lock_file("sid", "pid", "fid")

    assert out["acquired"] is True
    assert (
        "session_open_file",
        {"session_id": "sid", "project_id": "pid", "file_id": "fid"},
    ) in calls


@pytest.mark.asyncio
async def test_download_by_file_id_without_project_id() -> None:
    calls: list[tuple[str, dict]] = []

    async def _exec(command: str, params: dict, **_: object) -> dict:
        calls.append((command, params))
        if command == "session_list_file_locks":
            return {"success": True, "data": {"locks": [], "count": 0}}
        if command == "project_file_transfer_download_begin":
            return {
                "success": True,
                "data": {
                    "transfer_id": "t-1",
                    "file_id": "fid",
                },
            }
        raise AssertionError(command)

    mock_rpc = MagicMock()
    mock_rpc.execute_command = AsyncMock(side_effect=_exec)
    mock_rpc.download_file = AsyncMock(return_value=SimpleNamespace(completed=True))
    mock_rpc.help = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": True,
                }
            },
        }
    )
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        fs = FileSessionClient(client)
        begin, _receipt = await fs.download("sid", "/tmp/out.bin", "fid", lock=True)

    assert begin["file_id"] == "fid"
    assert (
        "project_file_transfer_download_begin",
        {
            "session_id": "sid",
            "compression": "identity",
            "lock_mode": "full",
            "include_backup_history": True,
            "file_id": "fid",
        },
    ) in calls


@pytest.mark.asyncio
async def test_download_lock_false_uses_none_mode() -> None:
    calls: list[tuple[str, dict]] = []

    async def _exec(command: str, params: dict, **_: object) -> dict:
        calls.append((command, params))
        if command == "session_list_file_locks":
            return {"success": True, "data": {"locks": [], "count": 0}}
        if command == "project_file_transfer_download_begin":
            return {
                "success": True,
                "data": {"transfer_id": "t-2", "file_id": "fid"},
            }
        raise AssertionError(command)

    mock_rpc = MagicMock()
    mock_rpc.execute_command = AsyncMock(side_effect=_exec)
    mock_rpc.download_file = AsyncMock(return_value=SimpleNamespace(completed=True))
    mock_rpc.help = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": True,
                }
            },
        }
    )
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        fs = FileSessionClient(client)
        await fs.download("sid", "/tmp/out.bin", "fid", lock=False)

    assert (
        "project_file_transfer_download_begin",
        {
            "session_id": "sid",
            "compression": "identity",
            "lock_mode": "none",
            "include_backup_history": True,
            "file_id": "fid",
        },
    ) in calls


@pytest.mark.asyncio
async def test_download_requires_file_id() -> None:
    mock_rpc = MagicMock()
    mock_rpc.execute_command = AsyncMock()
    mock_rpc.help = AsyncMock()
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        fs = FileSessionClient(client)
        with pytest.raises(ClientValidationError, match="file_id is required"):
            await fs.download("sid", "/tmp/x", "")
    mock_rpc.execute_command.assert_not_called()


@pytest.mark.asyncio
async def test_upload_existing_file_by_file_id() -> None:
    calls: list[tuple[str, dict]] = []

    async def _exec(command: str, params: dict, **_: object) -> dict:
        calls.append((command, params))
        if command == "session_list_file_locks":
            return {"success": True, "data": {"locks": [], "count": 0}}
        if command == "project_file_transfer_upload_save":
            return {
                "success": True,
                "data": {"file_id": params["file_id"], "file_path": "src/app.py"},
            }
        raise AssertionError(command)

    mock_rpc = MagicMock()
    mock_rpc.execute_command = AsyncMock(side_effect=_exec)
    mock_rpc.upload_file = AsyncMock(
        return_value=SimpleNamespace(completed=True, transfer_id="up-1")
    )
    mock_rpc.help = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": True,
                }
            },
        }
    )
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        fs = FileSessionClient(client)
        out = await fs.upload("sid", b"data", "fid", unlock=True)

    assert out["file_id"] == "fid"
    assert (
        "project_file_transfer_upload_save",
        {
            "session_id": "sid",
            "transfer_id": "up-1",
            "unlock_after_write": True,
            "dry_run": False,
            "backup": True,
            "file_id": "fid",
        },
    ) in calls


@pytest.mark.asyncio
async def test_upload_unlock_false() -> None:
    calls: list[tuple[str, dict]] = []

    async def _exec(command: str, params: dict, **_: object) -> dict:
        calls.append((command, params))
        if command == "session_list_file_locks":
            return {"success": True, "data": {"locks": [], "count": 0}}
        if command == "project_file_transfer_upload_save":
            return {"success": True, "data": {"file_id": params["file_id"]}}
        raise AssertionError(command)

    mock_rpc = MagicMock()
    mock_rpc.execute_command = AsyncMock(side_effect=_exec)
    mock_rpc.upload_file = AsyncMock(
        return_value=SimpleNamespace(completed=True, transfer_id="up-2")
    )
    mock_rpc.help = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": True,
                }
            },
        }
    )
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        fs = FileSessionClient(client)
        await fs.upload("sid", b"data", "fid", unlock=False)

    assert (
        "project_file_transfer_upload_save",
        {
            "session_id": "sid",
            "transfer_id": "up-2",
            "unlock_after_write": False,
            "dry_run": False,
            "backup": True,
            "file_id": "fid",
        },
    ) in calls


@pytest.mark.asyncio
async def test_upload_new_requires_project_and_path() -> None:
    mock_rpc = MagicMock()
    mock_rpc.execute_command = AsyncMock()
    mock_rpc.help = AsyncMock()
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        fs = FileSessionClient(client)
        with pytest.raises(ClientValidationError, match="file_path is required"):
            await fs.upload_new("sid", b"x", "pid", "")
    mock_rpc.execute_command.assert_not_called()


@pytest.mark.asyncio
async def test_commit_upload_rejects_file_id_and_file_path() -> None:
    mock_rpc = MagicMock()
    mock_rpc.execute_command = AsyncMock()
    mock_rpc.help = AsyncMock()
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        fs = FileSessionClient(client)
        with pytest.raises(ClientValidationError, match="exactly one of file_id"):
            await fs._commit_upload(
                "sid",
                "tid",
                file_id="fid",
                file_path="src/a.py",
                project_id="pid",
            )
    mock_rpc.execute_command.assert_not_called()
