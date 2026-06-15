"""Unit tests for SearchCancelCommand (T-005/A-003, T-006)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.commands.search_cancel_command import (
    SESSION_NOT_FOUND,
    SearchCancelCommand,
)
from code_analysis.core.search_session.directory import (
    provision_search_session_directory,
)
from code_analysis.core.search_session.manifest import (
    DEFAULT_METRICS,
    SearchSessionManifest,
    capture_server_process_identity,
    read_manifest,
    write_manifest_atomic,
)
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


def _make_layout(tmp_path: Path):
    search_id = str(uuid.uuid4())
    return provision_search_session_directory(sessions_root=tmp_path / "search_sessions", search_id=search_id)


def _write_manifest(layout, status: str = "running") -> None:
    now = time.time()
    manifest = SearchSessionManifest(
        search_id=layout.root.name,
        created_at=now,
        last_access_at=now,
        heartbeat_at=now,
        status=status,
        phase="indexed_search",
        request={},
        metrics=dict(DEFAULT_METRICS),
        process=capture_server_process_identity(),
        block_ready_count=0,
    )
    write_manifest_atomic(layout, manifest)


def _cmd(tmp_path: Path) -> SearchCancelCommand:
    cmd = SearchCancelCommand()
    cmd._get_search_sessions_root = MagicMock(
        return_value=tmp_path / "search_sessions"
    )
    return cmd


@pytest.mark.asyncio
async def test_session_not_found(tmp_path: Path) -> None:
    cmd = _cmd(tmp_path)
    result = await cmd.execute(job_id="missing")
    assert isinstance(result, ErrorResult)
    assert result.code == SESSION_NOT_FOUND  # type: ignore[comparison-overlap]


@pytest.mark.asyncio
async def test_running_session_transitions_to_cancelled(tmp_path: Path) -> None:
    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="running")
    cmd = _cmd(tmp_path)
    result = await cmd.execute(job_id=layout.root.name)
    assert isinstance(result, SuccessResult)
    assert result.data["cancelled"] is True
    manifest = read_manifest(layout)
    assert manifest.status == "cancelled"


@pytest.mark.asyncio
async def test_repeated_cancel_returns_false(tmp_path: Path) -> None:
    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="cancelled")
    cmd = _cmd(tmp_path)
    result = await cmd.execute(job_id=layout.root.name)
    assert isinstance(result, SuccessResult)
    assert result.data["cancelled"] is False


@pytest.mark.asyncio
async def test_schema_requires_job_id_not_search_id(tmp_path: Path) -> None:
    schema = SearchCancelCommand.get_schema()
    assert "job_id" in schema["required"]
    assert "search_id" not in schema.get("properties", {})


@pytest.mark.asyncio
async def test_cancel_queued_job_invoked_when_queue_job_id_present(tmp_path: Path) -> None:
    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="running")
    cmd = _cmd(tmp_path)
    with patch(
        "code_analysis.commands.search_cancel_command.queue_job_id_from_manifest",
        return_value="qjob-123",
    ), patch(
        "code_analysis.commands.search_cancel_command.cancel_queued_search_job",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_cancel:
        result = await cmd.execute(job_id=layout.root.name)
    assert isinstance(result, SuccessResult)
    mock_cancel.assert_awaited_once_with("qjob-123")
