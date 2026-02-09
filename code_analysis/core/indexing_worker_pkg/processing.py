"""
Processing loop for IndexingWorker.

One cycle: discover projects with needs_chunking=1, per project take a batch of files,
call database.index_file(path, project_id). Backoff on DB unavailability.
Writes cycle stats to indexing_worker_stats (start/update/end) via database.execute().

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict

from ..worker_status_file import (
    STATUS_OPERATION_IDLE,
    STATUS_OPERATION_INDEXING,
    STATUS_OPERATION_POLLING,
    write_worker_status,
)

logger = logging.getLogger(__name__)


async def process_cycle(self: Any, poll_interval: int = 30) -> Dict[str, Any]:
    """Run indexing cycles until stop: query projects with needs_chunking=1, index batch per project.

    Discovery: SELECT DISTINCT project_id FROM files WHERE (deleted=0 OR deleted IS NULL)
    AND needs_chunking=1. Per project: SELECT id, path, project_id FROM files
    WHERE project_id=? AND (deleted=0 OR deleted IS NULL) AND needs_chunking=1
    ORDER BY updated_at ASC LIMIT ?. For each file call database.index_file(path, project_id).
    Driver clears needs_chunking after success. Backoff 1–60s when DB unavailable.

    Args:
        poll_interval: Seconds between cycles (default 30).

    Returns:
        Stats dict when stopped: indexed, errors, cycles.
    """
    from ..database_client.client import DatabaseClient
    from ..constants import DEFAULT_DB_DRIVER_SOCKET_DIR

    if not self.socket_path:
        db_name = self.db_path.stem if hasattr(self.db_path, "stem") else "db"
        from pathlib import Path

        socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
        socket_dir.mkdir(parents=True, exist_ok=True)
        socket_path = str(socket_dir / f"{db_name}_driver.sock")
    else:
        socket_path = self.socket_path

    db_available = False
    db_status_logged = False
    database: Any = None
    total_indexed = 0
    total_errors = 0
    cycle_count = 0
    backoff = 1.0
    backoff_max = 60.0

    try:
        logger.info(
            "Starting indexing worker, poll interval: %ss, batch_size: %s",
            poll_interval,
            self.batch_size,
        )

        while not self._stop_event.is_set():
            cycle_count += 1

            if database is None or not db_available:
                try:
                    database = DatabaseClient(socket_path=socket_path)
                    database.connect()
                    try:
                        database.execute(
                            "SELECT 1",
                            None,
                        )
                        if not db_available:
                            logger.info("Database is now available")
                            db_available = True
                            db_status_logged = True
                            backoff = 1.0
                        else:
                            db_status_logged = False
                    except Exception as e:
                        if db_available:
                            logger.warning("Database is now unavailable: %s", e)
                            db_available = False
                            db_status_logged = True
                        elif not db_status_logged:
                            logger.warning("Database is unavailable: %s", e)
                            db_status_logged = True
                        else:
                            db_status_logged = False
                        try:
                            database.disconnect()
                        except Exception:
                            pass
                        database = None
                        logger.debug("Retrying in %.1fs...", backoff)
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2.0, backoff_max)
                        continue
                except Exception as e:
                    if db_available:
                        logger.warning("Database is now unavailable: %s", e)
                        db_available = False
                        db_status_logged = True
                    elif not db_status_logged:
                        logger.warning("Database is unavailable: %s", e)
                        db_status_logged = True
                    logger.debug("Retrying in %.1fs...", backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, backoff_max)
                    continue

            try:
                write_worker_status(
                    getattr(self, "status_file_path", None),
                    STATUS_OPERATION_POLLING,
                    current_file=None,
                )
                logger.info("[CYCLE #%s] Starting indexing cycle", cycle_count)
            except Exception as e:
                try:
                    logger.warning("Indexing cycle setup failed (will retry): %s", e)
                except Exception:
                    pass
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, backoff_max)
                continue

            cycle_id = str(uuid.uuid4())
            cycle_start_time = time.time()
            cycle_had_activity = False

            try:
                # Start indexing_worker_stats cycle (same pattern as vectorization)
                database.execute(
                    """
                    UPDATE indexing_worker_stats
                    SET cycle_end_time = ?, last_updated = julianday('now')
                    WHERE cycle_end_time IS NULL
                    """,
                    (cycle_start_time,),
                )
                files_total_result = database.execute(
                    """
                    SELECT COUNT(*) as count FROM files
                    WHERE (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1
                    """,
                    None,
                )
                files_total_at_start = 0
                if isinstance(files_total_result, dict) and files_total_result.get(
                    "data"
                ):
                    row = files_total_result["data"][0]
                    files_total_at_start = row.get("count", 0) or 0
                logger.info(
                    "[CYCLE #%s] files_total_at_start (needs_chunking=1)=%s",
                    cycle_count,
                    files_total_at_start,
                )
                database.execute(
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

                try:
                    projects_result = database.execute(
                        "SELECT DISTINCT project_id FROM files "
                        "WHERE (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1",
                        None,
                    )
                    projects_data = (
                        projects_result.get("data", [])
                        if isinstance(projects_result, dict)
                        else []
                    )
                    project_ids = [
                        row["project_id"]
                        for row in projects_data
                        if row.get("project_id")
                    ]
                    logger.info(
                        "[CYCLE #%s] project_ids count=%s (batch_size=%s)",
                        cycle_count,
                        len(project_ids),
                        self.batch_size,
                    )

                    if not project_ids:
                        logger.info(
                            "[CYCLE #%s] No projects with files needing indexing",
                            cycle_count,
                        )
                    else:
                        cycle_indexed = 0
                        cycle_had_activity = False
                        for project_id in project_ids:
                            files_result = database.execute(
                                "SELECT id, path, project_id FROM files "
                                "WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL) "
                                "AND needs_chunking = 1 ORDER BY updated_at ASC LIMIT ?",
                                (project_id, self.batch_size),
                            )
                            files_data = (
                                files_result.get("data", [])
                                if isinstance(files_result, dict)
                                else []
                            )
                            logger.info(
                                "[CYCLE #%s] project_id=%s files_batch=%s",
                                cycle_count,
                                project_id[:8] if project_id else None,
                                len(files_data),
                            )
                            for row in files_data:
                                path = row.get("path")
                                if not path or not project_id:
                                    continue
                                # Only index Python files; skip others and clear flag so they are not retried
                                if not (path.endswith(".py") or path.endswith(".pyi")):
                                    try:
                                        database.execute(
                                            "UPDATE files SET needs_chunking = 0 WHERE id = ?",
                                            (row.get("id"),),
                                        )
                                    except Exception:
                                        pass
                                    continue
                                file_start = time.time()
                                progress_pct = (
                                    round(cycle_indexed / files_total_at_start * 100, 1)
                                    if files_total_at_start
                                    else None
                                )
                                write_worker_status(
                                    getattr(self, "status_file_path", None),
                                    STATUS_OPERATION_INDEXING,
                                    current_file=path,
                                    progress_percent=progress_pct,
                                )
                                try:
                                    result = database.index_file(path, project_id)
                                    elapsed = time.time() - file_start
                                    if result.get("success"):
                                        total_indexed += 1
                                        logger.debug("Indexed %s", path)
                                        try:
                                            database.execute(
                                                "DELETE FROM indexing_errors WHERE project_id = ? AND file_path = ?",
                                                (project_id, path),
                                            )
                                        except Exception:
                                            pass
                                    else:
                                        total_errors += 1
                                        err_msg = result.get("error", "unknown")
                                        logger.warning(
                                            "Index failed for %s: %s",
                                            path,
                                            err_msg,
                                        )
                                        try:
                                            database.execute(
                                                """
                                                INSERT OR REPLACE INTO indexing_errors
                                                (project_id, file_path, error_type, error_message, created_at)
                                                VALUES (?, ?, ?, ?, julianday('now'))
                                                """,
                                                (
                                                    project_id,
                                                    path,
                                                    "index_error",
                                                    err_msg,
                                                ),
                                            )
                                            if "temp_files" in (err_msg or ""):
                                                logger.error(
                                                    "[indexing_errors] Stored temp_files-related error (caller=index_file): %s",
                                                    err_msg,
                                                )
                                        except Exception:
                                            pass
                                    database.execute(
                                        """
                                        UPDATE indexing_worker_stats
                                        SET
                                            files_indexed = files_indexed + ?,
                                            files_failed = files_failed + ?,
                                            total_processing_time_seconds = total_processing_time_seconds + ?,
                                            last_updated = julianday('now')
                                        WHERE cycle_id = ?
                                        """,
                                        (
                                            1 if result.get("success") else 0,
                                            0 if result.get("success") else 1,
                                            elapsed,
                                            cycle_id,
                                        ),
                                    )
                                    database.execute(
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
                                    )
                                    cycle_indexed += 1
                                    cycle_had_activity = True
                                except Exception as e:
                                    total_errors += 1
                                    cycle_indexed += 1
                                    cycle_had_activity = True
                                    elapsed = time.time() - file_start
                                    try:
                                        logger.warning(
                                            "Index error for %s: %s", path, e
                                        )
                                    except Exception:
                                        pass
                                    try:
                                        err_str = str(e)
                                        database.execute(
                                            """
                                            INSERT OR REPLACE INTO indexing_errors
                                            (project_id, file_path, error_type, error_message, created_at)
                                            VALUES (?, ?, ?, ?, julianday('now'))
                                            """,
                                            (
                                                project_id,
                                                path,
                                                "index_exception",
                                                err_str,
                                            ),
                                        )
                                        if "temp_files" in err_str:
                                            logger.error(
                                                "[indexing_errors] Stored temp_files-related exception (caller=index_file): %s",
                                                err_str,
                                            )
                                    except Exception:
                                        pass
                                    try:
                                        database.execute(
                                            """
                                            UPDATE indexing_worker_stats
                                            SET
                                                files_failed = files_failed + 1,
                                                total_processing_time_seconds = total_processing_time_seconds + ?,
                                                last_updated = julianday('now')
                                            WHERE cycle_id = ?
                                            """,
                                            (elapsed, cycle_id),
                                        )
                                        database.execute(
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
                                        )
                                    except Exception:
                                        pass
                        write_worker_status(
                            getattr(self, "status_file_path", None),
                            STATUS_OPERATION_IDLE,
                            current_file=None,
                        )
                except Exception as e:
                    try:
                        logger.error("Error in indexing cycle: %s", e, exc_info=True)
                    except Exception:
                        pass
                    err_str = str(e).lower()
                    if (
                        "database" in err_str
                        or "connection" in err_str
                        or "db" in err_str
                    ):
                        try:
                            database.disconnect()
                        except Exception:
                            pass
                        database = None
                    db_available = False
                    db_status_logged = False
                    backoff = min(backoff * 2.0, backoff_max)
                    try:
                        await asyncio.sleep(backoff)
                    except Exception:
                        pass
                    continue

                # End indexing_worker_stats cycle
                try:
                    database.execute(
                        """
                        UPDATE indexing_worker_stats
                        SET cycle_end_time = ?, last_updated = julianday('now')
                        WHERE cycle_id = ?
                        """,
                        (time.time(), cycle_id),
                    )
                except Exception as e:
                    try:
                        logger.debug("Failed to end indexing cycle stats: %s", e)
                    except Exception:
                        pass

                if not self._stop_event.is_set():
                    sleep_seconds = 2 if cycle_had_activity else poll_interval
                    logger.info(
                        "[CYCLE #%s] cycle_had_activity=%s sleep_seconds=%s",
                        cycle_count,
                        cycle_had_activity,
                        sleep_seconds,
                    )
                    for _ in range(sleep_seconds):
                        if self._stop_event.is_set():
                            break
                        await asyncio.sleep(1)
            except Exception as e:
                # No space, DB unavailable, or service error: do not crash worker
                try:
                    logger.warning(
                        "Indexing cycle failed (will retry): %s",
                        e,
                        exc_info=True,
                    )
                except Exception:
                    pass
                try:
                    if database is not None:
                        database.disconnect()
                except Exception:
                    pass
                database = None
                db_available = False
                db_status_logged = False
                backoff = min(backoff * 2.0, backoff_max)
                try:
                    await asyncio.sleep(backoff)
                except Exception:
                    pass
                continue

    finally:
        if database is not None:
            try:
                database.disconnect()
            except Exception:
                pass

    logger.info(
        "Indexing worker stopped: %s indexed, %s errors, %s cycles",
        total_indexed,
        total_errors,
        cycle_count,
    )
    return {
        "indexed": total_indexed,
        "errors": total_errors,
        "cycles": cycle_count,
    }
