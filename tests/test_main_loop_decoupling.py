"""
Regression tests for main event-loop decoupling.

Covers the four changes that keep the single server event loop free of blocking
work so the proxy heartbeat never starves:

1. Command offload pool runs command bodies off the main loop, in parallel.
2. Advisory ``file_lock`` no longer blocks forever (bounded default timeout).
3. CST tree registry is safe under concurrent worker-thread access.
4. The loop-liveness / watchdog stall detector fires only on a real stall.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import math
import threading
import time
from pathlib import Path

import pytest

from code_analysis.core import command_offload
from code_analysis.core import file_lock
from code_analysis.core.file_lock import FileLockTimeoutError


def test_offload_keeps_main_loop_free_and_parallel() -> None:
    """A blocking command body must not freeze the main loop, and N run in parallel."""

    async def blocking_run(**kwargs):  # stands in for adapter Command.run
        time.sleep(0.4)
        return ("worker", threading.current_thread().name, kwargs)

    async def main() -> None:
        ticks = 0

        async def ticker() -> None:
            nonlocal ticks
            for _ in range(8):
                await asyncio.sleep(0.05)
                ticks += 1

        t = asyncio.create_task(ticker())
        res = await command_offload.offload_command_run(blocking_run, {"a": 1})
        await t

        assert res[0] == "worker"
        assert res[1].startswith("cmd-worker")  # ran on the pool, not the main loop
        # The main loop kept ticking while the worker blocked.
        assert ticks >= 6

        # Three 0.4s blocking commands should overlap (~0.4s, not ~1.2s).
        start = time.monotonic()
        await asyncio.gather(
            *[command_offload.offload_command_run(blocking_run, {"i": i}) for i in range(3)]
        )
        assert time.monotonic() - start < 0.9

    try:
        asyncio.run(main())
    finally:
        command_offload.shutdown()


def test_file_lock_default_timeout_is_bounded(tmp_path: Path) -> None:
    """A second exclusive acquire times out instead of blocking forever."""
    target = tmp_path / "data.txt"
    target.write_text("x", encoding="utf-8")

    # Hold an exclusive lock in a background thread.
    holding = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with file_lock.file_lock(target, mode="full"):
            holding.set()
            release.wait(5)

    th = threading.Thread(target=hold, daemon=True)
    th.start()
    assert holding.wait(5)

    # Second acquirer with a short timeout must raise, not hang.
    start = time.monotonic()
    with pytest.raises(FileLockTimeoutError):
        with file_lock.file_lock(target, mode="full", timeout=0.5):
            pass
    elapsed = time.monotonic() - start
    assert 0.4 <= elapsed < 3.0

    release.set()
    th.join(timeout=5)


def test_file_lock_infinite_timeout_opt_in(tmp_path: Path) -> None:
    """math.inf still means 'wait forever' (acquired immediately when free)."""
    target = tmp_path / "free.txt"
    target.write_text("x", encoding="utf-8")
    with file_lock.file_lock(target, mode="full", timeout=math.inf):
        pass  # uncontended → returns immediately


def test_cst_tree_registry_concurrent_access() -> None:
    """Concurrent create/get/remove on the CST tree registry must not corrupt it."""
    from code_analysis.core.cst_tree import tree_builder

    errors: list[Exception] = []

    def worker(idx: int) -> None:
        try:
            for n in range(50):
                tree = tree_builder.create_tree_from_code(
                    f"/virtual/mod_{idx}_{n}.py",
                    f"x = {n}\n",
                    register_in_memory=True,
                )
                assert tree_builder.get_tree(tree.tree_id) is not None
                tree_builder.remove_tree(tree.tree_id)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"concurrent CST registry access raised: {errors}"


def test_watchdog_detects_stall_but_not_busy_or_boot(monkeypatch) -> None:
    """Stall detector fires on a real stall, not while busy and not during boot."""
    from code_analysis.core import loop_liveness, proxy_heartbeat_watchdog as wd

    monkeypatch.setattr(wd, "STALL_LIMIT_SECONDS", 0.2)
    monkeypatch.setattr(wd, "LIVENESS_CHECK_INTERVAL", 0.05)

    import logging

    handler_records: list[str] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            handler_records.append(record.getMessage())

    lh = _ListHandler()
    wd.logger.addHandler(lh)
    wd.logger.setLevel(logging.DEBUG)

    # Reset liveness module state to "never beaten".
    monkeypatch.setattr(loop_liveness, "_ever_beat", False, raising=False)

    stop = threading.Event()
    thread = wd.start_proxy_heartbeat_watchdog({}, Path("config.json").resolve(), stop)
    try:
        # Boot window (never beaten): no stall.
        time.sleep(0.4)
        assert not any("STALLED" in m for m in handler_records)

        # Busy loop: beat steadily → no stall.
        for _ in range(8):
            loop_liveness.beat()
            time.sleep(0.05)
        assert not any("STALLED" in m for m in handler_records)

        # Real stall: stop beating beyond the limit.
        time.sleep(0.5)
        assert any("STALLED" in m for m in handler_records)
    finally:
        stop.set()
        thread.join(timeout=2)
        wd.logger.removeHandler(lh)
