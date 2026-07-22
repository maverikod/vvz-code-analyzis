"""
Per-cycle project processing for vectorization worker.

Runs the "for project in projects" loop: chunking query, chunk-only
embedding fill, assign vector_id, and returns deltas and step timings.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Tuple

from code_analysis.core.sql_portable import (WHERE_FILES_ACTIVE_F,
                                             WHERE_HAS_DOCSTRING_F,
                                             sql_julian_timestamp_now_expr)

from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY
from ..worker_status_file import (STATUS_OPERATION_CHUNKING,
                                  STATUS_OPERATION_VECTORIZING,
                                  write_worker_status)
from .batch_processor import (process_chunk_only_files,
                              process_embedding_ready_chunks)
from .timing_log import log_operation_timing

logger = logging.getLogger(__name__)


async def process_projects_in_cycle(
    worker: Any,
    database: Any,
    projects: List[Any],
    cycle_id: str,
    cycle_count: int,
    chunks_total_at_start: int,
    total_processed: int,
    total_errors: int,
) -> Tuple[int, int, bool, float, float, float, float, int, int]:
    """
    Process each project in the cycle: chunking, chunk-only embedding fill,
    assign vector_id.

    Returns:
        (total_processed_delta, total_errors_delta, cycle_activity,
         cycle_step0_s, cycle_step1_query_s, cycle_step1_chunking_s,
         cycle_step2_s, cycle_chunked_files, cycle_committed_work).
    """
    from ..faiss_manager import FaissIndexManager

    cycle_step0_s = 0.0
    cycle_step1_query_s = 0.0
    cycle_step1_chunking_s = 0.0
    cycle_step2_s = 0.0
    cycle_chunked_files = 0
    cycle_activity = False
    delta_processed = 0
    delta_errors = 0
    cycle_committed_work = 0

    _now_sql = sql_julian_timestamp_now_expr(database)

    for project in projects:
        project_id = project["project_id"]
        root_path = project["root_path"]
        pending_count = project["pending_count"]

        write_worker_status(
            getattr(worker, "status_file_path", None),
            "processing_project",
            current_file=None,
            extra={
                "project_id": project_id,
                "pending_count": pending_count,
                "root_path": str(root_path),
            },
        )
        logger.info(
            "Processing project %s (%s) with %s pending items "
            "(cat1_unchunked_files=%s cat2_embedded_no_vector=%s "
            "cat3_unembedded_chunks=%s)",
            project_id,
            root_path,
            pending_count,
            project.get("cat1_count", "?"),
            project.get("cat2_count", "?"),
            project.get("cat3_count", "?"),
        )

        faiss_manager = None
        try:
            index_path = worker.faiss_dir / f"{project_id}.bin"
            if getattr(worker, "vector_ann_backend", "faiss") != "pgvector":
                faiss_manager = FaissIndexManager(
                    index_path=str(index_path),
                    vector_dim=worker.vector_dim,
                )
            original_faiss_manager = getattr(worker, "faiss_manager", None)
            original_project_id = getattr(worker, "project_id", None)
            worker.faiss_manager = faiss_manager
            worker.project_id = project_id

            # Project-cycle Step 1: docstring chunking candidates
            write_worker_status(
                getattr(worker, "status_file_path", None),
                "chunking_query",
                current_file=None,
                extra={"project_id": project_id},
            )
            logger.info(
                "[PROJECT_CYCLE STEP 1] docstring chunking candidates project_id=%s limit=%s",
                project_id,
                worker.max_files_per_pass,
            )
            original_faiss_manager_chunking = getattr(worker, "faiss_manager", None)
            original_project_id_chunking = getattr(worker, "project_id", None)
            worker.faiss_manager = faiss_manager
            worker.project_id = project_id

            try:
                # Docstring chunking must run even without SVO: DocstringChunker persists
                # rows locally when svo_client_manager is None (see docstring_chunker_pkg).
                # Previously chunking was gated on SVO, which left code_chunks empty forever.
                if worker.svo_client_manager:
                    circuit_state = worker.svo_client_manager.get_circuit_state()
                    state_str = getattr(circuit_state, "state", circuit_state)
                    if state_str == "open":
                        backoff_delay = worker.svo_client_manager.get_backoff_delay()
                        logger.info(
                            "Circuit breaker OPEN (backoff=%.1fs) for project %s; "
                            "still running docstring chunking (local persist / per-item fallback).",
                            backoff_delay,
                            project_id,
                        )
                else:
                    logger.debug(
                        "No SVO client manager for project %s; docstring chunking "
                        "uses local AST extraction only (no chunker RPC).",
                        project_id,
                    )
                try:
                    from code_analysis.core.database.watch_dirs_partition import \
                        current_server_instance_id

                    sid = current_server_instance_id()
                    t0_step1 = time.time()
                    files_result = database.execute(
                        f"""
                        SELECT f.id, f.path, f.project_id, f.relative_path,
                               p.root_path AS project_root_path,
                               p.name AS project_name,
                               (SELECT wdp.absolute_path FROM watch_dir_paths wdp
                                WHERE wdp.server_instance_id = p.server_instance_id
                                  AND wdp.watch_dir_id = COALESCE(
                                      f.watch_dir_id, p.watch_dir_id
                                  )
                                LIMIT 1) AS watch_absolute_path
                        FROM files f
                        INNER JOIN projects p ON p.id = f.project_id
                        WHERE p.server_instance_id = ?
                          AND f.project_id = ?
                          AND {WHERE_FILES_ACTIVE_F}
                          AND (
                              {WHERE_HAS_DOCSTRING_F}
                              OR EXISTS (
                                  SELECT 1 FROM classes c
                                  WHERE c.file_id = f.id
                                    AND c.docstring IS NOT NULL
                                    AND c.docstring != ''
                              )
                              OR EXISTS (
                                  SELECT 1 FROM functions fn
                                  WHERE fn.file_id = f.id
                                    AND fn.docstring IS NOT NULL
                                    AND fn.docstring != ''
                              )
                              OR EXISTS (
                                  SELECT 1 FROM methods m
                                  JOIN classes c ON m.class_id = c.id
                                  WHERE c.file_id = f.id
                                    AND m.docstring IS NOT NULL
                                    AND m.docstring != ''
                              )
                          )
                          AND (f.needs_chunking = 1 OR NOT EXISTS (
                              SELECT 1 FROM code_chunks cc
                              WHERE cc.file_id = f.id
                          ))
                        ORDER BY f.updated_at DESC, f.id DESC
                        LIMIT ?
                        """,
                        (
                            sid,
                            project_id,
                            worker.max_files_per_pass,
                        ),
                    )
                    files_to_chunk = (
                        files_result.get("data", [])
                        if isinstance(files_result, dict)
                        else []
                    )
                    step1_query_duration = time.time() - t0_step1
                    cycle_step1_query_s += step1_query_duration
                    log_operation_timing(
                        getattr(worker, "log_timing", False),
                        logger,
                        "Step1_SELECT_files_needing_chunking",
                        step1_query_duration,
                        project_id=project_id,
                        files=len(files_to_chunk),
                    )

                    logger.info(
                        "[PROJECT_CYCLE STEP 1] selected %s file(s) to chunk project_id=%s",
                        len(files_to_chunk),
                        project_id,
                    )
                    if files_to_chunk:
                        t0_chunk = time.time()
                        write_worker_status(
                            getattr(
                                worker,
                                "status_file_path",
                                None,
                            ),
                            STATUS_OPERATION_CHUNKING,
                            current_file=None,
                            extra={
                                "project_id": project_id,
                                "files_count": len(files_to_chunk),
                            },
                        )
                        logger.info(
                            "Found %s files needing chunking in "
                            "project %s, requesting chunking...",
                            len(files_to_chunk),
                            project_id,
                        )
                        chunked_count = await worker._request_chunking_for_files(
                            database, files_to_chunk
                        )
                        cycle_step1_chunking_s += time.time() - t0_chunk
                        cycle_chunked_files += chunked_count
                        logger.info(
                            "Requested chunking for %s files in project %s",
                            chunked_count,
                            project_id,
                        )
                except Exception as e:
                    logger.error(
                        "[PROJECT_CYCLE STEP 1] docstring chunking failed project_id=%s: %s",
                        project_id,
                        e,
                        exc_info=True,
                    )
            finally:
                worker.faiss_manager = original_faiss_manager_chunking
                worker.project_id = original_project_id_chunking

            # Project-cycle Step 2: embedding-ready → FAISS / vector_id
            try:
                t0_co = time.time()
                co_updated, co_errors = await process_chunk_only_files(worker, database)
                log_operation_timing(
                    getattr(worker, "log_timing", False),
                    logger,
                    "Step1_5_chunk_only_vectorize",
                    time.time() - t0_co,
                    project_id=project_id,
                    updated=co_updated,
                    errors=co_errors,
                )
                if co_updated or co_errors:
                    logger.info(
                        "[PROJECT_CYCLE STEP 1.5] chunk_only: updated=%d errors=%d project_id=%s",
                        co_updated,
                        co_errors,
                        project_id,
                    )
                    if co_updated > 0:
                        cycle_activity = True
                cycle_committed_work += co_updated
            except Exception as e:
                logger.error(
                    "[PROJECT_CYCLE STEP 1.5] chunk_only vectorization failed project_id=%s: %s",
                    project_id,
                    e,
                    exc_info=True,
                )
            logger.info(
                "[PROJECT_CYCLE STEP 2] embedding/vectorization project_id=%s",
                project_id,
            )
            original_faiss_manager = getattr(worker, "faiss_manager", None)
            original_project_id = getattr(worker, "project_id", None)
            worker.faiss_manager = faiss_manager
            worker.project_id = project_id

            try:
                batch_start_time = time.time()
                running_p = total_processed + delta_processed
                running_e = total_errors + delta_errors
                write_worker_status(
                    getattr(worker, "status_file_path", None),
                    STATUS_OPERATION_VECTORIZING,
                    current_file=None,
                    progress_percent=(
                        round(
                            (running_p + running_e) / chunks_total_at_start * 100,
                            1,
                        )
                        if chunks_total_at_start
                        else None
                    ),
                )
                batch_processed, batch_errors = await process_embedding_ready_chunks(
                    worker, database
                )
                batch_duration = time.time() - batch_start_time
                cycle_step2_s += batch_duration
                logger.info(
                    "[PROJECT_CYCLE STEP 2] done processed=%s errors=%s duration=%.3fs "
                    "project_id=%s",
                    batch_processed,
                    batch_errors,
                    batch_duration,
                    project_id,
                )

                delta_processed += batch_processed
                cycle_committed_work += batch_processed
                delta_errors += batch_errors
                write_worker_status(
                    getattr(worker, "status_file_path", None),
                    STATUS_OPERATION_VECTORIZING,
                    current_file=None,
                    progress_percent=(
                        round(
                            (
                                total_processed
                                + delta_processed
                                + total_errors
                                + delta_errors
                            )
                            / chunks_total_at_start
                            * 100,
                            1,
                        )
                        if chunks_total_at_start
                        else None
                    ),
                )

                if batch_processed > 0:
                    cycle_activity = True

                database.execute(
                    f"""
                    UPDATE vectorization_stats
                    SET
                        chunks_processed = chunks_processed + ?,
                        chunks_failed = chunks_failed + ?,
                        total_processing_time_seconds = total_processing_time_seconds + ?,
                        last_updated = {_now_sql}
                    WHERE cycle_id = ?
                    """,
                    (
                        batch_processed,
                        batch_errors,
                        batch_duration,
                        cycle_id,
                    ),
                )
            finally:
                worker.faiss_manager = original_faiss_manager
                worker.project_id = original_project_id

        except Exception as e:
            logger.error(
                "Error processing project %s: %s",
                project_id,
                e,
                exc_info=True,
            )
        finally:
            try:
                if faiss_manager is not None:
                    faiss_manager = None
            except Exception:
                pass

    return (
        delta_processed,
        delta_errors,
        cycle_activity,
        cycle_step0_s,
        cycle_step1_query_s,
        cycle_step1_chunking_s,
        cycle_step2_s,
        cycle_chunked_files,
        cycle_committed_work,
    )
