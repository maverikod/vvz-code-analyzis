"""Tests for search inline timeout and auto-queue behavior."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks
from mcp_proxy_adapter.commands.result import SuccessResult
from mcp_proxy_adapter.integrations.queuemgr_integration import (
    QueueJobStatus,
    get_global_queue_manager,
    init_global_queue_manager,
    shutdown_global_queue_manager,
)

import code_analysis.hooks  # noqa: F401
from code_analysis.commands.fs_grep_budget import GREP_HARD_TIMEOUT
from code_analysis.commands.fs_grep_command import FsGrepCommand
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.search_mcp_command import SearchMCPCommand
from code_analysis.core.search_inline_execution import (
    cancel_pending_enqueue_start_tasks,
)
from code_analysis.core.search_timeouts import (
    EXECUTION_MODE_QUEUED,
    INTERNAL_EXECUTION_MODE_KEY,
    SEARCH_INLINE_TIMEOUT_SECONDS,
)


async def _drain_queue_jobs_before_shutdown() -> None:
    """Stop auto-queued jobs and pending start tasks so pytest loop teardown is clean."""
    await cancel_pending_enqueue_start_tasks()
    try:
        queue_manager = await get_global_queue_manager()
    except Exception:
        return
    active_statuses = {QueueJobStatus.PENDING, QueueJobStatus.RUNNING}
    try:
        jobs = await queue_manager.list_jobs()
    except Exception:
        return
    for job in jobs:
        if job.status in active_statuses:
            try:
                await queue_manager.stop_job(job.job_id)
            except Exception:
                pass
    await cancel_pending_enqueue_start_tasks()


@pytest_asyncio.fixture
async def queue_manager():
    """Return queue manager."""
    hooks.execute_custom_commands_hooks(registry)
    await shutdown_global_queue_manager()
    await init_global_queue_manager(
        in_memory=True,
        max_concurrent_jobs=2,
        completed_job_retention_seconds=3600,
    )
    try:
        yield
    finally:
        await _drain_queue_jobs_before_shutdown()
        await shutdown_global_queue_manager()


@pytest.mark.asyncio
async def test_inline_fast_search_returns_result(tmp_path) -> None:
    """Verify test inline fast search returns result."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "hit.txt").write_text("needle here\n", encoding="utf-8")

    with patch.object(
        FsGrepCommand, "_resolve_project_root", return_value=project_root
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000001",
            pattern="needle",
            fast_text_only=True,
            enrich_blocks=False,
        )

    assert isinstance(result, SuccessResult)
    assert result.data is not None
    assert result.data.get("queued") is False
    assert result.data.get("job_id") is None
    assert result.data.get("match_count") == 1


@pytest.mark.asyncio
async def test_inline_slow_search_auto_queues(tmp_path, queue_manager) -> None:
    """Verify test inline slow search auto queues."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "slow.txt").write_text("needle\n", encoding="utf-8")

    def _slow_sync(*_args: object, **_kwargs: object) -> SuccessResult:
        """Return slow sync."""
        time.sleep(SEARCH_INLINE_TIMEOUT_SECONDS + 2)
        return SuccessResult(data={"matches": [], "match_count": 0, "files_scanned": 0})

    with (
        patch.object(FsGrepCommand, "_resolve_project_root", return_value=project_root),
        patch.object(FsGrepCommand, "_execute_sync", side_effect=_slow_sync),
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000002",
            pattern="needle",
            inline_timeout_seconds=0.2,
        )

    assert isinstance(result, SuccessResult)
    assert result.data is not None
    assert result.data.get("queued") is True
    assert result.data.get("job_id")
    assert result.data.get("status") == "pending"


@pytest.mark.asyncio
async def test_queued_job_does_not_requeue(tmp_path, queue_manager) -> None:
    """Verify test queued job does not requeue."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.txt").write_text("needle\n", encoding="utf-8")

    enqueue_mock = AsyncMock(
        return_value=SuccessResult(data={"queued": True, "job_id": "should-not-run"})
    )

    with (
        patch.object(FsGrepCommand, "_resolve_project_root", return_value=project_root),
        patch(
            "code_analysis.core.search_inline_execution.enqueue_search_command",
            enqueue_mock,
        ),
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000003",
            pattern="needle",
            context={INTERNAL_EXECUTION_MODE_KEY: EXECUTION_MODE_QUEUED},
        )

    enqueue_mock.assert_not_called()
    assert isinstance(result, SuccessResult)
    assert result.data.get("queued") is False


@pytest.mark.asyncio
async def test_queued_job_hard_timeout(tmp_path) -> None:
    """Verify test queued job hard timeout."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "slow.txt").write_text("needle\n", encoding="utf-8")

    def _slow_sync(*_args: object, **_kwargs: object) -> SuccessResult:
        """Return slow sync."""
        time.sleep(3)
        return SuccessResult(data={"matches": [], "match_count": 0, "files_scanned": 0})

    with (
        patch.object(FsGrepCommand, "_resolve_project_root", return_value=project_root),
        patch.object(FsGrepCommand, "_execute_sync", side_effect=_slow_sync),
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000004",
            pattern="needle",
            hard_timeout_seconds=1,
            auto_queue_on_inline_timeout=False,
            context={INTERNAL_EXECUTION_MODE_KEY: EXECUTION_MODE_QUEUED},
        )

    assert result.code == GREP_HARD_TIMEOUT
    assert "hard timeout" in (result.message or "").lower()


@pytest.mark.asyncio
async def test_search_inline_wait_returns_handoff_when_phases_are_slow(
    tmp_path,
) -> None:
    """The live ``search`` command must not block on slow phases (reworked from the
    now-deleted ``ProjectCrossSearchCommand`` auto-queue coverage: that command's
    ``inline_timeout_seconds`` -> auto-queue behavior is superseded by ``search``'s
    own background-thread + first-block-wait-then-handoff architecture - this test
    asserts the same underlying guarantee (a slow search never blocks the caller
    past its configured wait bound) against the live machinery that replaced it,
    see search_mcp_command.SearchMCPCommand / search_paginated_cross.run_paginated_cross)."""

    async def _slow_run_paginated_cross(**_kwargs: object) -> None:
        """Simulate a phase that runs far longer than first_block_wait_seconds."""
        await __import__("asyncio").sleep(SEARCH_INLINE_TIMEOUT_SECONDS + 2)

    with (
        patch.object(BaseMCPCommand, "_validate_project_id_exists", return_value=None),
        patch(
            "code_analysis.commands.search_mcp_command.run_paginated_cross",
            side_effect=_slow_run_paginated_cross,
        ),
    ):
        cmd = SearchMCPCommand()
        start = time.monotonic()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000005",
            query="xpath test",
            enable_semantic=False,
            enable_grep=False,
            first_block_wait_seconds=0.2,
        )
        elapsed = time.monotonic() - start

    assert isinstance(result, SuccessResult)
    assert elapsed < SEARCH_INLINE_TIMEOUT_SECONDS
    assert result.data is not None
    assert result.data.get("search_still_running") is True
    assert result.data.get("job_id")
