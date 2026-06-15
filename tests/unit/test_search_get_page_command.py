"""Unit tests for SearchGetPageCommand (T-005/A-001, T-006)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.search_get_page_command import (
    BLOCK_NOT_READY,
    CLOSED_SESSION,
    SESSION_NOT_FOUND,
    SearchGetPageCommand,
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
    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(
        sessions_root=tmp_path / "search_sessions", search_id=search_id
    )
    return layout


def _write_manifest(layout, status: str = "running") -> None:
    import time

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
        block_ready_count=1,
    )
    write_manifest_atomic(layout, manifest)


def _write_block(layout, position: int = 1) -> None:
    block_path = layout.blocks_dir / f"block_{position}.json"
    block_path.write_text(
        json.dumps({"position": position, "items": [{"result_id": f"r{position}"}]})
    )


def _cmd_with_sessions_root(tmp_path: Path) -> SearchGetPageCommand:
    cmd = SearchGetPageCommand()
    sessions_root = tmp_path / "search_sessions"
    cmd._get_search_sessions_root = MagicMock(return_value=sessions_root)
    return cmd


_cmd_with_storage = _cmd_with_sessions_root


@pytest.mark.asyncio
async def test_session_not_found(tmp_path: Path) -> None:
    cmd = _cmd_with_storage(tmp_path)
    result = await cmd.execute(job_id="nonexistent-job")
    assert isinstance(result, ErrorResult)
    assert result.code == SESSION_NOT_FOUND  # type: ignore[comparison-overlap]


@pytest.mark.asyncio
async def test_block_not_ready_when_running_and_no_block(tmp_path: Path) -> None:
    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="running")
    cmd = _cmd_with_storage(tmp_path)
    result = await cmd.execute(job_id=layout.root.name, block_position=1)
    assert isinstance(result, ErrorResult)
    assert result.code == BLOCK_NOT_READY  # type: ignore[comparison-overlap]


@pytest.mark.asyncio
async def test_returns_block_items_when_published(tmp_path: Path) -> None:
    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="completed")
    _write_block(layout, position=1)
    cmd = _cmd_with_storage(tmp_path)
    result = await cmd.execute(job_id=layout.root.name, block_position=1)
    assert isinstance(result, SuccessResult)
    data = result.data
    assert data["block_position"] == 1
    assert data["job_id"] == layout.root.name
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_closed_session_returns_closed_error(tmp_path: Path) -> None:
    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="closed")
    _write_block(layout, position=1)
    cmd = _cmd_with_storage(tmp_path)
    result = await cmd.execute(job_id=layout.root.name, block_position=1)
    assert isinstance(result, ErrorResult)
    assert result.code == CLOSED_SESSION  # type: ignore[comparison-overlap]


@pytest.mark.asyncio
async def test_block_position_uses_default_1(tmp_path: Path) -> None:
    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="completed")
    _write_block(layout, position=1)
    cmd = _cmd_with_storage(tmp_path)
    result = await cmd.execute(job_id=layout.root.name)
    assert isinstance(result, SuccessResult)
    assert result.data["block_position"] == 1
