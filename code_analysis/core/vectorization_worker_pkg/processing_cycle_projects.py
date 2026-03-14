"""
Per-cycle project processing for vectorization worker.

Runs the "for project in projects" loop: re-embed, chunking query,
assign vector_id, and returns deltas and step timings.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Tuple

from ..worker_status_file import (
    STATUS_OPERATION_CHUNKING,
    STATUS_OPERATION_VECTORIZING,
    write_worker_status,
)
from .batch_processor import (
    process_chunks_missing_embedding_params,
    process_embedding_ready_chunks,
)
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
) -> Tuple[int, int, bool, float, float, float, float, int]:
    """
    Process each project in the cycle: re-embed, chunking, assign vector_id.

    Returns:
        (total_processed_delta, total_errors_delta, cycle_activity,
         cycle_step0_s, cycle_step1_query_s, cycle_step1_chunking_s,
         cycle_step2_s, cycle_chunked_files).
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
            "Processing project %s (%s) with %s pending items",
            project_id,
            root_path,
            pending_count,
        )

        faiss_manager = None
        try:
            index_path = worker.faiss_dir / f"{project_id}.bin"
            faiss_manager = FaissIndexManager(
                index_path=str(index_path),
                vector_dim=worker.vector_dim,
            )
            original_faiss_manager = getattr(worker, "faiss_manager", None)
            original_project_id = getattr(worker, "project_id", None)
            worker.faiss_manager = faiss_manager
            worker.project_id = project_id

            # Step 0: Re-embed chunks missing at least one of (embedding_model, embedding_vector)
            t0_step0 = time.time()
            write_worker_status(
                getattr(worker, "status_file_path", None),
                "reembed",
                current_file=None,
                extra={"project_id": project_id},
            )
            logger.info(
                "[STEP] Step 0: Re-embed chunks missing params (project=%s)",
                project_id,
            )
            try:
                fill_count, fill_errors = await process_chunks_missing_embedding_params(
                    worker, database
                )
                logger.info(
                    "[STEP] Step 0 done: filled=%s, errors=%s",
                    fill_count,
                    fill_errors,
                )
                if fill_count or fill_errors:
                    logger.info(
                        "Filled missing embedding params: %s updated, %s errors",
                        fill_count,
                        fill_errors,
                    )
                if fill_count > 0:
                    logger.info(
                        "[STEP] Step 5 after Step 0: process_embedding_ready_chunks "
                        "(project=%s)",
                        project_id,
                    )
                    step5_processed, step5_errors = (
                        await process_embedding_ready_chunks(worker, database)
                    )
                    logger.info(
                        "[STEP] Step 5 after Step 0 done: processed=%s, errors=%s",
                        step5_processed,
                        step5_errors,
                    )
                    if step5_processed or step5_errors:
                        logger.info(
                            "After fill: added to FAISS and set vector_id: "
                            "%s chunks, %s errors",
                            step5_processed,
                            step5_errors,
                        )
            finally:
                cycle_step0_s += time.time() - t0_step0
                worker.faiss_manager = original_faiss_manager
                worker.project_id = original_project_id

            # Step 1: Request chunking for files that need it
            write_worker_status(
                getattr(worker, "status_file_path", None),
                "chunking_query",
                current_file=None,
                extra={"project_id": project_id},
            )
            logger.info(
                "[STEP] Step 1: Query files needing chunking (project=%s, limit=%s)",
                project_id,
                worker.max_files_per_pass,
            )
            original_faiss_manager_chunking = getattr(worker, "faiss_manager", None)
            original_project_id_chunking = getattr(worker, "project_id", None)
            worker.faiss_manager = faiss_manager
            worker.project_id = project_id

            try:
                if worker.svo_client_manager:
                    circuit_state = worker.svo_client_manager.get_circuit_state()
                    state_str = getattr(circuit_state, "state", circuit_state)
                    if state_str == "open":
                        backoff_delay = worker.svo_client_manager.get_backoff_delay()
                        logger.debug(
                            "Skipping chunking requests for project %s - "
                            "circuit breaker is OPEN (backoff: %.1fs)",
                            project_id,
                            backoff_delay,
                        )
                    else:
                        try:
                            t0_step1 = time.time()
                            files_result = database.execute(
                                """
                                SELECT f.id, f.path, f.project_id
                                FROM files f
                                WHERE f.project_id = ?
                                  AND (f.deleted = 0 OR f.deleted IS NULL)
                                  AND (
                                      f.has_docstring = 1
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
                                LIMIT ?
                                """,
                                (
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
                                "[STEP] Step 1: Found %s files to chunk",
                                len(files_to_chunk),
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
                                chunked_count = (
                                    await worker._request_chunking_for_files(
                                        database, files_to_chunk
                                    )
                                )
                                cycle_step1_chunking_s += time.time() - t0_chunk
                                cycle_chunked_files += chunked_count
                                logger.info(
                                    "Requested chunking for %s files in " "project %s",
                                    chunked_count,
                                    project_id,
                                )
                        except Exception as e:
                            logger.error(
                                "Error requesting chunking for project %s: %s",
                                project_id,
                                e,
                                exc_info=True,
                            )
                else:
                    logger.debug(
                        "SVO client manager not available, skipping chunking "
                        "requests for project %s",
                        project_id,
                    )
            finally:
                worker.faiss_manager = original_faiss_manager_chunking
                worker.project_id = original_project_id_chunking

            # Step 2: Assign vector_id in FAISS for chunks that already have embeddings.
            write_worker_status(
                getattr(worker, "status_file_path", None),
                "assigning_vector_ids",
                current_file=None,
                extra={"project_id": project_id},
            )
            logger.info(
                "[STEP] Step 2: process_embedding_ready_chunks "
                "(project=%s, assign vector_id)",
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
                    "[STEP] Step 2 done: processed=%s, errors=%s, " "duration=%.3fs",
                    batch_processed,
                    batch_errors,
                    batch_duration,
                )

                delta_processed += batch_processed
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
                    """
                    UPDATE vectorization_stats
                    SET
                        chunks_processed = chunks_processed + ?,
                        chunks_failed = chunks_failed + ?,
                        total_processing_time_seconds = total_processing_time_seconds + ?,
                        last_updated = julianday('now')
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
    )
