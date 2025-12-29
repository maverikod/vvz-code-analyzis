"""
Base repair worker for database integrity restoration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
import signal
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class RepairWorker:
    """
    Worker for repairing database integrity.

    Responsibilities:
    - Restore file status based on actual file presence
    - Process files in batches
    - Handle graceful shutdown
    """

    def __init__(
        self,
        db_path: Path,
        project_id: str,
        root_dir: Path,
        version_dir: str,
        batch_size: int = 10,
        poll_interval: int = 30,
    ):
        """
        Initialize repair worker.

        Args:
            db_path: Path to database file
            project_id: Project ID
            root_dir: Project root directory
            version_dir: Version directory for deleted files
            batch_size: Number of files to process per batch (default: 10)
            poll_interval: Interval in seconds between repair cycles (default: 30)
        """
        self.db_path = db_path
        self.project_id = project_id
        self.root_dir = root_dir
        self.version_dir = version_dir
        self.batch_size = batch_size
        self.poll_interval = poll_interval

        self._stop_event = multiprocessing.Event()
        self._pid = os.getpid()
        self._shutdown_requested = False

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self._shutdown_requested = True
        self.stop()

    def stop(self) -> None:
        """Stop the worker gracefully."""
        self._stop_event.set()
        logger.info("Repair worker stop requested")

    async def run(self) -> Dict[str, Any]:
        """
        Main worker loop.

        Processes files in batches, checking and repairing database integrity.

        Returns:
            Dictionary with processing statistics
        """
        total_stats = {
            "files_processed": 0,
            "files_restored": 0,
            "files_marked_deleted": 0,
            "files_restored_from_cst": 0,
            "errors": 0,
            "cycles": 0,
        }

        logger.info(
            f"Starting repair worker for project {self.project_id}, "
            f"batch size: {self.batch_size}, "
            f"poll interval: {self.poll_interval}s"
        )

        try:
            from ..database import CodeDatabase, create_driver_config_for_worker

            driver_config = create_driver_config_for_worker(self.db_path)
            database = CodeDatabase(driver_config=driver_config)

            while not self._stop_event.is_set():
                try:
                    # Run repair cycle
                    cycle_stats = await self._repair_cycle(database)
                    total_stats["files_processed"] += cycle_stats.get(
                        "files_processed", 0
                    )
                    total_stats["files_restored"] += cycle_stats.get(
                        "files_restored", 0
                    )
                    total_stats["files_marked_deleted"] += cycle_stats.get(
                        "files_marked_deleted", 0
                    )
                    total_stats["files_restored_from_cst"] += cycle_stats.get(
                        "files_restored_from_cst", 0
                    )
                    total_stats["errors"] += cycle_stats.get("errors", 0)
                    total_stats["cycles"] += 1

                    from datetime import datetime

                    cycle_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    logger.info(
                        f"[CYCLE #{total_stats['cycles']}] {cycle_time} | "
                        f"processed: {cycle_stats.get('files_processed', 0)} | "
                        f"restored: {cycle_stats.get('files_restored', 0)} | "
                        f"marked_deleted: {cycle_stats.get('files_marked_deleted', 0)} | "
                        f"restored_from_cst: {cycle_stats.get('files_restored_from_cst', 0)} | "
                        f"errors: {cycle_stats.get('errors', 0)}"
                    )

                    # Wait for next cycle or stop if shutdown requested
                    if self._shutdown_requested:
                        logger.info("Shutdown requested, stopping worker")
                        break

                    # Wait for next poll interval
                    await asyncio.sleep(self.poll_interval)

                except asyncio.CancelledError:
                    logger.info("Repair worker cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in repair cycle: {e}", exc_info=True)
                    total_stats["errors"] += 1
                    # Wait a bit before retrying
                    await asyncio.sleep(5)

            database.close()
            logger.info("Repair worker stopped gracefully")

        except KeyboardInterrupt:
            logger.info("Repair worker interrupted")
        except Exception as e:
            logger.error(f"Repair worker error: {e}", exc_info=True)
            total_stats["errors"] += 1

        return total_stats

    async def _repair_cycle(self, database: Any) -> Dict[str, Any]:
        """
        Perform one repair cycle.

        Args:
            database: CodeDatabase instance

        Returns:
            Dictionary with cycle statistics
        """
        cycle_stats = {
            "files_processed": 0,
            "files_restored": 0,
            "files_marked_deleted": 0,
            "files_restored_from_cst": 0,
            "errors": 0,
        }

        try:
            from ...commands.file_management import RepairDatabaseCommand

            # Create repair command
            command = RepairDatabaseCommand(
                database=database,
                project_id=self.project_id,
                root_dir=self.root_dir,
                version_dir=self.version_dir,
                dry_run=False,
            )

            # Execute repair
            result = await command.execute()

            # Update statistics
            cycle_stats["files_processed"] = (
                len(result.get("files_in_project_restored", []))
                + len(result.get("files_in_versions_marked_deleted", []))
                + len(result.get("files_restored_from_cst", []))
            )
            cycle_stats["files_restored"] = len(
                result.get("files_in_project_restored", [])
            )
            cycle_stats["files_marked_deleted"] = len(
                result.get("files_in_versions_marked_deleted", [])
            )
            cycle_stats["files_restored_from_cst"] = len(
                result.get("files_restored_from_cst", [])
            )
            cycle_stats["errors"] = len(result.get("errors", []))

        except Exception as e:
            logger.error(f"Error in repair cycle: {e}", exc_info=True)
            cycle_stats["errors"] += 1

        return cycle_stats
