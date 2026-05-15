"""
Vectorization cycle statistics.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
import uuid
from typing import Any, Dict, Optional

from code_analysis.core.sql_portable import (
    WHERE_FILES_ACTIVE,
    WHERE_FILES_ACTIVE_F,
    sql_julian_timestamp_now_expr,
)
from code_analysis.core.vector_search_backend import (
    VectorSearchBackend,
    ann_pending_sql_fragment,
    ann_ready_sql_fragment,
    effective_vector_search_backend,
)

logger = logging.getLogger(__name__)


def _vector_ann_backend(self: Any) -> VectorSearchBackend:
    dc = getattr(self, "driver_config", None) or {}
    dt = str(dc.get("type") or "")
    inner = dc.get("config") or {}
    vsb = inner.get("vector_search_backend")
    return effective_vector_search_backend(dt, vsb)


def start_vectorization_cycle(self: Any, cycle_id: Optional[str] = None) -> str:
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
    _now = sql_julian_timestamp_now_expr(self)

    # Don't delete previous cycles - keep history
    # Only ensure we don't have multiple active cycles (shouldn't happen, but just in case)
    # Mark any old active cycles as ended (with current time as end_time)
    self._execute(
        f"""
        UPDATE vectorization_stats
        SET cycle_end_time = ?, last_updated = {_now}
        WHERE cycle_end_time IS NULL
        """,
        (cycle_start_time,),
    )

    ann = _vector_ann_backend(self)
    chunk_pending = ann_pending_sql_fragment("code_chunks", ann)
    # Total chunks count at start (not ANN-indexed; exclude skipped)
    result = self._fetchone(
        f"""SELECT COUNT(*) as count FROM code_chunks
           WHERE {chunk_pending}
             AND (vectorization_skipped IS NULL OR vectorization_skipped = 0)"""
    )
    chunks_total_at_start = result["count"] if result else 0

    # Get total files count at start (active files in all projects)
    files_result = self._fetchone(
        f"SELECT COUNT(*) as count FROM files WHERE {WHERE_FILES_ACTIVE}"
    )
    files_total_at_start = files_result["count"] if files_result else 0

    cc_ready = ann_ready_sql_fragment("cc", ann)
    vectorized_files_result = self._fetchone(
        f"""
        SELECT COUNT(DISTINCT f.id) as count
        FROM files f
        INNER JOIN code_chunks cc ON f.id = cc.file_id
        WHERE {WHERE_FILES_ACTIVE_F}
        AND {cc_ready}
        """
    )
    files_vectorized = (
        vectorized_files_result["count"] if vectorized_files_result else 0
    )

    # Insert new cycle record
    self._execute(
        f"""
        INSERT INTO vectorization_stats (
            cycle_id, cycle_start_time, chunks_total_at_start,
            chunks_processed, chunks_skipped, chunks_failed,
            files_total_at_start, files_vectorized,
            total_processing_time_seconds, average_processing_time_seconds,
            last_updated
        ) VALUES (?, ?, ?, 0, 0, 0, ?, ?, 0.0, NULL, {_now})
        """,
        (
            cycle_id,
            cycle_start_time,
            chunks_total_at_start,
            files_total_at_start,
            files_vectorized,
        ),
    )
    self._commit()

    logger.debug(
        f"Started vectorization cycle {cycle_id}, "
        f"chunks_total_at_start={chunks_total_at_start}, "
        f"files_total_at_start={files_total_at_start}, "
        f"files_vectorized={files_vectorized}"
    )
    return cycle_id


def update_vectorization_stats(
    self: Any,
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
    _now = sql_julian_timestamp_now_expr(self)
    self._execute(
        f"""
        UPDATE vectorization_stats
        SET
            chunks_processed = chunks_processed + ?,
            chunks_skipped = chunks_skipped + ?,
            chunks_failed = chunks_failed + ?,
            total_processing_time_seconds = total_processing_time_seconds + ?,
            last_updated = {_now}
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

    ann_u = _vector_ann_backend(self)
    cc_ready_u = ann_ready_sql_fragment("cc", ann_u)
    vectorized_files_result = self._fetchone(
        f"""
        SELECT COUNT(DISTINCT f.id) as count
        FROM files f
        INNER JOIN code_chunks cc ON f.id = cc.file_id
        WHERE {WHERE_FILES_ACTIVE_F}
        AND {cc_ready_u}
        """
    )
    files_vectorized = (
        vectorized_files_result["count"] if vectorized_files_result else 0
    )
    self._execute(
        """
        UPDATE vectorization_stats
        SET files_vectorized = ?
        WHERE cycle_id = ?
        """,
        (files_vectorized, cycle_id),
    )

    self._commit()


def end_vectorization_cycle(self: Any, cycle_id: str) -> None:
    """
    End vectorization cycle by setting end time.

    Args:
        cycle_id: Cycle ID
    """
    cycle_end_time = time.time()
    _now = sql_julian_timestamp_now_expr(self)
    self._execute(
        f"""
        UPDATE vectorization_stats
        SET cycle_end_time = ?, last_updated = {_now}
        WHERE cycle_id = ?
        """,
        (cycle_end_time, cycle_id),
    )
    self._commit()
    logger.debug(f"Ended vectorization cycle {cycle_id}")


def get_vectorization_stats(self: Any) -> Optional[Dict[str, Any]]:
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
            files_total_at_start,
            files_vectorized,
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
                files_total_at_start,
                files_vectorized,
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

    # Calculate percentage of vectorized files
    files_total = result.get("files_total_at_start", 0) or 0
    files_vectorized = result.get("files_vectorized", 0) or 0
    files_vectorized_percent = None
    if files_total and files_total > 0:
        files_vectorized_percent = round((files_vectorized / files_total) * 100, 2)

    return {
        "cycle_id": result["cycle_id"],
        "cycle_start_time": result["cycle_start_time"],
        "cycle_end_time": result["cycle_end_time"],
        "chunks_total_at_start": result["chunks_total_at_start"],
        "chunks_processed": result["chunks_processed"],
        "chunks_skipped": result["chunks_skipped"],
        "chunks_failed": result["chunks_failed"],
        "files_total_at_start": files_total,
        "files_vectorized": files_vectorized,
        "files_vectorized_percent": files_vectorized_percent,
        "total_processing_time_seconds": result["total_processing_time_seconds"],
        "average_processing_time_seconds": result["average_processing_time_seconds"],
        "last_updated": result["last_updated"],
    }
