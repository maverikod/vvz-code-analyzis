"""
Cooperative cancellation on the fs_grep hard-timeout path (bug 0c124699).

``asyncio.wait_for`` only cancels the *awaiting* Task; the real
``asyncio.to_thread`` worker keeps running (and its DB connection stays open)
until it notices ``cancel_event``. This covers the fix in
``FsGrepCommand._execute_grep``'s ``except asyncio.TimeoutError`` branch,
which must set ``cancel_event`` so a stub slow worker actually observes the
cancellation and stops instead of leaking the thread for the rest of its scan.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.fs_grep_budget import GREP_HARD_TIMEOUT
from code_analysis.commands.fs_grep_command import FsGrepCommand

_BASE_EXECUTE_GREP_KWARGS: dict = dict(
    project_id="00000000-0000-0000-0000-0000000000aa",
    pattern="needle",
    literal=True,
    case_sensitive=False,
    file_pattern=None,
    glob=None,
    max_matches=500,
    max_file_bytes=5 * 1024 * 1024,
    line_preview_len=None,
    scan_all=False,
    include_logs=False,
    indexed_only=False,
    skip_indexed_unchanged=True,
    source="disk",
    session_id=None,
    fast_text_only=False,
    enrich_blocks=True,
    enrich_max_results=50,
    ensure_persisted_tree=True,
    stable_ids_required=True,
    grep_sync_max_wall_seconds=None,
    show_venv=False,
    python_only=False,
    include_venv_ignore_exceptions=False,
    show_hidden=False,
    max_files_scanned=None,
    wall_time_budget_s=None,
    context={},
)


@pytest.mark.asyncio
async def test_hard_timeout_sets_cancel_event_for_worker_thread(monkeypatch) -> None:
    """Hard-timeout TimeoutError must set cancel_event; a stub slow worker
    thread must observe it and stop well before its own (long) budget."""
    cmd = FsGrepCommand()
    worker_saw_cancel = threading.Event()
    worker_finished_via_cancel = threading.Event()

    def _slow_execute_sync(*args):
        """Stand-in for FsGrepCommand._execute_sync: a slow scan loop that
        polls cancel_event exactly like FsGrepBudgetState.should_stop_scan
        does in the real implementation."""
        cancel_event = args[-2]
        started = time.monotonic()
        while time.monotonic() - started < 5.0:
            if cancel_event is not None and cancel_event.is_set():
                worker_saw_cancel.set()
                worker_finished_via_cancel.set()
                return ErrorResult(
                    message="stub worker stopped on cancel",
                    code="STUB_CANCELLED",
                    details={},
                )
            time.sleep(0.02)
        return SuccessResult(data={"success": True, "matches": [], "files_scanned": 0})

    # Instance attribute shadows the bound method; asyncio.to_thread calls it
    # with the same positional args _execute_grep already passes today.
    monkeypatch.setattr(cmd, "_execute_sync", _slow_execute_sync)

    result = await cmd._execute_grep(
        **_BASE_EXECUTE_GREP_KWARGS,
        hard_timeout_seconds=0.2,
        cancel_event=threading.Event(),
        on_match_batch=None,
    )

    assert isinstance(result, ErrorResult)
    assert result.code == GREP_HARD_TIMEOUT

    # Give the background thread a bounded window to notice the signal and
    # return - it must NOT need anywhere near its own 5s stub budget.
    deadline = time.monotonic() + 2.0
    while not worker_finished_via_cancel.is_set() and time.monotonic() < deadline:
        await asyncio.sleep(0.02)

    assert worker_saw_cancel.is_set(), (
        "worker thread never observed cancel_event - the hard-timeout path "
        "leaked the thread instead of signaling cooperative cancellation"
    )
