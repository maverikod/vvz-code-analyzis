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

import logging
import sys
import threading
from typing import Any, List, Optional

from code_analysis.commands.base_mcp_command import (
    BaseMCPCommand,
    _get_socket_path_from_db_path,
)
from code_analysis.commands.base_mcp_command_open_db import (
    open_database_from_config_impl,
)
from code_analysis.core.constants import DEFAULT_SHUTDOWN_GRACE_TIMEOUT
from code_analysis.core.runtime_lock_sessions import register_runtime_session
from code_analysis.core.shared_database import (
    close_shared_database,
    set_shared_database,
)
from code_analysis.core.cst_tree.tree_builder import start_cst_tree_ttl_cleanup
from code_analysis.main_workers import (
    startup_database_driver,
    startup_file_watcher_worker,
    startup_indexing_worker,
    startup_vectorization_worker,
)


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

                try:
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
                except Exception as e:
                    logger.error(
                        "❌ [BACKGROUND] Failed to open shared database (integrity/connect/probe): %s",
                        e,
                        exc_info=True,
                    )
                    _db_open_error[0] = str(e)
                    _db_open_done.set()
                    return

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
            timeout_sec = 60.0
            if not _db_open_done.wait(timeout=timeout_sec):
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
        logger = logging.getLogger(__name__)
        print(
            "🛑 [SHUTDOWN EVENT] Server shutdown: stopping workers via shutdown event...",
            flush=True,
        )
        logger.info(
            "🛑 [SHUTDOWN EVENT] Server shutdown: stopping workers via shutdown event..."
        )

        try:
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
