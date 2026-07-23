"""
Register FastAPI startup/shutdown events for workers.

At startup: after the database driver is started, open the long-lived DB connection
(integrity + connect + probe once), set it via set_shared_database(), then start
other workers. The server does not accept requests until set_shared_database() has
been called. At shutdown: close_shared_database() before stopping workers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from typing import Any, List, Optional

from code_analysis.commands.base_mcp_command import (
    BaseMCPCommand,
    _get_socket_path_from_db_path,
)
from code_analysis.commands.base_mcp_command_open_db import (
    open_database_from_config_impl,
)
from code_analysis.core.constants import DEFAULT_SHUTDOWN_GRACE_TIMEOUT
from code_analysis.core.retry_policy import RetryPolicy
from code_analysis.core.runtime_lock_sessions import register_runtime_session
from code_analysis.core.shared_database import (
    close_shared_database,
    set_shared_database,
)
from code_analysis.core.cst_tree.tree_builder import start_cst_tree_ttl_cleanup
from code_analysis.core import command_offload
from code_analysis.core.loop_liveness import loop_liveness_beat_loop
from code_analysis.main_workers import (
    startup_database_driver,
    startup_file_watcher_worker,
    startup_indexing_worker,
    startup_vectorization_worker,
)

# Strong references to long-lived background tasks. asyncio.create_task keeps only
# a weak reference, so without this the beat task can be garbage-collected and stop.
_background_tasks: set = set()

# Bug c5e8fb49 (boot race): bounded retry for the long-lived shared-DB bootstrap
# (open + probe + set_shared_database). Total worst-case sleep across 4 retries
# (5 attempts) is ~15.8s (1+2+4+8s plus jitter), well under the 60s
# ``_db_open_done.wait`` timeout below so a genuinely-down DB still degrades on
# the documented schedule rather than silently blocking the whole wait window.
_DB_OPEN_RETRY_POLICY = RetryPolicy(
    attempts=5,
    delay_seconds=1.0,
    backoff_multiplier=2.0,
    jitter_seconds=0.2,
)


def _bootstrap_with_retry(
    attempt_fn: Any,
    *,
    retry_policy: RetryPolicy,
    logger: logging.Logger,
    operation_name: str,
    sleep_fn: Any = time.sleep,
) -> Optional[BaseException]:
    """Run ``attempt_fn()`` with bounded retry; return the last exception, or None on success.

    Module-level and dependency-injected (``sleep_fn``) so the retry schedule is
    unit-testable without a real ``time.sleep`` — used for the shared-DB bootstrap
    (bug c5e8fb49) but kept generic (no closure over server-startup state).
    """
    max_attempts = retry_policy.attempts
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        try:
            attempt_fn()
            return None
        except Exception as e:
            last_exc = e
            if attempt >= max_attempts:
                break
            delay = retry_policy.delay_for_attempt(attempt)
            logger.warning(
                "[DB_RETRY] backend=postgres layer=bootstrap operation=%s "
                "attempt=%s/%s error=%s; retrying in %.2fs",
                operation_name,
                attempt,
                max_attempts,
                e,
                delay,
            )
            sleep_fn(delay)
    return last_exc


def _fail_loud_shared_database_bootstrap(
    exc: BaseException,
    logger: logging.Logger,
    *,
    max_attempts: int,
    exit_fn: Any = os._exit,
) -> None:
    """Force the process to exit non-zero after the shared-DB bootstrap retry is exhausted.

    Runs from a daemon thread (see ``thread.start()`` in
    ``start_workers_on_startup``): a bare ``raise`` here would only kill this
    thread — it would NOT stop the process, so nothing would trigger an s6
    restart, and the process would keep running with no shared DB and no
    further retry, serving every DB-dependent command a silent
    ``SharedDatabaseNotInitializedError`` forever. The shared DB is a hard boot
    requirement (``get_shared_database()`` backs virtually every command), so
    once the bounded retry is exhausted the only correct move is to make the
    whole process exit non-zero: ``os._exit(1)`` is the same fail-fast idiom
    ``main()`` already uses on its own shutdown path (see ``main.py``'s
    ``finally: ... os._exit(exit_code)``), chosen over ``sys.exit()``/``raise``
    because both of those only unwind the current thread's stack, not the
    interpreter. s6 supervises this process as the 40-casmgr longrun and
    restarts it on exit (``docker/casmgr/s6/s6-rc.d/40-casmgr/run``). NOTE:
    unlike 20-postgres, 40-casmgr has no ``finish`` script and no restart
    backoff/throttle configured, so a persistently-down DB will make this
    process flap-restart at s6's default (immediate) respawn rate — a
    pre-existing s6 configuration gap, documented here; s6 config changes are
    out of scope for this fix. ``exit_fn`` is injectable so tests can assert
    the fail-loud path fires without killing the test process.
    """
    logger.critical(
        "❌ [BACKGROUND] Failed to open shared database (integrity/connect/probe) "
        "after %s attempts: %s",
        max_attempts,
        exc,
        exc_info=exc,
    )
    exit_fn(1)


def register_startup_shutdown_events(
    app: Any,
    app_config: dict[str, Any],
    worker_manager: Any,
) -> None:
    """Register @app.on_event('startup') and @app.on_event('shutdown') for workers."""

    # Event set when long-lived DB open has finished (success or failure).
    # Main thread waits so the server does not accept requests before set_shared_database().
    _db_open_done: threading.Event = threading.Event()
    _db_open_error: List[Optional[str]] = [None]

    @app.on_event("startup")
    async def start_workers_on_startup() -> None:
        """Return start workers on startup."""
        logger = logging.getLogger(__name__)
        print(
            "🚀 [STARTUP EVENT] Server startup: initializing workers via startup event...",
            flush=True,
        )
        logger.info(
            "🚀 [STARTUP EVENT] Server startup: initializing workers via startup event..."
        )

        try:

            def _open_shared_database_once() -> None:
                """Open long-lived DB (integrity + connect + probe once), set shared holder.

                On any failure: log and set _db_open_error so startup aborts.
                Driver is already started; connect() in open_database_from_config_impl
                has its own retries (startup_connect_timeout).
                """
                try:
                    logger.info("🚀 [BACKGROUND] Starting database driver...")
                    startup_database_driver()
                    logger.info("✅ [BACKGROUND] Database driver started")
                except Exception as e:
                    logger.error(
                        f"❌ [BACKGROUND] Failed to start database driver: {e}",
                        exc_info=True,
                    )
                    _db_open_error[0] = str(e)
                    _db_open_done.set()
                    return

                def _open_and_set_shared_database_once() -> None:
                    """One bootstrap attempt: open long-lived DB, set shared holder."""
                    logger.info(
                        "🚀 [BACKGROUND] Opening long-lived database connection..."
                    )
                    db = open_database_from_config_impl(
                        BaseMCPCommand._resolve_config_path,
                        _get_socket_path_from_db_path,
                        auto_analyze=False,
                    )
                    set_shared_database(db)
                    listener_url = None
                    try:
                        host = str(app_config.get("host") or "").strip()
                        port = app_config.get("port")
                        if host and port:
                            listener_url = f"http://{host}:{int(port)}"
                    except Exception:
                        listener_url = None
                    register_runtime_session(
                        db,
                        role="daemon",
                        listener_url=listener_url,
                    )
                    logger.info(
                        "✅ [BACKGROUND] Long-lived database connection set (shared)"
                    )

                last_exc = _bootstrap_with_retry(
                    _open_and_set_shared_database_once,
                    retry_policy=_DB_OPEN_RETRY_POLICY,
                    logger=logger,
                    operation_name="open_shared_database",
                )

                if last_exc is not None:
                    _db_open_error[0] = str(last_exc)
                    _db_open_done.set()
                    # See _fail_loud_shared_database_bootstrap docstring for why a
                    # hard process exit (not raise/sys.exit) is required here: this
                    # runs on a daemon thread (thread.start() below).
                    _fail_loud_shared_database_bootstrap(
                        last_exc,
                        logger,
                        max_attempts=_DB_OPEN_RETRY_POLICY.attempts,
                    )
                    return  # pragma: no cover - unreachable in production (exit_fn exits)

                _db_open_done.set()

                try:
                    logger.info("🚀 [BACKGROUND] Starting indexing worker...")
                    startup_indexing_worker()
                    logger.info("✅ [BACKGROUND] Indexing worker started")
                except Exception as e:
                    logger.error(
                        f"❌ [BACKGROUND] Failed to start indexing worker: {e}",
                        exc_info=True,
                    )

                try:
                    logger.info("🚀 [BACKGROUND] Starting vectorization worker...")
                    startup_vectorization_worker()
                    logger.info("✅ [BACKGROUND] Vectorization worker started")
                except Exception as e:
                    logger.error(
                        f"❌ [BACKGROUND] Failed to start vectorization worker: {e}",
                        exc_info=True,
                    )

                try:
                    logger.info("🚀 [BACKGROUND] Starting file watcher worker...")
                    startup_file_watcher_worker()
                    logger.info("✅ [BACKGROUND] File watcher worker started")
                except Exception as e:
                    logger.error(
                        f"❌ [BACKGROUND] Failed to start file watcher worker: {e}",
                        exc_info=True,
                    )

            thread = threading.Thread(target=_open_shared_database_once, daemon=True)
            thread.start()

            # Wait for background DB open; on failure the HTTP server still runs (degraded).
            # Offload the blocking Event.wait to a thread so the startup coroutine
            # does not freeze the main event loop (and its heartbeat) for up to 60s.
            timeout_sec = 60.0
            if not await asyncio.to_thread(_db_open_done.wait, timeout_sec):
                logger.warning(
                    "⚠️ [STARTUP] Timed out waiting for shared database (%.1fs); "
                    "HTTP server stays up (degraded).",
                    timeout_sec,
                )
                print(
                    "⚠️ [STARTUP EVENT] Timed out waiting for database; "
                    "server running degraded.",
                    flush=True,
                )
            elif _db_open_error[0] is not None:
                logger.warning(
                    "⚠️ [STARTUP] Shared database open failed: %s; "
                    "HTTP server stays up (degraded).",
                    _db_open_error[0],
                )
                print(
                    f"⚠️ [STARTUP EVENT] Database unavailable: {_db_open_error[0]}; "
                    "server running degraded.",
                    flush=True,
                )
            else:
                print(
                    "✅ [STARTUP EVENT] Workers startup completed (shared DB set)",
                    flush=True,
                )
                logger.info(
                    "✅ [STARTUP EVENT] Workers startup completed (shared DB set)"
                )

            start_cst_tree_ttl_cleanup()
            # Heartbeat liveness beacon: the watchdog thread reads this to tell
            # "loop busy" from "loop wedged" (see proxy_heartbeat_watchdog).
            # Keep a strong reference so the task is not garbage-collected.
            _beat_task = asyncio.create_task(loop_liveness_beat_loop())
            _background_tasks.add(_beat_task)
            _beat_task.add_done_callback(_background_tasks.discard)
            # Apply optional offload config, then pre-create the worker pool so the
            # first request is not slowed by lazy startup of the worker threads/loops.
            try:
                off_cfg = (
                    app_config.get("command_offload")
                    if isinstance(app_config, dict)
                    else None
                )
                if isinstance(off_cfg, dict):
                    command_offload.configure_offload(
                        enabled=off_cfg.get("enabled"),
                        max_workers=off_cfg.get("max_workers"),
                    )
                command_offload.warm_up()
            except Exception as e:  # pragma: no cover - non-fatal
                logger.warning("Command offload warm-up failed: %s", e)
        except Exception as e:
            print(
                f"❌ [STARTUP EVENT] Failed to start workers: {e}",
                flush=True,
                file=sys.stderr,
            )
            logger.error(
                f"❌ [STARTUP EVENT] Failed to start workers: {e}", exc_info=True
            )
            raise

    @app.on_event("shutdown")
    async def stop_workers_on_shutdown() -> None:
        """Return stop workers on shutdown."""
        logger = logging.getLogger(__name__)
        print(
            "🛑 [SHUTDOWN EVENT] Server shutdown: stopping workers via shutdown event...",
            flush=True,
        )
        logger.info(
            "🛑 [SHUTDOWN EVENT] Server shutdown: stopping workers via shutdown event..."
        )

        try:
            try:
                command_offload.shutdown(wait=True)
                logger.info("✅ Command offload pool stopped")
            except Exception as e:  # pragma: no cover - best-effort
                logger.warning("Command offload pool shutdown failed: %s", e)

            close_shared_database()
            logger.info("✅ Shared database connection closed")

            shutdown_cfg = (
                app_config.get("process_management")
                or app_config.get("server_manager")
                or {}
            )
            shutdown_timeout = DEFAULT_SHUTDOWN_GRACE_TIMEOUT
            if isinstance(shutdown_cfg, dict):
                try:
                    val = shutdown_cfg.get("shutdown_grace_seconds")
                    if isinstance(val, (int, float)) and float(val) > 0:
                        shutdown_timeout = float(val)
                except Exception:
                    shutdown_timeout = DEFAULT_SHUTDOWN_GRACE_TIMEOUT

            shutdown_result = worker_manager.stop_all_workers(timeout=shutdown_timeout)
            if shutdown_result.get("total_failed", 0) > 0:
                logger.warning(
                    f"⚠️  Some workers failed to stop: {shutdown_result.get('message')}"
                )
            else:
                logger.info(f"✅ All workers stopped: {shutdown_result.get('message')}")
        except Exception as e:
            logger.error(f"❌ Error stopping workers: {e}", exc_info=True)
