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
from code_analysis.main_workers import (
    startup_database_driver,
    startup_file_watcher_worker,
    startup_indexing_worker,
    startup_vectorization_worker,
)


def run_workers_directly_and_start_monitoring(worker_manager: Any) -> None:
    """Start database driver and all workers synchronously, then start monitoring."""
    logger = logging.getLogger(__name__)
    logger.info("🚀 Starting workers directly before server start...")
    print("🚀 Starting workers directly before server start...", flush=True)

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
            startup_file_watcher_worker()
            logger.info("✅ File watcher worker started successfully")
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
