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
from pathlib import Path
from typing import Any, Dict, Optional

from ..worker_status_file import (
    STATUS_OPERATION_IDLE,
    STATUS_OPERATION_INDEXING,
    STATUS_OPERATION_POLLING,
    write_worker_status,
)
from ..vectorization_worker_pkg.timing_log import log_operation_timing
from ..worker_project_activity import (
    heartbeat_project_activity,
    release_project_activity,
    try_acquire_project_activity,
)
from code_analysis.core.sql_portable import (
    WHERE_FILES_ACTIVE,
    WHERE_FILES_ACTIVE_F,
    WHERE_PROCESSING_ACTIVE_P,
    sql_julian_timestamp_now_expr,
)
from code_analysis.core.worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY
from code_analysis.core.docs_indexing_config_load import (
    load_docs_indexing_from_config_path,
)
from code_analysis.core.docs_indexing_defaults import DOCS_INDEX_FILE_SUFFIXES
from code_analysis.core.docs_indexing_eligibility import is_docs_markdown_eligible
from code_analysis.core.database.file_edit_lock import editing_lock_holder_is_alive
from code_analysis.core.runtime_lock_sessions import register_runtime_session

logger = logging.getLogger(__name__)

# Projects with files needing indexing, excluding processing_paused projects.
# Order: projects with the most recently updated pending file first (stable tie-break on project id).
INDEXING_PROJECT_DISCOVERY_SQL = (
    "SELECT f.project_id FROM files f "
    "INNER JOIN projects p ON p.id = f.project_id "
    "WHERE f.project_id IS NOT NULL AND "
    + WHERE_FILES_ACTIVE_F
    + " AND f.needs_chunking = 1 AND "
    + WHERE_PROCESSING_ACTIVE_P
    + " GROUP BY f.project_id "
    + "ORDER BY MAX(f.updated_at) DESC, f.project_id DESC"
)

# Project activity lease (Step 16): long batches may exceed TTL without heartbeat.
_INDEXER_LEASE_TTL_S = 120.0


def _docs_relative_path_from_row_path(*, path: str, project_root: Path) -> str:
    """
    Project-relative POSIX path for ``is_docs_markdown_eligible``.

    ``files.path`` is often project-relative; resolving ``Path(path)`` alone uses
    process cwd and breaks ``relative_to(project_root)``. Join project root first
    when the path is not absolute.
    """
    raw = (path or "").strip().replace("\\", "/")
    if not raw:
        return ""
    try:
        pr = project_root.resolve()
        p = Path(raw)
        abs_p = p.resolve() if p.is_absolute() else (pr / p).resolve()
        return str(abs_p.relative_to(pr))
    except (OSError, ValueError):
        return ""


