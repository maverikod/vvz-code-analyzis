"""
Processing loop for IndexingWorker.

One cycle: discover projects with needs_chunking=1, per project take a batch of files,
call database.index_file(path, project_id). Backoff on DB unavailability.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

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

            logger.info("[CYCLE #%s] Starting indexing cycle", cycle_count)

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
                project_ids: List[str] = [
                    row["project_id"] for row in projects_data if row.get("project_id")
                ]

                if not project_ids:
                    logger.info(
                        "[CYCLE #%s] No projects with files needing indexing",
                        cycle_count,
                    )
                else:
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
                        for row in files_data:
                            path = row.get("path")
                            if not path or not project_id:
                                continue
                            try:
                                result = database.index_file(path, project_id)
                                if result.get("success"):
                                    total_indexed += 1
                                    logger.debug("Indexed %s", path)
                                else:
                                    total_errors += 1
                                    logger.warning(
                                        "Index failed for %s: %s",
                                        path,
                                        result.get("error", "unknown"),
                                    )
                            except Exception as e:
                                total_errors += 1
                                logger.warning("Index error for %s: %s", path, e)
            except Exception as e:
                logger.error("Error in indexing cycle: %s", e, exc_info=True)
                err_str = str(e).lower()
                if "database" in err_str or "connection" in err_str or "db" in err_str:
                    try:
                        database.disconnect()
                    except Exception:
                        pass
                    database = None
                    db_available = False
                    db_status_logged = False
                    backoff = 1.0
                    continue

            if not self._stop_event.is_set():
                for _ in range(poll_interval):
                    if self._stop_event.is_set():
                        break
                    await asyncio.sleep(1)

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
