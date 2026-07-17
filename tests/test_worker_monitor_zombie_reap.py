"""
Tests for the zombie-child reap step in WorkerMonitor._check_and_restart_workers.

Before falling back to the psutil-based liveness check, the monitor now makes a
best-effort ``os.waitpid(pid, os.WNOHANG)`` call to reap an already-dead child
process (avoiding zombie accumulation). Any failure there (not our child,
already reaped, no children) must fall through to the existing psutil check
unchanged.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import errno
import logging
import os
import time
from typing import Any, Callable, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.worker_monitor import WorkerMonitor


class _FakeRegistry:
    """Minimal registry double exposing one worker with a live PID, no process handle."""

    def __init__(self, pid: int) -> None:
        """Initialize the instance."""
        self._pid = pid

    def get_workers(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return one worker_type with a single worker_info dict."""
        return {
            "vectorization": [
                {
                    "pid": self._pid,
                    "process": None,
                    "name": "vectorization-0",
                    "restart_func": None,
                    "restart_args": (),
                    "restart_kwargs": {},
                    # Recent registration -> grace period keeps the test from
                    # needing a working unregister/restart path.
                    "registered_at": time.time(),
                }
            ]
        }


def _make_monitor(pid: int) -> WorkerMonitor:
    """Build a WorkerMonitor wired to a minimal fake registry."""
    unregister_cb: Callable = MagicMock()
    register_cb: Callable = MagicMock()
    return WorkerMonitor(_FakeRegistry(pid), unregister_cb, register_cb)


def test_waitpid_reaps_and_logs_debug_then_falls_through_to_psutil(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A successful reap logs a debug line and does not prevent the psutil check."""
    caplog.set_level(logging.DEBUG, logger="code_analysis.core.worker_monitor")
    pid = 424242

    monitor = _make_monitor(pid)

    fake_proc = MagicMock()
    fake_proc.is_running.return_value = True

    with (
        patch("os.waitpid", return_value=(pid, 0)) as mock_waitpid,
        patch("psutil.Process", return_value=fake_proc) as mock_psutil_process,
    ):
        monitor._check_and_restart_workers()

    mock_waitpid.assert_called_once_with(pid, os.WNOHANG)
    mock_psutil_process.assert_called_once_with(pid)
    assert "Reaped zombie child process" in caplog.text
    assert str(pid) in caplog.text


def test_waitpid_child_process_error_falls_through_without_raising() -> None:
    """ChildProcessError (not our child / already reaped) falls through to psutil."""
    pid = 424243
    monitor = _make_monitor(pid)

    fake_proc = MagicMock()
    fake_proc.is_running.return_value = True

    with (
        patch("os.waitpid", side_effect=ChildProcessError("no such child")),
        patch("psutil.Process", return_value=fake_proc) as mock_psutil_process,
    ):
        monitor._check_and_restart_workers()

    mock_psutil_process.assert_called_once_with(pid)


def test_waitpid_oserror_echild_falls_through_without_error_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """OSError with errno.ECHILD falls through to psutil with no error-level log."""
    caplog.set_level(logging.DEBUG, logger="code_analysis.core.worker_monitor")
    pid = 424244
    monitor = _make_monitor(pid)

    fake_proc = MagicMock()
    fake_proc.is_running.return_value = True
    oserror = OSError(errno.ECHILD, "No child processes")

    with (
        patch("os.waitpid", side_effect=oserror),
        patch("psutil.Process", return_value=fake_proc) as mock_psutil_process,
    ):
        monitor._check_and_restart_workers()

    mock_psutil_process.assert_called_once_with(pid)
    assert not any(rec.levelno >= logging.ERROR for rec in caplog.records)
