"""Unit tests for SearchCloseCommand (T-005/A-004, T-006)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_analysis.commands.search_close_command import (
    SESSION_NOT_FOUND,
    SearchCloseCommand,
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
    return provision_search_session_directory(config_dir=tmp_path, search_id=search_id)


def _write_manifest(layout, status: str = "completed") -> None:
    now = time.time()
    manifest = SearchSessionManifest(
        search_id=layout.root.name,
        created_at=now,
        last_access_at=now,
        heartbeat_at=now,
        status=status,
        phase="completion",
        request={},
        metrics=dict(DEFAULT_METRICS),
        process=capture_server_process_identity(),
        block_ready_count=1,
    )
    write_manifest_atomic(layout, manifest)


def _cmd(tmp_path: Path) -> SearchCloseCommand:
    cmd = SearchCloseCommand()
    storage = MagicMock()
    storage.config_dir = tmp_path
    cmd._get_shared_storage = MagicMock(return_value=storage)
    return cmd


@pytest.mark.asyncio
async def test_session_not_found(tmp_path: Path) -> None:
    cmd = _cmd(tmp_path)
    result = await cmd.execute(job_id="missing")
    assert isinstance(result, ErrorResult)
    assert result.code == SESSION_NOT_FOUND  # type: ignore[comparison-overlap]


@pytest.mark.asyncio
async def test_close_sets_manifest_status_closed(tmp_path: Path) -> None:
    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="completed")
    cmd = _cmd(tmp_path)
    result = await cmd.execute(job_id=layout.root.name)
    assert isinstance(result, SuccessResult)
    assert result.data["closed"] is True
    manifest = read_manifest(layout)
    assert manifest.status == "closed"


@pytest.mark.asyncio
async def test_buffer_scratch_files_removed(tmp_path: Path) -> None:
    layout = _make_layout(tmp_path)
    _write_manifest(layout)
    scratch = layout.buffer_dir / "finding_000001.jsonl"
    scratch.write_text('{"result_id": "r1"}')
    assert scratch.is_file()
    cmd = _cmd(tmp_path)
    await cmd.execute(job_id=layout.root.name)
    assert not scratch.is_file()


@pytest.mark.asyncio
async def test_blocks_remain_after_close(tmp_path: Path) -> None:
    layout = _make_layout(tmp_path)
    _write_manifest(layout)
    block = layout.blocks_dir / "block_1.json"
    block.write_text('{"position": 1, "items": []}')
    cmd = _cmd(tmp_path)
    await cmd.execute(job_id=layout.root.name)
    assert block.is_file(), "Blocks must remain until cleaner TTL"


@pytest.mark.asyncio
async def test_cursor_invalid_after_close(tmp_path: Path) -> None:
    """After close, search_get_page should return CLOSED_SESSION."""
    from code_analysis.commands.search_get_page_command import (
        CLOSED_SESSION,
        SearchGetPageCommand,
    )
    import json

    layout = _make_layout(tmp_path)
    _write_manifest(layout, status="completed")
    block = layout.blocks_dir / "block_1.json"
    block.write_text(json.dumps({"position": 1, "items": []}))

    close_cmd = _cmd(tmp_path)
    await close_cmd.execute(job_id=layout.root.name)

    get_page_cmd = SearchGetPageCommand()
    storage = MagicMock()
    storage.config_dir = tmp_path
    get_page_cmd._get_shared_storage = MagicMock(return_value=storage)
    page_result = await get_page_cmd.execute(job_id=layout.root.name, block_position=1)
    assert isinstance(page_result, ErrorResult)
    assert page_result.code == CLOSED_SESSION  # type: ignore[comparison-overlap]
