"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .lock_manager import LockManager
from .processor import FileChangeProcessor
from .scanner import scan_directory

logger = logging.getLogger(__name__)


class FileWatcherWorker:
    """
    Worker for tracking file changes in configured directories.

    Responsibilities:
    - Scan root watch_dirs from config (recursively)
    - Compare file mtime with DB last_modified
    - Mark changed files for processing
    - Handle lock files in service state directory (locks_dir)

    Note: Lock files are created in service state directory (locks_dir),
    not in watched directories. This implements Step 4 of the refactor plan.
    """

    def __init__(
        self,
        db_path: Path,
        watch_dirs: List[Path],
        locks_dir: Path,
        scan_interval: int = 60,
        version_dir: Optional[str] = None,
        ignore_patterns: Optional[List[str]] = None,
    ):
        """
        Initialize file watcher worker.

        Projects are discovered automatically within each watch_dir by finding
        projectid files. Multiple projects can exist in one watch_dir.

        Args:
            db_path: Path to database file
            watch_dirs: List of root directories to watch (from config).
            locks_dir: Service state directory for lock files (from StoragePaths).
            scan_interval: Interval in seconds between scans (default: 60)
            version_dir: Version directory for deleted files (optional)
            ignore_patterns: List of glob patterns to ignore (from config, optional)
        """
        self.db_path = db_path
        self.watch_dirs = [Path(d) for d in watch_dirs]
        self.scan_interval = scan_interval
        self.version_dir = version_dir
        self.ignore_patterns = ignore_patterns or []

        # Use first watch_dir as lock key
        lock_key = str(self.watch_dirs[0].resolve()) if self.watch_dirs else "default"
        self.lock_manager = LockManager(locks_dir, lock_key)
        self._stop_event = multiprocessing.Event()
        self._pid = os.getpid()

    def stop(self) -> None:
        """Stop the worker."""
        self._stop_event.set()

    async def run(self) -> Dict[str, Any]:
        """
        Main worker loop.

        Scans configured directories at specified intervals.

        Returns:
            Dictionary with processing statistics
        """
        total_stats = {
            "scanned_dirs": 0,
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
            "cycles": 0,
        }

        logger.info(
            f"Starting file watcher worker, "
            f"scan interval: {self.scan_interval}s, "
            f"watching {len(self.watch_dirs)} directories"
        )

        try:
            from ..database import CodeDatabase, create_driver_config_for_worker

            driver_config = create_driver_config_for_worker(self.db_path)
            database = CodeDatabase(driver_config=driver_config)
            processor = FileChangeProcessor(
                database=database,
                watch_dirs=self.watch_dirs,
                version_dir=self.version_dir,
            )

            while not self._stop_event.is_set():
                cycle_stats = await self._scan_cycle(database, processor)
                total_stats["scanned_dirs"] += cycle_stats.get("scanned_dirs", 0)
                total_stats["new_files"] += cycle_stats.get("new_files", 0)
                total_stats["changed_files"] += cycle_stats.get("changed_files", 0)
                total_stats["deleted_files"] += cycle_stats.get("deleted_files", 0)
                total_stats["errors"] += cycle_stats.get("errors", 0)
                total_stats["cycles"] += 1

                from datetime import datetime

                cycle_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(
                    f"[CYCLE #{total_stats['cycles']}] {cycle_time} | "
                    f"scanned_dirs: {cycle_stats.get('scanned_dirs', 0)} | "
                    f"new_files: {cycle_stats.get('new_files', 0)} | "
                    f"changed_files: {cycle_stats.get('changed_files', 0)} | "
                    f"deleted_files: {cycle_stats.get('deleted_files', 0)} | "
                    f"errors: {cycle_stats.get('errors', 0)}"
                )

                # Wait for next scan interval
                await asyncio.sleep(self.scan_interval)

            database.close()

        except KeyboardInterrupt:
            logger.info("File watcher worker interrupted")
        except Exception as e:
            logger.error(f"File watcher worker error: {e}", exc_info=True)
            total_stats["errors"] += 1

        return total_stats

    async def _scan_cycle(
        self, database: Any, processor: FileChangeProcessor
    ) -> Dict[str, Any]:
        """
        Perform one scan cycle for all root watched directories.

        Args:
            database: CodeDatabase instance
            processor: FileChangeProcessor instance

        Returns:
            Dictionary with cycle statistics
        """
        cycle_stats = {
            "scanned_dirs": 0,
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }

        for root_dir in self.watch_dirs:
            if self._stop_event.is_set():
                break

            if not root_dir.exists():
                logger.warning(f"Watched directory does not exist: {root_dir}")
                continue

            # Acquire lock for root directory
            if not self.lock_manager.acquire_lock(root_dir, self._pid):
                logger.warning(
                    f"Could not acquire lock for {root_dir}, skipping this cycle"
                )
                cycle_stats["errors"] += 1
                continue

            try:
                # Step 3: Scan phase - compute delta without DB operations
                from datetime import datetime

                scan_start = datetime.now()
                logger.info(
                    f"[SCAN START] Directory: {root_dir} | "
                    f"time: {scan_start.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                scanned_files = scan_directory(
                    root_dir=root_dir,
                    watch_dirs=self.watch_dirs,
                    ignore_patterns=self.ignore_patterns,
                )

                # Compute delta (scan phase - no DB writes)
                delta = processor.compute_delta(root_dir, scanned_files)
                scan_end = datetime.now()
                scan_duration = (scan_end - scan_start).total_seconds()
                
                # Log scan results (delta is always Dict[str, FileDelta])
                total_new = sum(len(d.new_files) for d in delta.values())
                total_changed = sum(len(d.changed_files) for d in delta.values())
                total_deleted = sum(len(d.deleted_files) for d in delta.values())
                logger.info(
                    f"[SCAN END] Directory: {root_dir} | "
                    f"time: {scan_end.strftime('%Y-%m-%d %H:%M:%S')} | "
                    f"duration: {scan_duration:.2f}s | "
                    f"files_scanned: {len(scanned_files)} | "
                    f"projects: {len(delta)} | "
                    f"delta: new={total_new}, changed={total_changed}, deleted={total_deleted}"
                )

                # Step 3: Queue phase - batch DB operations
                queue_start = datetime.now()
                dir_stats = processor.queue_changes(root_dir, delta)
                queue_end = datetime.now()
                queue_duration = (queue_end - queue_start).total_seconds()
                logger.info(
                    f"[QUEUE END] Directory: {root_dir} | "
                    f"duration: {queue_duration:.2f}s | "
                    f"new: {dir_stats.get('new_files', 0)} | "
                    f"changed: {dir_stats.get('changed_files', 0)} | "
                    f"deleted: {dir_stats.get('deleted_files', 0)}"
                )

                cycle_stats["scanned_dirs"] += 1
                cycle_stats["new_files"] += dir_stats["new_files"]
                cycle_stats["changed_files"] += dir_stats["changed_files"]
                cycle_stats["deleted_files"] += dir_stats["deleted_files"]
                cycle_stats["errors"] += dir_stats["errors"]

            except Exception as e:
                logger.error(f"Error scanning directory {root_dir}: {e}", exc_info=True)
                cycle_stats["errors"] += 1
            finally:
                # Always release lock
                self.lock_manager.release_lock(root_dir)

        return cycle_stats
