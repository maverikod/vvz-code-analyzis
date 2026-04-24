"""
One scan cycle for multi-project file watcher.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Dict

import logging

from .multi_project_worker_scan import scan_watch_dir
from .processor import FileChangeProcessor

logger = logging.getLogger(__name__)


async def run_scan_cycle(worker: Any, database: Any, processors: Any) -> Dict[str, Any]:
    """
    Perform one scan cycle for all watched directories.

    Projects are discovered automatically within each watched directory.

    Args:
        worker: MultiProjectFileWatcherWorker instance (uses watch_dirs,
            version_dir, status_file_path, _stop_event, ignore_patterns,
            locks_dir, _pid, _count_files_on_disk).
        database: CodeDatabase instance.
        processors: Unused (kept for API compatibility).

    Returns:
        Dictionary with cycle statistics.
    """
    from ..worker_status_file import (
        STATUS_OPERATION_IDLE,
        STATUS_OPERATION_SCANNING,
        write_worker_status,
    )

    write_worker_status(
        getattr(worker, "status_file_path", None),
        STATUS_OPERATION_SCANNING,
        current_file=None,
    )
    logger.info("Counting total files on disk across all projects...")
    files_total_on_disk = worker._count_files_on_disk()
    logger.info(f"Total files on disk: {files_total_on_disk}")

    cycle_id = str(uuid.uuid4())
    cycle_start_time = time.time()

    database.execute(
        """
        UPDATE file_watcher_stats
        SET cycle_end_time = ?, last_updated = julianday('now')
        WHERE cycle_end_time IS NULL
        """,
        (cycle_start_time,),
    )

    database.execute(
        """
        INSERT INTO file_watcher_stats (
            cycle_id, cycle_start_time, files_total_at_start, last_updated
        ) VALUES (?, ?, ?, julianday('now'))
        """,
        (cycle_id, cycle_start_time, files_total_on_disk),
    )

    cycle_stats: Dict[str, Any] = {
        "scanned_dirs": 0,
        "new_files": 0,
        "changed_files": 0,
        "deleted_files": 0,
        "errors": 0,
    }

    processor = FileChangeProcessor(
        database=database,
        watch_dirs=[spec.watch_dir for spec in worker.watch_dirs],
        version_dir=worker.version_dir,
    )

    cfg_raw = getattr(worker, "config_path", None)
    scan_config_path = Path(cfg_raw) if cfg_raw else None

    progress_done = 0.0

    for spec in worker.watch_dirs:
        if worker._stop_event.is_set():
            break

        write_worker_status(
            getattr(worker, "status_file_path", None),
            STATUS_OPERATION_SCANNING,
            current_file=str(spec.watch_dir),
            progress_percent=round(progress_done, 1) if progress_done else 0,
        )
        watch_dir_start = time.time()
        watch_dir_stats = scan_watch_dir(
            spec,
            processor,
            database,
            tuple(worker.ignore_patterns),
            worker.locks_dir,
            worker._pid,
            config_path=scan_config_path,
        )
        watch_dir_duration = time.time() - watch_dir_start

        cycle_stats["scanned_dirs"] += watch_dir_stats.get("scanned_dirs", 0)
        cycle_stats["new_files"] += watch_dir_stats.get("new_files", 0)
        cycle_stats["changed_files"] += watch_dir_stats.get("changed_files", 0)
        cycle_stats["deleted_files"] += watch_dir_stats.get("deleted_files", 0)
        cycle_stats["errors"] += watch_dir_stats.get("errors", 0)
        if files_total_on_disk:
            processed = (
                cycle_stats["new_files"]
                + cycle_stats["changed_files"]
                + cycle_stats["deleted_files"]
            )
            progress_done = min(100.0, (processed / files_total_on_disk) * 100.0)

        database.execute(
            """
            UPDATE file_watcher_stats
            SET
                files_added = files_added + ?,
                files_processed = files_processed + ?,
                files_skipped = files_skipped + ?,
                files_failed = files_failed + ?,
                files_changed = files_changed + ?,
                files_deleted = files_deleted + ?,
                total_processing_time_seconds = total_processing_time_seconds + ?,
                last_updated = julianday('now')
            WHERE cycle_id = ?
            """,
            (
                watch_dir_stats.get("new_files", 0),
                watch_dir_stats.get("new_files", 0)
                + watch_dir_stats.get("changed_files", 0),
                0,
                watch_dir_stats.get("errors", 0),
                watch_dir_stats.get("changed_files", 0),
                watch_dir_stats.get("deleted_files", 0),
                watch_dir_duration,
                cycle_id,
            ),
        )

    database.execute(
        """
        UPDATE file_watcher_stats
        SET cycle_end_time = ?, last_updated = julianday('now')
        WHERE cycle_id = ?
        """,
        (time.time(), cycle_id),
    )
    write_worker_status(
        getattr(worker, "status_file_path", None),
        STATUS_OPERATION_IDLE,
        current_file=None,
        progress_percent=100.0 if files_total_on_disk else None,
    )
    return cycle_stats
