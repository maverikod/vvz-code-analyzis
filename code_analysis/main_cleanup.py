"""
Register atexit and signal handlers for worker cleanup on exit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import atexit
import signal
import sys
import threading
from typing import Any

from code_analysis.core.constants import DEFAULT_SHUTDOWN_GRACE_TIMEOUT


def register_cleanup_handlers(
    worker_manager: Any,
    app_config: dict[str, Any],
    main_logger: Any,
) -> None:
    """Register cleanup_workers on atexit and SIGTERM/SIGINT."""
    cleanup_lock = threading.Lock()
    cleanup_started = False

    def cleanup_workers() -> None:
        nonlocal cleanup_started
        with cleanup_lock:
            if cleanup_started:
                main_logger.info(
                    "cleanup_workers() already executed for this shutdown; skipping duplicate invocation"
                )
                return
            cleanup_started = True
        try:
            main_logger.info(
                "cleanup_workers() invoked (shutdown path); stopping workers"
            )
            main_logger.info("🛑 Server shutdown: stopping all workers")
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
                main_logger.warning(
                    f"⚠️  Some workers failed to stop: {shutdown_result.get('message')}"
                )
            else:
                main_logger.info(
                    f"✅ All workers stopped: {shutdown_result.get('message')}"
                )
        except Exception as e:
            main_logger.error(f"❌ Error stopping workers: {e}", exc_info=True)

    def signal_handler(signum: int, frame: object) -> None:
        main_logger.info(
            "Received signal %s, stopping all workers then exiting",
            signum,
        )
        cleanup_workers()
        main_logger.info("Signal handler: calling sys.exit(0) after cleanup")
        sys.exit(0)

    atexit.register(cleanup_workers)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
