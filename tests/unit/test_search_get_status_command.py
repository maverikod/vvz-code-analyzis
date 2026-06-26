"""Unit tests for SearchGetStatusCommand (T-005/A-002, T-006)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_analysis.commands.search_get_status_command import (
    SESSION_NOT_FOUND,
    SearchGetStatusCommand,
)
from code_analysis.core.search_session.directory import (
    provision_search_session_directory,
)
from code_analysis.core.search_session.manifest import (
    DEFAULT_METRICS,
    SearchSessionManifest,
    capture_server_process_identity,
    write_manifest_atomic,
)
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


def _make_layout(tmp_path: Path):
    """Return make layout."""
    search_id = str(uuid.uuid4())
    return provision_search_session_directory(
        sessions_root=tmp_path / "search_sessions", search_id=search_id
    )


def _write_manifest(layout, status: str = "running") -> None:
    """Return write manifest."""
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


def _cmd(tmp_path: Path) -> SearchGetStatusCommand:
    """Return cmd."""
    cmd = SearchGetStatusCommand()
    cmd._get_search_sessions_root = MagicMock(return_value=tmp_path / "search_sessions")
    return cmd


@pytest.mark.asyncio
async def test_session_not_found(tmp_path: Path) -> None:
    """Verify test session not found."""
    cmd = _cmd(tmp_path)
    result = await cmd.execute(job_id="missing")
    assert isinstance(result, ErrorResult)
    assert result.code == SESSION_NOT_FOUND  # type: ignore[comparison-overlap]


@pytest.mark.asyncio
async def test_returns_status_without_items(tmp_path: Path) -> None:
    """Verify test returns status without items."""
    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="running")
    cmd = _cmd(tmp_path)
    result = await cmd.execute(job_id=layout.root.name)
    assert isinstance(result, SuccessResult)
    data = result.data
    assert data["status"] == "running"
    assert "items" not in data
    assert "progress" in data
    assert data["job_id"] == layout.root.name


@pytest.mark.asyncio
async def test_cancelled_status_maps_correctly(tmp_path: Path) -> None:
    """Verify test cancelled status maps correctly."""
    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="cancelled")
    cmd = _cmd(tmp_path)
    result = await cmd.execute(job_id=layout.root.name)
    assert isinstance(result, SuccessResult)
    assert result.data["status"] == "cancelled"


@pytest.mark.asyncio
async def test_timed_out_status_maps_correctly(tmp_path: Path) -> None:
    """Verify test timed out status maps correctly."""
    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="timed_out")
    cmd = _cmd(tmp_path)
    result = await cmd.execute(job_id=layout.root.name)
    assert isinstance(result, SuccessResult)
    assert result.data["status"] == "timed_out"
