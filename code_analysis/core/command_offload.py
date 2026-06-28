"""
Command execution offload pool.

Goal: keep the main asyncio event loop (Hypercorn/FastAPI) free of command
bodies. Commands are ``async def execute(...)`` but their bodies do synchronous
blocking work (DB RPC round-trips, ``fcntl.flock``, ``subprocess.run``, LibCST
parsing). Running them inline on the single server loop freezes everything on it,
including the proxy heartbeat, which makes the proxy deregister the server.

This module provides a bounded pool of worker threads, each owning its own
persistent event loop. ``offload_command_run`` relocates a command's execution
onto a worker thread and bridges the result back to the main loop via
``asyncio.wrap_future`` — so the main loop only schedules a callback and stays
responsive while the command runs in parallel.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import logging
import os
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_pool: Optional["_OffloadPool"] = None

# Configuration (set via configure_offload(); otherwise resolved from env/defaults).
_enabled_override: Optional[bool] = None
_max_workers_override: Optional[int] = None


class _OffloadPool:
    """Bounded thread pool where each worker thread owns a persistent loop."""

    def __init__(self, max_workers: int) -> None:
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="cmd-worker"
        )
        self._tls = threading.local()
        self.max_workers = max_workers

    def _thread_loop(self) -> asyncio.AbstractEventLoop:
        """Return (creating once) this worker thread's own event loop."""
        loop = getattr(self._tls, "loop", None)
        if loop is None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._tls.loop = loop
        return loop

    def submit(self, fn: Callable[[], Any]) -> "concurrent.futures.Future[Any]":
        return self._executor.submit(fn)

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


def configure_offload(
    *, enabled: Optional[bool] = None, max_workers: Optional[int] = None
) -> None:
    """Override offload settings (call once at startup from server config)."""
    global _enabled_override, _max_workers_override
    if enabled is not None:
        _enabled_override = bool(enabled)
    if max_workers is not None and int(max_workers) > 0:
        _max_workers_override = int(max_workers)


def offload_enabled() -> bool:
    """Return whether command bodies should run on the worker pool (default on)."""
    if _enabled_override is not None:
        return _enabled_override
    env = os.environ.get("CODE_ANALYSIS_COMMAND_OFFLOAD")
    if env is not None:
        return env.strip().lower() not in ("0", "false", "no", "off")
    return True


def _resolve_max_workers() -> int:
    if _max_workers_override:
        return _max_workers_override
    env = os.environ.get("CODE_ANALYSIS_COMMAND_OFFLOAD_MAX_WORKERS")
    if env and env.strip().isdigit() and int(env) > 0:
        return int(env)
    return min(32, (os.cpu_count() or 1) * 4)


def _get_pool() -> _OffloadPool:
    global _pool
    with _lock:
        if _pool is None:
            _pool = _OffloadPool(_resolve_max_workers())
            logger.info(
                "Command offload pool started (max_workers=%d)", _pool.max_workers
            )
        return _pool


def warm_up() -> None:
    """Eagerly create the pool so the first request is not slowed by startup."""
    if offload_enabled():
        _get_pool()


def shutdown(wait: bool = True) -> None:
    """Drain and stop the pool (best-effort; idempotent)."""
    global _pool
    with _lock:
        pool = _pool
        _pool = None
    if pool is not None:
        try:
            pool.shutdown(wait=wait)
        except Exception:  # pragma: no cover - shutdown best-effort
            logger.debug("Command offload pool shutdown raised", exc_info=True)


async def offload_command_run(
    parent_run: Callable[..., Any], kwargs: dict
) -> Any:
    """Run ``parent_run(**kwargs)`` on a worker thread's loop; await the result.

    ``parent_run`` is the inherited adapter ``Command.run`` bound classmethod. It
    already validates params and converts every exception into a result object,
    so the worker coroutine returns a result rather than raising. The main loop
    only awaits the bridged future and stays free for other requests/heartbeats.
    """
    pool = _get_pool()
    ctx = contextvars.copy_context()

    def worker() -> Any:
        loop = pool._thread_loop()
        coro = parent_run(**kwargs)
        # Run under a copy of the caller's context so request-scoped contextvars
        # (e.g. request-id logging) propagate into the worker.
        return ctx.run(loop.run_until_complete, coro)

    future = pool.submit(worker)
    # wrap_future schedules a main-loop callback on completion; if the caller is
    # cancelled (wait_for timeout) CancelledError propagates here while the worker
    # thread finishes and its result is discarded (threads can't be force-killed).
    return await asyncio.wrap_future(future)
