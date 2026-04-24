"""
Indexing cycle statistics.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
import uuid
from typing import Any, Dict, Optional

from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE

logger = logging.getLogger(__name__)


def start_indexing_cycle(
    self: Any,
    cycle_id: Optional[str] = None,
    files_total_at_start: Optional[int] = None,
) -> str:
    """
    Start a new indexing cycle and clear previous statistics.

    Args:
        cycle_id: Optional cycle ID (UUID4). If not provided, will be generated.
        files_total_at_start: Optional count of files with needs_chunking=1 at start.
            If not provided, will be counted from database.

    Returns:
        Cycle ID string
    """
    if cycle_id is None:
        cycle_id = str(uuid.uuid4())

    cycle_start_time = time.time()

    self._execute(
        """
        UPDATE indexing_worker_stats
        SET cycle_end_time = ?, last_updated = julianday('now')
        WHERE cycle_end_time IS NULL
        """,
        (cycle_start_time,),
    )

    if files_total_at_start is None:
        result = self._fetchone(
            f"""
            SELECT COUNT(*) as count FROM files
            WHERE {WHERE_FILES_ACTIVE} AND needs_chunking = 1
            """
        )
        files_total_at_start = result["count"] if result else 0

    self._execute(
        """
        INSERT INTO indexing_worker_stats (
            cycle_id, cycle_start_time, files_total_at_start,
            files_indexed, files_failed,
            total_processing_time_seconds, average_processing_time_seconds,
            last_updated
        ) VALUES (?, ?, ?, 0, 0, 0.0, NULL, julianday('now'))
        """,
        (cycle_id, cycle_start_time, files_total_at_start),
    )
    self._commit()

    logger.debug(
        f"Started indexing cycle {cycle_id}, files_total_at_start={files_total_at_start}"
    )
    return cycle_id


def update_indexing_stats(
    self: Any,
    cycle_id: str,
    files_indexed: int = 0,
    files_failed: int = 0,
    processing_time_seconds: float = 0.0,
) -> None:
    """
    Update indexing cycle statistics (batch: two UPDATEs in one round-trip).

    Args:
        cycle_id: Cycle ID
        files_indexed: Number of files indexed (increment)
        files_failed: Number of files failed (increment)
        processing_time_seconds: Processing time for this batch (add to total)
    """
    ops = [
        (
            """
            UPDATE indexing_worker_stats
            SET
                files_indexed = files_indexed + ?,
                files_failed = files_failed + ?,
                total_processing_time_seconds = total_processing_time_seconds + ?,
                last_updated = julianday('now')
            WHERE cycle_id = ?
            """,
            (files_indexed, files_failed, processing_time_seconds, cycle_id),
        ),
        (
            """
            UPDATE indexing_worker_stats
            SET average_processing_time_seconds = CASE
                WHEN (files_indexed + files_failed) > 0
                THEN total_processing_time_seconds / (files_indexed + files_failed)
                ELSE NULL
            END
            WHERE cycle_id = ?
            """,
            (cycle_id,),
        ),
    ]
    tid = self.begin_transaction()
    self.execute_batch(ops, tid)
    self.commit_transaction(tid)


def end_indexing_cycle(self: Any, cycle_id: str) -> None:
    """
    End indexing cycle by setting end time.

    Args:
        cycle_id: Cycle ID
    """
    cycle_end_time = time.time()
    self._execute(
        """
        UPDATE indexing_worker_stats
        SET cycle_end_time = ?, last_updated = julianday('now')
        WHERE cycle_id = ?
        """,
        (cycle_end_time, cycle_id),
    )
    self._commit()
    logger.debug(f"Ended indexing cycle {cycle_id}")


def get_indexing_stats(self: Any) -> Optional[Dict[str, Any]]:
    """
    Get current indexing cycle statistics.

    Returns the most recent cycle (completed or active).
    If current cycle is active (cycle_end_time is NULL), returns it.
    Otherwise returns the last completed cycle.

    Returns:
        Dictionary with statistics or None if no cycles exist
    """
    result = self._fetchone(
        """
        SELECT
            cycle_id,
            cycle_start_time,
            cycle_end_time,
            files_total_at_start,
            files_indexed,
            files_failed,
            total_processing_time_seconds,
            average_processing_time_seconds,
            last_updated
        FROM indexing_worker_stats
        WHERE cycle_end_time IS NULL
        ORDER BY cycle_start_time DESC
        LIMIT 1
        """
    )

    if not result:
        result = self._fetchone(
            """
            SELECT
                cycle_id,
                cycle_start_time,
                cycle_end_time,
                files_total_at_start,
                files_indexed,
                files_failed,
                total_processing_time_seconds,
                average_processing_time_seconds,
                last_updated
            FROM indexing_worker_stats
            WHERE cycle_end_time IS NOT NULL
            ORDER BY cycle_start_time DESC
            LIMIT 1
            """
        )

    if not result:
        return None

    files_total = result.get("files_total_at_start", 0) or 0
    files_done = (result.get("files_indexed", 0) or 0) + (
        result.get("files_failed", 0) or 0
    )
    files_indexed_percent = None
    if files_total and files_total > 0:
        files_indexed_percent = round((files_done / files_total) * 100, 2)

    return {
        "cycle_id": result["cycle_id"],
        "cycle_start_time": result["cycle_start_time"],
        "cycle_end_time": result["cycle_end_time"],
        "files_total_at_start": result["files_total_at_start"],
        "files_indexed": result["files_indexed"],
        "files_failed": result["files_failed"],
        "files_indexed_percent": files_indexed_percent,
        "total_processing_time_seconds": result["total_processing_time_seconds"],
        "average_processing_time_seconds": result["average_processing_time_seconds"],
        "last_updated": result["last_updated"],
    }
