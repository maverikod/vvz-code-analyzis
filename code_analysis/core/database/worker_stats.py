"""
Worker statistics management module.

Provides methods for tracking and retrieving worker cycle statistics
for file_watcher and vectorization workers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def start_file_watcher_cycle(
    self, cycle_id: Optional[str] = None, files_total_at_start: Optional[int] = None
) -> str:
    """
    Start a new file watcher cycle and clear previous statistics.

    Args:
        cycle_id: Optional cycle ID (UUID4). If not provided, will be generated.
        files_total_at_start: Optional total files count on disk at cycle start.
            If not provided, will count from database.

    Returns:
        Cycle ID string
    """
    if cycle_id is None:
        cycle_id = str(uuid.uuid4())

    cycle_start_time = time.time()

    # Don't delete previous cycles - keep history
    # Only ensure we don't have multiple active cycles (shouldn't happen, but just in case)
    # Mark any old active cycles as ended (with current time as end_time)
    self._execute(
        """
        UPDATE file_watcher_stats
        SET cycle_end_time = ?, last_updated = julianday('now')
        WHERE cycle_end_time IS NULL
        """,
        (cycle_start_time,),
    )

    # Get total files count at start
    # If files_total_at_start is provided (counted from disk), use it
    # Otherwise, count from database (backward compatibility)
    if files_total_at_start is None:
        result = self._fetchone(
            "SELECT COUNT(*) as count FROM files WHERE (deleted = 0 OR deleted IS NULL)"
        )
        files_total_at_start = result["count"] if result else 0

    # Insert new cycle record
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
        f"Started file_watcher cycle {cycle_id}, files_total_at_start={files_total_at_start}"
    )
    return cycle_id


def update_file_watcher_stats(
    self,
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
    """
    Update file watcher cycle statistics.

    Args:
        cycle_id: Cycle ID
        files_added: Number of files added (increment)
        files_processed: Number of files processed (increment)
        files_skipped: Number of files skipped (increment)
        files_failed: Number of files failed (increment)
        files_changed: Number of files changed (increment)
        files_deleted: Number of files deleted (increment)
        processing_time_seconds: Processing time for this batch (add to total)
        current_project_id: Optional project ID currently being processed
    """
    # Update statistics with increments
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
    update_params = [
        files_added,
        files_processed,
        files_skipped,
        files_failed,
        files_changed,
        files_deleted,
        processing_time_seconds,
    ]

    # Update current_project_id if provided
    if current_project_id is not None:
        update_sql += ", current_project_id = ?"
        update_params.append(current_project_id)

    update_sql += " WHERE cycle_id = ?"
    update_params.append(cycle_id)

    self._execute(update_sql, tuple(update_params))

    # Calculate and update average processing time
    # Average = total_time / (files_processed + files_failed) if > 0
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


def end_file_watcher_cycle(self, cycle_id: str) -> None:
    """
    End file watcher cycle by setting end time.

    Args:
        cycle_id: Cycle ID
    """
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
    logger.debug(f"Ended file_watcher cycle {cycle_id}")


def get_file_watcher_stats(self) -> Optional[Dict[str, Any]]:
    """
    Get current file watcher cycle statistics.

    Returns the most recent cycle (completed or active).
    If current cycle is active (cycle_end_time is NULL), returns it.
    Otherwise returns the last completed cycle.

    Returns:
        Dictionary with statistics or None if no cycles exist
    """
    # First try to get active cycle (cycle_end_time is NULL)
    result = self._fetchone(
        """
        SELECT
            cycle_id,
            cycle_start_time,
            cycle_end_time,
            files_total_at_start,
            files_added,
            files_processed,
            files_skipped,
            files_failed,
            files_changed,
            files_deleted,
            total_processing_time_seconds,
            average_processing_time_seconds,
            current_project_id,
            last_updated
        FROM file_watcher_stats
        WHERE cycle_end_time IS NULL
        ORDER BY cycle_start_time DESC
        LIMIT 1
        """
    )

    # If no active cycle, get last completed cycle
    if not result:
        result = self._fetchone(
            """
            SELECT
                cycle_id,
                cycle_start_time,
                cycle_end_time,
                files_total_at_start,
                files_added,
                files_processed,
                files_skipped,
                files_failed,
                files_changed,
                files_deleted,
                total_processing_time_seconds,
                average_processing_time_seconds,
                current_project_id,
                last_updated
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


