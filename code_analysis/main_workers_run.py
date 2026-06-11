"""
Start workers directly and start worker monitoring (before server loop).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from code_analysis.core.constants import DEFAULT_WORKER_MONITOR_INTERVAL
from code_analysis.core.config_state import is_config_valid
from code_analysis.main_workers import (
    startup_database_driver,
    startup_file_watcher_worker,
    startup_indexing_worker,
    startup_vectorization_worker,
)


def run_workers_directly_and_start_monitoring(worker_manager: Any) -> None:
    """Start database driver and all workers synchronously, then start monitoring.

    Call ``init_queue_manager_before_workers`` in ``main()`` before this function
    when ``queue_manager.enabled`` is true (queuemgr is an external package).
    """
    logger = logging.getLogger(__name__)
    logger.info("🚀 Starting workers directly before server start...")
    print("🚀 Starting workers directly before server start...", flush=True)

    if not is_config_valid():
        logger.error(
            "Skipping worker startup: configuration is invalid "
            "(fix config.json; only help and health are available)"
        )
        print(
            "⚠️  Workers not started: configuration is invalid. "
            "Fix config.json and restart, or wait for file watcher reload after fix.",
            flush=True,
        )
        try:
            worker_manager.start_monitoring(interval=DEFAULT_WORKER_MONITOR_INTERVAL)
            logger.info("✅ Worker monitoring started (after workers)")
        except Exception as e:
            logger.error(f"❌ Failed to start worker monitoring: {e}", exc_info=True)
        return

    try:
        try:
            logger.info("🚀 Starting database driver...")
            startup_database_driver()
            logger.info("✅ Database driver started successfully")
        except Exception as e:
            logger.error(
                f"❌ Failed to start database driver: {e}",
                exc_info=True,
            )
            print(
                f"❌ Failed to start database driver: {e}",
                flush=True,
                file=sys.stderr,
            )

        logger.info(
            "🔍 Starting other workers (indexing, vectorization, file_watcher) synchronously"
        )

        try:
            logger.info("🚀 Starting indexing worker...")
            startup_indexing_worker()
            logger.info("✅ Indexing worker started successfully")
        except Exception as e:
            logger.error(
                f"❌ Failed to start indexing worker: {e}",
                exc_info=True,
            )
            print(
                f"❌ Failed to start indexing worker: {e}",
                flush=True,
                file=sys.stderr,
            )

        try:
            logger.info("🚀 Starting vectorization worker...")
            startup_vectorization_worker()
            logger.info("✅ Vectorization worker started successfully")
        except Exception as e:
            logger.error(
                f"❌ Failed to start vectorization worker: {e}",
                exc_info=True,
            )
            print(
                f"❌ Failed to start vectorization worker: {e}",
                flush=True,
                file=sys.stderr,
            )

        try:
            logger.info("🚀 Starting file watcher worker...")
            if startup_file_watcher_worker():
                logger.info("✅ File watcher worker started successfully")
            else:
                logger.warning(
                    "⚠️  File watcher worker was not started (disabled, missing config, or already running)"
                )
        except Exception as e:
            logger.error(
                f"❌ Failed to start file watcher worker: {e}",
                exc_info=True,
            )
            print(
                f"❌ Failed to start file watcher worker: {e}",
                flush=True,
                file=sys.stderr,
            )

        logger.info("✅ All workers startup completed")
        print(
            "✅ Database driver and all workers started",
            flush=True,
        )
    except Exception as e:
        logger.error(f"❌ Failed to start workers: {e}", exc_info=True)
        print(f"❌ Failed to start workers: {e}", flush=True, file=sys.stderr)

    try:
        worker_manager.start_monitoring(interval=DEFAULT_WORKER_MONITOR_INTERVAL)
        logger.info("✅ Worker monitoring started (after workers)")
    except Exception as e:
        logger.error(f"❌ Failed to start worker monitoring: {e}", exc_info=True)
