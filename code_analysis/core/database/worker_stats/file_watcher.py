"""
File watcher cycle statistics (start, update, end, get).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE

logger = logging.getLogger(__name__)


def start_file_watcher_cycle(
    self: Any,
    cycle_id: Optional[str] = None,
    files_total_at_start: Optional[int] = None,
) -> str:
    """Start a new file watcher cycle and clear previous statistics."""
    if cycle_id is None:
        cycle_id = str(uuid.uuid4())

    cycle_start_time = time.time()

    self._execute(
        """
        UPDATE file_watcher_stats
        SET cycle_end_time = ?, last_updated = julianday('now')
        WHERE cycle_end_time IS NULL
        """,
        (cycle_start_time,),
    )

    if files_total_at_start is None:
        result = self._fetchone(
            f"SELECT COUNT(*) as count FROM files WHERE {WHERE_FILES_ACTIVE}"
        )
        files_total_at_start = result["count"] if result else 0

    self._execute(
        """
        INSERT INTO file_watcher_stats (
            cycle_id, cycle_start_time, files_total_at_start,
            files_added, files_processed, files_skipped, files_failed,
            files_changed, files_deleted,
            total_processing_time_seconds, average_processing_time_seconds,
            current_project_id, last_updated
        ) VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0, 0.0, NULL, NULL, julianday('now'))
        """,
        (cycle_id, cycle_start_time, files_total_at_start),
    )
    self._commit()

    logger.debug(
        "Started file_watcher cycle %s, files_total_at_start=%s",
        cycle_id,
        files_total_at_start,
    )
    return cycle_id


def update_file_watcher_stats(
    self: Any,
    cycle_id: str,
    files_added: int = 0,
    files_processed: int = 0,
    files_skipped: int = 0,
    files_failed: int = 0,
    files_changed: int = 0,
    files_deleted: int = 0,
    processing_time_seconds: float = 0.0,
    current_project_id: Optional[str] = None,
) -> None:
    """Update file watcher cycle statistics."""
    update_sql = """
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
    """
    update_params: List[Union[int, float, str, None]] = [
        files_added,
        files_processed,
        files_skipped,
        files_failed,
        files_changed,
        files_deleted,
        processing_time_seconds,
    ]
    if current_project_id is not None:
        update_sql += ", current_project_id = ?"
        update_params.append(current_project_id)
    update_sql += " WHERE cycle_id = ?"
    update_params.append(cycle_id)
    self._execute(update_sql, tuple(update_params))

    self._execute(
        """
        UPDATE file_watcher_stats
        SET average_processing_time_seconds = CASE
            WHEN (files_processed + files_failed) > 0
            THEN total_processing_time_seconds / (files_processed + files_failed)
            ELSE NULL
        END
        WHERE cycle_id = ?
        """,
        (cycle_id,),
    )
    self._commit()


def end_file_watcher_cycle(self: Any, cycle_id: str) -> None:
    """End file watcher cycle by setting end time."""
    cycle_end_time = time.time()
    self._execute(
        """
        UPDATE file_watcher_stats
        SET cycle_end_time = ?, last_updated = julianday('now')
        WHERE cycle_id = ?
        """,
        (cycle_end_time, cycle_id),
    )
    self._commit()
    logger.debug("Ended file_watcher cycle %s", cycle_id)


def get_file_watcher_stats(self: Any) -> Optional[Dict[str, Any]]:
    """Get current file watcher cycle statistics (most recent active or completed)."""
    result = self._fetchone(
        """
        SELECT
            cycle_id, cycle_start_time, cycle_end_time,
            files_total_at_start, files_added, files_processed, files_skipped,
            files_failed, files_changed, files_deleted,
            total_processing_time_seconds, average_processing_time_seconds,
            current_project_id, last_updated
        FROM file_watcher_stats
        WHERE cycle_end_time IS NULL
        ORDER BY cycle_start_time DESC
        LIMIT 1
        """
    )

    if not result:
        result = self._fetchone(
            """
            SELECT
                cycle_id, cycle_start_time, cycle_end_time,
                files_total_at_start, files_added, files_processed, files_skipped,
                files_failed, files_changed, files_deleted,
                total_processing_time_seconds, average_processing_time_seconds,
                current_project_id, last_updated
            FROM file_watcher_stats
            WHERE cycle_end_time IS NOT NULL
            ORDER BY cycle_start_time DESC
            LIMIT 1
            """
        )

    if not result:
        return None

    return {
        "cycle_id": result["cycle_id"],
        "cycle_start_time": result["cycle_start_time"],
        "cycle_end_time": result["cycle_end_time"],
        "files_total_at_start": result["files_total_at_start"],
        "files_added": result["files_added"],
        "files_processed": result["files_processed"],
        "files_skipped": result["files_skipped"],
        "files_failed": result["files_failed"],
        "files_changed": result["files_changed"],
        "files_deleted": result["files_deleted"],
        "total_processing_time_seconds": result["total_processing_time_seconds"],
        "average_processing_time_seconds": result["average_processing_time_seconds"],
        "current_project_id": result.get("current_project_id"),
        "last_updated": result["last_updated"],
    }