def start_vectorization_cycle(self, cycle_id: Optional[str] = None) -> str:
    """
    Start a new vectorization cycle and clear previous statistics.

    Args:
        cycle_id: Optional cycle ID (UUID4). If not provided, will be generated.

    Returns:
        Cycle ID string
    """
    if cycle_id is None:
        cycle_id = str(uuid.uuid4())

    cycle_start_time = time.time()

    # Don't delete previous cycles - keep history
    # Only ensure we don't have multiple active cycles (shouldn't happen, but just in case)
    # Mark any old active cycles as ended (with current time as end_time)
    self._execute(
        """
        UPDATE vectorization_stats
        SET cycle_end_time = ?, last_updated = julianday('now')
        WHERE cycle_end_time IS NULL
        """,
        (cycle_start_time,),
    )

    # Get total chunks count at start (not vectorized)
    result = self._fetchone(
        "SELECT COUNT(*) as count FROM code_chunks WHERE vector_id IS NULL"
    )
    chunks_total_at_start = result["count"] if result else 0

    # Insert new cycle record
    self._execute(
        """
        INSERT INTO vectorization_stats (
            cycle_id, cycle_start_time, chunks_total_at_start,
            chunks_processed, chunks_skipped, chunks_failed,
            total_processing_time_seconds, average_processing_time_seconds,
            last_updated
        ) VALUES (?, ?, ?, 0, 0, 0, 0.0, NULL, julianday('now'))
        """,
        (cycle_id, cycle_start_time, chunks_total_at_start),
    )
    self._commit()

    logger.debug(
        f"Started vectorization cycle {cycle_id}, chunks_total_at_start={chunks_total_at_start}"
    )
    return cycle_id


def update_vectorization_stats(
    self,
    cycle_id: str,
    chunks_processed: int = 0,
    chunks_skipped: int = 0,
    chunks_failed: int = 0,
    processing_time_seconds: float = 0.0,
) -> None:
    """
    Update vectorization cycle statistics.

    Args:
        cycle_id: Cycle ID
        chunks_processed: Number of chunks processed (increment)
        chunks_skipped: Number of chunks skipped (increment)
        chunks_failed: Number of chunks failed (increment)
        processing_time_seconds: Processing time for this batch (add to total)
    """
    # Update statistics with increments
    self._execute(
        """
        UPDATE vectorization_stats
        SET
            chunks_processed = chunks_processed + ?,
            chunks_skipped = chunks_skipped + ?,
            chunks_failed = chunks_failed + ?,
            total_processing_time_seconds = total_processing_time_seconds + ?,
            last_updated = julianday('now')
        WHERE cycle_id = ?
        """,
        (
            chunks_processed,
            chunks_skipped,
            chunks_failed,
            processing_time_seconds,
            cycle_id,
        ),
    )

    # Calculate and update average processing time
    # Average = total_time / (chunks_processed + chunks_failed) if > 0
    self._execute(
        """
        UPDATE vectorization_stats
        SET average_processing_time_seconds = CASE
            WHEN (chunks_processed + chunks_failed) > 0
            THEN total_processing_time_seconds / (chunks_processed + chunks_failed)
            ELSE NULL
        END
        WHERE cycle_id = ?
        """,
        (cycle_id,),
    )
    self._commit()


def end_vectorization_cycle(self, cycle_id: str) -> None:
    """
    End vectorization cycle by setting end time.

    Args:
        cycle_id: Cycle ID
    """
    cycle_end_time = time.time()
    self._execute(
        """
        UPDATE vectorization_stats
        SET cycle_end_time = ?, last_updated = julianday('now')
        WHERE cycle_id = ?
        """,
        (cycle_end_time, cycle_id),
    )
    self._commit()
    logger.debug(f"Ended vectorization cycle {cycle_id}")


def get_vectorization_stats(self) -> Optional[Dict[str, Any]]:
    """
    Get current vectorization cycle statistics.

    Returns the most recent cycle (completed or active).
    If current cycle is active (cycle_end_time is NULL), returns it.
    Otherwise returns the last completed cycle.

    Returns:
        Dictionary with statistics or None if no cycles exist
    """
    # First try to get active cycle (cycle_end_time is NULL)
    result = self._fetchone(
        """
        SELECT
            cycle_id,
            cycle_start_time,
            cycle_end_time,
            chunks_total_at_start,
            chunks_processed,
            chunks_skipped,
            chunks_failed,
            total_processing_time_seconds,
            average_processing_time_seconds,
            last_updated
        FROM vectorization_stats
        WHERE cycle_end_time IS NULL
        ORDER BY cycle_start_time DESC
        LIMIT 1
        """
    )

    # If no active cycle, get last completed cycle
    if not result:
        result = self._fetchone(
            """
            SELECT
                cycle_id,
                cycle_start_time,
                cycle_end_time,
                chunks_total_at_start,
                chunks_processed,
                chunks_skipped,
                chunks_failed,
                total_processing_time_seconds,
                average_processing_time_seconds,
                last_updated
            FROM vectorization_stats
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
        "chunks_total_at_start": result["chunks_total_at_start"],
        "chunks_processed": result["chunks_processed"],
        "chunks_skipped": result["chunks_skipped"],
        "chunks_failed": result["chunks_failed"],
        "total_processing_time_seconds": result["total_processing_time_seconds"],
        "average_processing_time_seconds": result["average_processing_time_seconds"],
        "last_updated": result["last_updated"],
    }