async def process_cycle(self: Any, poll_interval: int = 30) -> Dict[str, Any]:
    """Run indexing cycles until stop: query projects with needs_chunking=1, index batch per project.

    Discovery: project_id from files joined to projects where processing is not paused
    and (deleted=0 OR deleted IS NULL) AND needs_chunking=1, grouped by project_id,
    ORDER BY MAX(updated_at) DESC (freshest pending work first). Per project: SELECT id, path, project_id FROM files
    WHERE project_id=? AND (deleted=0 OR deleted IS NULL) AND needs_chunking=1
    ORDER BY updated_at DESC, id DESC LIMIT ?. For each file call database.index_file(path, project_id).
    Driver clears needs_chunking after success. Backoff 1–60s when DB unavailable.

    Args:
        poll_interval: Seconds between cycles (default 30).

    Returns:
        Stats dict when stopped: indexed, errors, cycles.
    """
    from ..database_client.factory import create_worker_database_client

    cfg_raw = getattr(self, "config_path", None)
    if not cfg_raw:
        logger.error(
            "IndexingWorker requires config_path (server config.json) "
            "for the universal database driver."
        )
        return {
            "indexed": 0,
            "errors": 1,
            "cycles": 0,
        }
    cfg_path = Path(cfg_raw)

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
                    database = create_worker_database_client(
                        config_path=cfg_path,
                    )
                    database.connect()
                    register_runtime_session(database, role="indexing_worker")
                    try:
                        database.execute(
                            "SELECT 1",
                            None,
                            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
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
                logger.debug("[CYCLE #%s] Starting indexing cycle", cycle_count)
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
            log_timing = getattr(self, "log_timing", False)
            _now_sql = sql_julian_timestamp_now_expr(database)

            try:
                # Start indexing_worker_stats cycle (same pattern as vectorization)
                database.execute(
                    f"""
                    UPDATE indexing_worker_stats
                    SET cycle_end_time = ?, last_updated = {_now_sql}
                    WHERE cycle_end_time IS NULL
                    """,
                    (cycle_start_time,),
                    priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                )
                discovery_start = time.time()
                files_total_result = database.execute(
                    """
                    SELECT COUNT(*) as count FROM files
                    WHERE """
                    + WHERE_FILES_ACTIVE
                    + """ AND needs_chunking = 1
                    """,
                    None,
                    priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                )
                files_total_at_start = 0
                if isinstance(files_total_result, dict) and files_total_result.get(
                    "data"
                ):
                    row = files_total_result["data"][0]
                    files_total_at_start = row.get("count", 0) or 0
                logger.debug(
                    "[CYCLE #%s] files_total_at_start (needs_chunking=1)=%s",
                    cycle_count,
                    files_total_at_start,
                )
                database.execute(
                    f"""
                    INSERT INTO indexing_worker_stats (
                        cycle_id, cycle_start_time, files_total_at_start,
                        files_indexed, files_failed,
                        total_processing_time_seconds, average_processing_time_seconds,
                        last_updated
                    ) VALUES (?, ?, ?, 0, 0, 0.0, NULL, {_now_sql})
                    """,
                    (cycle_id, cycle_start_time, files_total_at_start),
                    priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                )

                try:
                    projects_result = database.execute(
                        INDEXING_PROJECT_DISCOVERY_SQL,
                        None,
                        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                    )
                    projects_data = (
                        projects_result.get("data", [])
                        if isinstance(projects_result, dict)
                        else []
                    )
                    project_ids: list[str] = []
                    _seen_pid: set[str] = set()
                    for row in projects_data:
                        raw = row.get("project_id")
                        if raw is None:
                            continue
                        pid = str(raw).strip()
                        if not pid or pid in _seen_pid:
                            continue
                        _seen_pid.add(pid)
                        project_ids.append(pid)
                    discovery_duration = time.time() - discovery_start
                    log_operation_timing(
                        log_timing,
                        logger,
                        "discovery",
                        discovery_duration,
                        files_total=files_total_at_start,
                        project_count=len(project_ids),
                    )
                    logger.debug(
                        "[CYCLE #%s] project_ids count=%s (batch_size=%s)",
                        cycle_count,
                        len(project_ids),
                        self.batch_size,
                    )

                    if not project_ids:
                        logger.debug(
                            "[CYCLE #%s] No projects with files needing indexing",
                            cycle_count,
                        )
                    else:
                        cycle_indexed = 0
                        cycle_had_activity = False
                        cycle_files_indexed = 0
                        cycle_files_failed = 0
                        cycle_total_time = 0.0
                        owner_id = self._project_activity_owner_id
                        cfg_raw_path = getattr(self, "config_path", None)
                        cfg_worker_path: Optional[Path] = (
                            Path(cfg_raw_path).expanduser().resolve()
                            if cfg_raw_path
                            else None
                        )
                        docs_cfg_loaded = (
                            load_docs_indexing_from_config_path(cfg_worker_path)
                            if cfg_worker_path is not None and cfg_worker_path.is_file()
                            else None
                        )
                        srv_cfg_str = (
                            str(cfg_worker_path)
                            if cfg_worker_path is not None and cfg_worker_path.is_file()
                            else None
                        )
                        for project_id in project_ids:
                            if not try_acquire_project_activity(
                                database,
                                project_id,
                                "indexer",
                                owner_id,
                                "indexer_processing",
                                _INDEXER_LEASE_TTL_S,
                                rpc_priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                            ):
                                logger.debug(
                                    "[WORKER_COORD] indexer skip project_id=%s "
                                    "(lease busy; next cycle)",
                                    project_id,
                                )
                                continue
                            errors_to_clear: list[tuple[str, str]] = []
                            errors_to_insert: list[tuple[str, str, str, str]] = []
                            try:
                                files_result = database.execute(
                                    "SELECT id, path, project_id, editing_pid FROM files "
                                    "WHERE project_id = ? AND "
                                    + WHERE_FILES_ACTIVE
                                    + " "
                                    "AND needs_chunking = 1 "
                                    "ORDER BY updated_at DESC, id DESC LIMIT ?",
                                    (project_id, self.batch_size),
                                    priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                                )
                                files_data = (
                                    files_result.get("data", [])
                                    if isinstance(files_result, dict)
                                    else []
                                )
                                logger.debug(
                                    "[CYCLE #%s] project_id=%s files_batch=%s",
                                    cycle_count,
                                    project_id[:8] if project_id else None,
                                    len(files_data),
                                )
                                proj_root_for_docs: Optional[Path] = None
                                proj_row = database.execute(
                                    "SELECT root_path FROM projects WHERE id = ?",
                                    (project_id,),
                                    priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                                )
                                if isinstance(proj_row, dict):
                                    pd = proj_row.get("data") or []
                                    if pd:
                                        try:
                                            proj_root_for_docs = Path(
                                                str(pd[0].get("root_path"))
                                            ).resolve()
                                        except Exception:
                                            proj_root_for_docs = None
                                for row in files_data:
                                    path = row.get("path")
                                    if not path or not project_id:
                                        continue
                                    # Skip rows where path is absolute (legacy defect until watcher dedup).
                                    if path.startswith("/") or (
                                        len(path) > 2
                                        and path[1] == ":"
                                        and path[2] in "\\/"
                                    ):
                                        logger.error(
                                            "[INDEXER_ABSPATH] Skipping file with absolute path in DB: "
                                            "file_id=%s project_id=%s path=%s — "
                                            "run file_watcher to deduplicate (abspath_dedup).",
                                            row.get("id"),
                                            project_id,
                                            path,
                                        )
                                        errors_to_insert.append(
                                            (
                                                project_id,
                                                path,
                                                "abspath_skipped",
                                                f"Absolute path in DB; deduplication required: {path}",
                                            )
                                        )
                                        heartbeat_project_activity(
                                            database,
                                            project_id,
                                            "indexer",
                                            owner_id,
                                            "indexer_processing",
                                            _INDEXER_LEASE_TTL_S,
                                            rpc_priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                                        )
                                        continue
                                    if editing_lock_holder_is_alive(
                                        row.get("editing_pid")
                                    ):
                                        logger.debug(
                                            "Skipping file_id=%s path=%s: live edit lock pid=%s",
                                            row.get("id"),
                                            path[:120] if path else "",
                                            row.get("editing_pid"),
                                        )
                                        heartbeat_project_activity(
                                            database,
                                            project_id,
                                            "indexer",
                                            owner_id,
                                            "indexer_processing",
                                            _INDEXER_LEASE_TTL_S,
                                            rpc_priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                                        )
                                        continue
                                    is_python = path.endswith(".py") or path.endswith(
                                        ".pyi"
                                    )
                                    is_docs_file_eligible = False
                                    doc_suffix = Path(path).suffix.lower()
                                    if (
                                        doc_suffix in DOCS_INDEX_FILE_SUFFIXES
                                        and docs_cfg_loaded is not None
                                        and proj_root_for_docs is not None
                                    ):
                                        rel_docs = _docs_relative_path_from_row_path(
                                            path=path,
                                            project_root=proj_root_for_docs,
                                        )
                                        verdict_docs = is_docs_markdown_eligible(
                                            docs_indexing=docs_cfg_loaded,
                                            relative_path=rel_docs,
                                            file_exists=True,
                                            is_deleted=False,
                                        )
                                        is_docs_file_eligible = verdict_docs.eligible

                                    if not is_python and not is_docs_file_eligible:
                                        try:
                                            database.execute(
                                                "UPDATE files SET needs_chunking = 0 WHERE id = ?",
                                                (row.get("id"),),
                                                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                                            )
                                        except Exception:
                                            pass
                                        heartbeat_project_activity(
                                            database,
                                            project_id,
                                            "indexer",
                                            owner_id,
                                            "indexer_processing",
                                            _INDEXER_LEASE_TTL_S,
                                            rpc_priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                                        )
                                        continue
                                    file_start = time.time()
                                    progress_pct = (
                                        round(
                                            cycle_indexed / files_total_at_start * 100,
                                            1,
                                        )
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
                                        idx_kw = (
                                            dict(
                                                docs_indexing=docs_cfg_loaded,
                                                server_config_path=srv_cfg_str,
                                            )
                                            if is_docs_file_eligible
                                            else {}
                                        )
                                        result = database.index_file(
                                            path,
                                            project_id,
                                            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                                            **idx_kw,
                                        )
                                        elapsed = time.time() - file_start
                                        log_operation_timing(
                                            log_timing,
                                            logger,
                                            "index_file",
                                            elapsed,
                                            path=path[:80] if path else "",
                                            success=result.get("success", False),
                                        )
                                        if result.get("success"):
                                            total_indexed += 1
                                            logger.debug("Indexed %s", path)
                                            errors_to_clear.append((project_id, path))
                                            cycle_files_indexed += 1
                                            cycle_total_time += elapsed
                                        else:
                                            total_errors += 1
                                            err_msg = result.get("error", "unknown")
                                            logger.warning(
                                                "Index failed for %s: %s",
                                                path,
                                                err_msg,
                                            )
                                            errors_to_insert.append(
                                                (
                                                    project_id,
                                                    path,
                                                    "index_error",
                                                    err_msg,
                                                )
                                            )
                                            cycle_files_failed += 1
                                            cycle_total_time += elapsed
                                            if "temp_files" in (err_msg or ""):
                                                logger.error(
                                                    "[indexing_errors] Stored temp_files-related error (caller=index_file): %s",
                                                    err_msg,
                                                )
                                        cycle_indexed += 1
                                        cycle_had_activity = True
                                    except Exception as e:
                                        total_errors += 1
                                        cycle_indexed += 1
                                        cycle_had_activity = True
                                        elapsed = time.time() - file_start
                                        err_str = str(e)
                                        errors_to_insert.append(
                                            (
                                                project_id,
                                                path,
                                                "index_exception",
                                                err_str,
                                            )
                                        )
                                        cycle_files_failed += 1
                                        cycle_total_time += elapsed
                                        log_operation_timing(
                                            log_timing,
                                            logger,
                                            "index_file",
                                            elapsed,
                                            path=path[:80] if path else "",
                                            success=False,
                                            error=err_str[:60],
                                        )
                                        try:
                                            logger.warning(
                                                "Index error for %s: %s", path, e
                                            )
                                        except Exception:
                                            pass
                                        if "temp_files" in err_str:
                                            logger.error(
                                                "[indexing_errors] Stored temp_files-related exception (caller=index_file): %s",
                                                err_str,
                                            )
                                    heartbeat_project_activity(
                                        database,
                                        project_id,
                                        "indexer",
                                        owner_id,
                                        "indexer_processing",
                                        _INDEXER_LEASE_TTL_S,
                                        rpc_priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                                    )
                                project_batch: list[
                                    tuple[str, tuple[Any, ...] | None]
                                ] = []
                                for p, file_path in errors_to_clear:
                                    project_batch.append(
                                        (
                                            "DELETE FROM indexing_errors WHERE project_id = ? AND file_path = ?",
                                            (p, file_path),
                                        )
                                    )
                                now_err_sql = sql_julian_timestamp_now_expr(database)
                                for p, file_path, typ, msg in errors_to_insert:
                                    project_batch.append(
                                        (
                                            "INSERT INTO indexing_errors "
                                            "(id, project_id, file_path, error_type, error_message, created_at) "
                                            f"VALUES (?, ?, ?, ?, ?, {now_err_sql}) "
                                            "ON CONFLICT (project_id, file_path) DO UPDATE SET "
                                            "error_type = excluded.error_type, "
                                            "error_message = excluded.error_message, "
                                            "created_at = excluded.created_at",
                                            (
                                                str(uuid.uuid4()),
                                                p,
                                                file_path,
                                                typ,
                                                msg,
                                            ),
                                        )
                                    )
                                if project_batch:
                                    database.execute_batch(
                                        project_batch,
                                        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                                    )
                            finally:
                                release_project_activity(
                                    database,
                                    project_id,
                                    "indexer",
                                    owner_id,
                                    rpc_priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                                )
                        total_files = cycle_files_indexed + cycle_files_failed
                        avg_time = (
                            cycle_total_time / total_files if total_files > 0 else None
                        )
                        database.execute(
                            "UPDATE indexing_worker_stats SET "
                            "files_indexed = ?, files_failed = ?, "
                            "total_processing_time_seconds = ?, "
                            "average_processing_time_seconds = ?, "
                            f"last_updated = {_now_sql} WHERE cycle_id = ?",
                            (
                                cycle_files_indexed,
                                cycle_files_failed,
                                cycle_total_time,
                                avg_time,
                                cycle_id,
                            ),
                            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                        )
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
                cycle_duration = time.time() - cycle_start_time
                log_operation_timing(
                    log_timing,
                    logger,
                    "cycle_total",
                    cycle_duration,
                    cycle_id=cycle_count,
                    had_activity=cycle_had_activity,
                )
                try:
                    database.execute(
                        f"""
                        UPDATE indexing_worker_stats
                        SET cycle_end_time = ?, last_updated = {_now_sql}
                        WHERE cycle_id = ?
                        """,
                        (time.time(), cycle_id),
                        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                    )
                except Exception as e:
                    try:
                        logger.debug("Failed to end indexing cycle stats: %s", e)
                    except Exception:
                        pass

                if not self._stop_event.is_set():
                    sleep_seconds = 2 if cycle_had_activity else poll_interval
                    logger.debug(
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
