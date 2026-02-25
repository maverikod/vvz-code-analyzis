"""
Processing loop for VectorizationWorker.

This module holds the outer cycle loop (interval between DB work checks) and
delegates batch processing to batch_processor. Chunker is called via WebSocket
only (no HTTP polling). Status "cycle_start" = starting a cycle (query DB for work).

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
    STATUS_OPERATION_CHUNKING,
    STATUS_OPERATION_IDLE,
    STATUS_OPERATION_POLLING,
    STATUS_OPERATION_VECTORIZING,
    write_worker_status,
)
from .batch_processor import (
    process_chunks_missing_embedding_params,
    process_embedding_ready_chunks,
)
from .timing_log import log_operation_timing

logger = logging.getLogger(__name__)


async def process_chunks(self, poll_interval: int = 30) -> Dict[str, Any]:
    """
    Process non-vectorized chunks in continuous loop; cycle every poll_interval seconds.

    Universal worker that processes all projects from database.
    Worker works only with database - no filesystem access, no watch_dirs.
    Worker periodically queries database to discover projects with files/chunks needing vectorization.

    Runs indefinitely, checking for chunks to vectorize at specified intervals.
    Also requests chunking for files that need chunking.

    Handles database unavailability gracefully:
    - Checks database availability before each cycle
    - Logs status changes only (not on every cycle)
    - Continues working when database becomes available again

    Args:
        poll_interval: Interval in seconds between worker cycles (default: 30)

    Returns:
        Dictionary with processing statistics (only when stopped)
    """
    from ..database_client.client import DatabaseClient
    from ..faiss_manager import FaissIndexManager

    if not self.svo_client_manager:
        logger.warning("SVO client manager not available, skipping vectorization")
        return {"processed": 0, "errors": 0}

    # Get socket path for database driver
    if not self.socket_path:
        from ..constants import DEFAULT_DB_DRIVER_SOCKET_DIR
        from pathlib import Path

        db_name = Path(self.db_path).stem
        socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
        socket_dir.mkdir(parents=True, exist_ok=True)
        socket_path = str(socket_dir / f"{db_name}_driver.sock")
    else:
        socket_path = self.socket_path
    logger.info(
        "[VECTORIZATION] Database socket_path=%s (db_path=%s)",
        socket_path,
        getattr(self, "db_path", None),
    )

    # Track database availability status
    db_available = False
    db_status_logged = False  # Track if we've logged the current status

    database: Any = None
    total_processed = 0
    total_errors = 0
    cycle_count = 0

    backoff = 1.0
    backoff_max = 60.0

    try:
        logger.info(
            f"Starting universal vectorization worker, "
            f"poll interval: {poll_interval}s"
        )

        while not self._stop_event.is_set():
            cycle_count += 1

            # Check database availability
            if database is None or not db_available:
                try:
                    logger.debug(
                        "[VECTORIZATION] Creating DatabaseClient(socket_path=%s)",
                        socket_path,
                    )
                    database = DatabaseClient(socket_path=socket_path)
                    database.connect()
                    # Test connection with a simple query
                    try:
                        logger.debug(
                            "[VECTORIZATION] Testing connection with list_projects()"
                        )
                        database.list_projects()
                        # Connection successful
                        if not db_available:
                            # Status changed: unavailable -> available
                            logger.info("✅ Database is now available")
                            db_available = True
                            db_status_logged = True
                            backoff = 1.0  # Reset backoff
                        else:
                            db_status_logged = False  # Already logged as available
                    except Exception as e:
                        # Connection failed
                        if db_available:
                            # Status changed: available -> unavailable
                            logger.warning(f"⚠️  Database is now unavailable: {e}")
                            db_available = False
                            db_status_logged = True
                        elif not db_status_logged:
                            # First time logging unavailability
                            logger.warning(f"⚠️  Database is unavailable: {e}")
                            db_status_logged = True
                        else:
                            # Already logged, don't spam
                            db_status_logged = False

                        try:
                            database.disconnect()
                        except Exception:
                            pass
                        database = None

                        # Wait with backoff before retrying
                        logger.debug(
                            f"Retrying database connection in {backoff:.1f}s..."
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2.0, backoff_max)
                        continue
                except Exception as e:
                    # Failed to create database connection
                    if db_available:
                        # Status changed: available -> unavailable
                        logger.warning(f"⚠️  Database is now unavailable: {e}")
                        db_available = False
                        db_status_logged = True
                    elif not db_status_logged:
                        # First time logging unavailability
                        logger.warning(f"⚠️  Database is unavailable: {e}")
                        db_status_logged = True
                    else:
                        # Already logged, don't spam
                        db_status_logged = False

                    # Wait with backoff before retrying
                    logger.debug(f"Retrying database connection in {backoff:.1f}s...")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, backoff_max)
                    continue

            # Database is available, proceed with cycle
            logger.info(
                "[CYCLE #%s] Loop iteration start (database available)",
                cycle_count,
            )
            write_worker_status(
                getattr(self, "status_file_path", None),
                STATUS_OPERATION_POLLING,
                current_file=None,
            )
            logger.info(f"[CYCLE #{cycle_count}] Starting vectorization cycle")
            logger.info(f"[STEP] Cycle #{cycle_count} started")

            # Start worker statistics cycle
            # Use execute() for worker stats methods that are not yet in DatabaseClient
            cycle_id = str(uuid.uuid4())
            cycle_start_time = time.time()
            logger.info(
                "[CYCLE #%s] Updating vectorization_stats (mark old cycles ended)...",
                cycle_count,
            )
            # Mark any old active cycles as ended
            database.execute(
                """
                UPDATE vectorization_stats
                SET cycle_end_time = ?, last_updated = julianday('now')
                WHERE cycle_end_time IS NULL
                """,
                (cycle_start_time,),
            )

            # Get total chunks count at start (exclude skipped: too short / unvectorizable)
            chunks_result = database.execute(
                """SELECT COUNT(*) as count FROM code_chunks
                   WHERE vector_id IS NULL
                     AND (vectorization_skipped IS NULL OR vectorization_skipped = 0)""",
                None,
            )
            # execute() returns dict with "data" key containing list of rows
            chunks_data = (
                chunks_result.get("data", []) if isinstance(chunks_result, dict) else []
            )
            chunks_total_at_start = chunks_data[0].get("count", 0) if chunks_data else 0

            # Get total files count at start
            files_result = database.execute(
                "SELECT COUNT(*) as count FROM files WHERE (deleted = 0 OR deleted IS NULL)",
                None,
            )
            files_data = (
                files_result.get("data", []) if isinstance(files_result, dict) else []
            )
            files_total_at_start = files_data[0].get("count", 0) if files_data else 0

            # Get vectorized files count
            vectorized_result = database.execute(
                """
                SELECT COUNT(DISTINCT f.id) as count
                FROM files f
                INNER JOIN code_chunks cc ON f.id = cc.file_id
                WHERE (f.deleted = 0 OR f.deleted IS NULL)
                AND cc.vector_id IS NOT NULL
                """,
                None,
            )
            vectorized_data = (
                vectorized_result.get("data", [])
                if isinstance(vectorized_result, dict)
                else []
            )
            files_vectorized = (
                vectorized_data[0].get("count", 0) if vectorized_data else 0
            )

            # Insert new cycle record
            database.execute(
                """
                INSERT INTO vectorization_stats (
                    cycle_id, cycle_start_time, chunks_total_at_start,
                    files_total_at_start, files_vectorized, last_updated
                ) VALUES (?, ?, ?, ?, ?, julianday('now'))
                """,
                (
                    cycle_id,
                    cycle_start_time,
                    chunks_total_at_start,
                    files_total_at_start,
                    files_vectorized,
                ),
            )
            cycle_start_time = time.time()

            cycle_activity = False

            # Get projects with files/chunks needing vectorization (sorted by count, smallest first)
            try:
                logger.info(
                    "[CYCLE #%s] Querying projects with pending items (execute)...",
                    cycle_count,
                )
                write_worker_status(
                    getattr(self, "status_file_path", None),
                    "querying_projects",
                    current_file=None,
                    extra={"cycle": cycle_count},
                )
                # Use execute() for complex query (can be slow on large DB)
                projects_result = database.execute(
                    """
                    SELECT 
                        p.id AS project_id,
                        p.root_path,
                        (
                            (SELECT COUNT(DISTINCT f.id)
                             FROM files f
                             WHERE f.project_id = p.id
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
                               AND NOT EXISTS (
                                   SELECT 1 FROM code_chunks cc 
                                   WHERE cc.file_id = f.id
                               ))
                            +
                            (SELECT COUNT(cc.id)
                             FROM code_chunks cc
                             INNER JOIN files f ON cc.file_id = f.id
                             WHERE cc.project_id = p.id
                               AND (f.deleted = 0 OR f.deleted IS NULL)
                               AND cc.embedding_vector IS NOT NULL
                               AND cc.vector_id IS NULL)
                            +
                            (SELECT COUNT(cc.id)
                             FROM code_chunks cc
                             INNER JOIN files f ON cc.file_id = f.id
                             WHERE cc.project_id = p.id
                               AND (f.deleted = 0 OR f.deleted IS NULL)
                               AND cc.vector_id IS NULL
                               AND (cc.embedding_vector IS NULL OR cc.embedding_model IS NULL)
                               AND (cc.vectorization_skipped IS NULL OR cc.vectorization_skipped = 0))
                        ) AS pending_count
                    FROM projects p
                    WHERE (
                        (SELECT COUNT(DISTINCT f.id)
                         FROM files f
                         WHERE f.project_id = p.id
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
                           AND NOT EXISTS (
                               SELECT 1 FROM code_chunks cc 
                               WHERE cc.file_id = f.id
                           ))
                        +
                        (SELECT COUNT(cc.id)
                         FROM code_chunks cc
                         INNER JOIN files f ON cc.file_id = f.id
                         WHERE cc.project_id = p.id
                           AND (f.deleted = 0 OR f.deleted IS NULL)
                           AND cc.embedding_vector IS NOT NULL
                           AND cc.vector_id IS NULL)
                        +
                        (SELECT COUNT(cc.id)
                         FROM code_chunks cc
                         INNER JOIN files f ON cc.file_id = f.id
                         WHERE cc.project_id = p.id
                           AND (f.deleted = 0 OR f.deleted IS NULL)
                           AND cc.vector_id IS NULL
                           AND (cc.embedding_vector IS NULL OR cc.embedding_model IS NULL)
                           AND (cc.vectorization_skipped IS NULL OR cc.vectorization_skipped = 0))
                    ) > 0
                    ORDER BY pending_count ASC
                    """,
                    None,
                )
                # Extract data from result - execute() returns dict with "data" key
                # execute() now returns full driver result: {"affected_rows": ..., "lastrowid": ..., "data": [...]}
                projects = (
                    projects_result.get("data", [])
                    if isinstance(projects_result, dict)
                    else []
                )
                logger.info(
                    "[CYCLE #%s] Projects query returned: %d project(s)",
                    cycle_count,
                    len(projects),
                )
                if projects:
                    logger.info(
                        f"[CYCLE #{cycle_count}] Found {len(projects)} projects with pending items: {projects}"
                    )
                if not projects:
                    logger.info(
                        "[CYCLE #%s] No projects with pending items - no work this cycle",
                        cycle_count,
                    )
                    write_worker_status(
                        getattr(self, "status_file_path", None),
                        STATUS_OPERATION_IDLE,
                        current_file=None,
                        extra={"reason": "no_pending_projects"},
                    )
                    # Update statistics even if no projects (0 processed)
                    # Use execute() for update_vectorization_stats
                    database.execute(
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
                        (0, 0, 0, 0.0, cycle_id),
                    )
                else:
                    logger.info(
                        f"[CYCLE #{cycle_count}] Found {len(projects)} projects with pending items: "
                        f"{[(p['project_id'], p['pending_count']) for p in projects]}"
                    )

                    # Accumulate step timings for cycle summary (when cycle_activity)
                    cycle_step0_s = 0.0
                    cycle_step1_query_s = 0.0
                    cycle_step1_chunking_s = 0.0
                    cycle_step2_s = 0.0
                    cycle_step3_s = 0.0
                    cycle_chunked_files = 0

                    # Process each project sequentially
                    for project in projects:
                        project_id = project["project_id"]
                        root_path = project["root_path"]
                        pending_count = project["pending_count"]

                        write_worker_status(
                            getattr(self, "status_file_path", None),
                            "processing_project",
                            current_file=None,
                            extra={
                                "project_id": project_id,
                                "pending_count": pending_count,
                                "root_path": str(root_path),
                            },
                        )
                        logger.info(
                            f"Processing project {project_id} ({root_path}) with {pending_count} pending items"
                        )

                        try:
                            # Create project-scoped FAISS manager
                            index_path = self.faiss_dir / f"{project_id}.bin"
                            faiss_manager = FaissIndexManager(
                                index_path=str(index_path),
                                vector_dim=self.vector_dim,
                            )
                            original_faiss_manager = getattr(
                                self, "faiss_manager", None
                            )
                            original_project_id = getattr(self, "project_id", None)
                            self.faiss_manager = faiss_manager
                            self.project_id = project_id

                            # Step 0: Re-embed chunks missing at least one of (embedding_model, embedding_vector)
                            t0_step0 = time.time()
                            write_worker_status(
                                getattr(self, "status_file_path", None),
                                "reembed",
                                current_file=None,
                                extra={"project_id": project_id},
                            )
                            logger.info(
                                f"[STEP] Step 0: Re-embed chunks missing params (project={project_id})"
                            )
                            try:
                                fill_count, fill_errors = (
                                    await process_chunks_missing_embedding_params(
                                        self, database
                                    )
                                )
                                logger.info(
                                    f"[STEP] Step 0 done: filled={fill_count}, errors={fill_errors}"
                                )
                                if fill_count or fill_errors:
                                    logger.info(
                                        f"Filled missing embedding params: {fill_count} updated, {fill_errors} errors"
                                    )
                                # Step 5 (mandatory): add to index and batch update after writing to DB
                                if fill_count > 0:
                                    logger.info(
                                        f"[STEP] Step 5 after Step 0: process_embedding_ready_chunks (project={project_id})"
                                    )
                                    step5_processed, step5_errors = (
                                        await process_embedding_ready_chunks(
                                            self, database
                                        )
                                    )
                                    logger.info(
                                        f"[STEP] Step 5 after Step 0 done: processed={step5_processed}, errors={step5_errors}"
                                    )
                                    if step5_processed or step5_errors:
                                        logger.info(
                                            f"After fill: added to FAISS and set vector_id: {step5_processed} chunks, {step5_errors} errors"
                                        )
                            finally:
                                cycle_step0_s += time.time() - t0_step0
                                self.faiss_manager = original_faiss_manager
                                self.project_id = original_project_id

                            # Step 1: Request chunking for files that need it
                            write_worker_status(
                                getattr(self, "status_file_path", None),
                                "chunking_query",
                                current_file=None,
                                extra={"project_id": project_id},
                            )
                            logger.info(
                                f"[STEP] Step 1: Query files needing chunking (project={project_id}, limit={self.max_files_per_pass})"
                            )
                            # Skip chunking requests if circuit breaker is open
                            # Set faiss_manager and project_id so Step 5 inside chunking sees correct project
                            original_faiss_manager_chunking = getattr(
                                self, "faiss_manager", None
                            )
                            original_project_id_chunking = getattr(
                                self, "project_id", None
                            )
                            self.faiss_manager = faiss_manager
                            self.project_id = project_id

                            try:
                                if self.svo_client_manager:
                                    circuit_state = (
                                        self.svo_client_manager.get_circuit_state()
                                    )
                                    if circuit_state == "open":
                                        backoff_delay = (
                                            self.svo_client_manager.get_backoff_delay()
                                        )
                                        logger.debug(
                                            f"Skipping chunking requests for project {project_id} - "
                                            f"circuit breaker is OPEN (backoff: {backoff_delay:.1f}s)"
                                        )
                                    else:
                                        try:
                                            # Use execute() for get_files_needing_chunking
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
                                                (project_id, self.max_files_per_pass),
                                            )
                                            # Extract data from result - execute() returns dict with "data" key
                                            files_to_chunk = (
                                                files_result.get("data", [])
                                                if isinstance(files_result, dict)
                                                else []
                                            )
                                            step1_query_duration = (
                                                time.time() - t0_step1
                                            )
                                            cycle_step1_query_s += step1_query_duration
                                            log_operation_timing(
                                                getattr(self, "log_timing", False),
                                                logger,
                                                "Step1_SELECT_files_needing_chunking",
                                                step1_query_duration,
                                                project_id=project_id,
                                                files=len(files_to_chunk),
                                            )

                                            logger.info(
                                                f"[STEP] Step 1: Found {len(files_to_chunk)} files to chunk"
                                            )
                                            if files_to_chunk:
                                                t0_chunk = time.time()
                                                write_worker_status(
                                                    getattr(
                                                        self,
                                                        "status_file_path",
                                                        None,
                                                    ),
                                                    STATUS_OPERATION_CHUNKING,
                                                    current_file=None,
                                                    extra={
                                                        "project_id": project_id,
                                                        "files_count": len(
                                                            files_to_chunk
                                                        ),
                                                    },
                                                )
                                                logger.info(
                                                    f"Found {len(files_to_chunk)} files needing chunking in project {project_id}, "
                                                    "requesting chunking..."
                                                )
                                                chunked_count = await self._request_chunking_for_files(
                                                    database, files_to_chunk
                                                )
                                                cycle_step1_chunking_s += (
                                                    time.time() - t0_chunk
                                                )
                                                cycle_chunked_files += chunked_count
                                                logger.info(
                                                    f"Requested chunking for {chunked_count} files in project {project_id}"
                                                )
                                        except Exception as e:
                                            logger.error(
                                                f"Error requesting chunking for project {project_id}: {e}",
                                                exc_info=True,
                                            )
                                else:
                                    # No SVO client manager, skip chunking
                                    logger.debug(
                                        f"SVO client manager not available, skipping chunking requests for project {project_id}"
                                    )
                            finally:
                                # Restore original faiss_manager and project_id
                                self.faiss_manager = original_faiss_manager_chunking
                                self.project_id = original_project_id_chunking

                            # Step 2: Assign vector_id in FAISS for chunks that already have embeddings.
                            write_worker_status(
                                getattr(self, "status_file_path", None),
                                "assigning_vector_ids",
                                current_file=None,
                                extra={"project_id": project_id},
                            )
                            logger.info(
                                f"[STEP] Step 2: process_embedding_ready_chunks (project={project_id}, assign vector_id)"
                            )
                            # Temporarily set faiss_manager for batch processor
                            original_faiss_manager = getattr(
                                self, "faiss_manager", None
                            )
                            original_project_id = getattr(self, "project_id", None)
                            self.faiss_manager = faiss_manager
                            self.project_id = project_id

                            try:
                                batch_start_time = time.time()
                                write_worker_status(
                                    getattr(self, "status_file_path", None),
                                    STATUS_OPERATION_VECTORIZING,
                                    current_file=None,
                                    progress_percent=(
                                        round(
                                            (total_processed + total_errors)
                                            / chunks_total_at_start
                                            * 100,
                                            1,
                                        )
                                        if chunks_total_at_start
                                        else None
                                    ),
                                )
                                batch_processed, batch_errors = (
                                    await process_embedding_ready_chunks(self, database)
                                )
                                batch_duration = time.time() - batch_start_time
                                cycle_step2_s += batch_duration
                                logger.info(
                                    f"[STEP] Step 2 done: processed={batch_processed}, errors={batch_errors}, duration={batch_duration:.3f}s"
                                )

                                total_processed += batch_processed
                                total_errors += batch_errors
                                write_worker_status(
                                    getattr(self, "status_file_path", None),
                                    STATUS_OPERATION_VECTORIZING,
                                    current_file=None,
                                    progress_percent=(
                                        round(
                                            (total_processed + total_errors)
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

                                # Update statistics
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
                                # Restore original values
                                self.faiss_manager = original_faiss_manager
                                self.project_id = original_project_id

                        except Exception as e:
                            logger.error(
                                f"Error processing project {project_id}: {e}",
                                exc_info=True,
                            )
                            # Continue with next project
                        finally:
                            # Close FAISS manager for this project
                            try:
                                if faiss_manager:
                                    faiss_manager = None
                            except Exception:
                                pass

                    # Step 3: Rebuild FAISS indexes for all projects at end of cycle
                    t0_step3 = time.time()
                    write_worker_status(
                        getattr(self, "status_file_path", None),
                        "rebuilding_faiss",
                        current_file=None,
                        extra={"cycle": cycle_count},
                    )
                    logger.info(
                        f"[CYCLE #{cycle_count}] Rebuilding FAISS indexes for all projects..."
                    )
                    all_projects_list = database.list_projects()
                    # Convert Project objects to dict format for compatibility
                    all_projects = [
                        {
                            "id": p.id,
                            "root_path": p.root_path,
                            "name": p.name,
                            "comment": p.comment,
                        }
                        for p in all_projects_list
                    ]
                    for project in all_projects:
                        project_id = project["id"]
                        project_path = project.get("root_path", "unknown")

                        write_worker_status(
                            getattr(self, "status_file_path", None),
                            "rebuilding_faiss",
                            current_file=None,
                            extra={
                                "project_id": project_id,
                                "root_path": str(project_path),
                            },
                        )
                        try:
                            index_path = self.faiss_dir / f"{project_id}.bin"
                            faiss_manager = FaissIndexManager(
                                index_path=str(index_path),
                                vector_dim=self.vector_dim,
                            )

                            logger.info(
                                f"Rebuilding FAISS index for project {project_id} ({project_path})..."
                            )
                            vectors_count = await faiss_manager.rebuild_from_database(
                                database=database,
                                svo_client_manager=self.svo_client_manager,
                                project_id=project_id,
                            )
                            logger.info(
                                f"✅ FAISS index rebuilt for project {project_id}: {vectors_count} vectors"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to rebuild FAISS index for project {project_id}: {e}",
                                exc_info=True,
                            )
                            # Continue with next project
                    cycle_step3_s = time.time() - t0_step3

            except Exception as e:
                logger.error(f"Error processing projects: {e}", exc_info=True)
                # Check if error is due to database unavailability
                error_str = str(e).lower()
                if (
                    "database" in error_str
                    or "db" in error_str
                    or "connection" in error_str
                ):
                    logger.warning(
                        "Database error detected, will reconnect on next cycle"
                    )
                    try:
                        database.disconnect()
                    except Exception:
                        pass
                    database = None
                    db_available = False
                    db_status_logged = False
                    backoff = 1.0
                    continue
                batch_errors = 0
                batch_processed = 0

            # End cycle
            write_worker_status(
                getattr(self, "status_file_path", None),
                "updating_stats",
                current_file=None,
                extra={"cycle": cycle_count},
            )
            database.execute(
                """
                UPDATE vectorization_stats
                SET cycle_end_time = ?, last_updated = julianday('now')
                WHERE cycle_id = ?
                """,
                (time.time(), cycle_id),
            )

            cycle_duration = time.time() - cycle_start_time
            if cycle_activity:
                logger.info(
                    f"[CYCLE #{cycle_count}] Complete in {cycle_duration:.3f}s: "
                    f"(total: {total_processed} processed, {total_errors} errors)"
                )
                logger.info(
                    "[CYCLE #%s] [TIMING] step0_reembed_s=%.2f step1_query_s=%.2f "
                    "step1_chunking_s=%.2f step2_assign_vector_id_s=%.2f step3_rebuild_faiss_s=%.2f "
                    "total_cycle_s=%.2f chunks_processed=%s files_chunked=%s",
                    cycle_count,
                    cycle_step0_s,
                    cycle_step1_query_s,
                    cycle_step1_chunking_s,
                    cycle_step2_s,
                    cycle_step3_s,
                    cycle_duration,
                    total_processed,
                    cycle_chunked_files,
                )
            else:
                logger.info(
                    f"[CYCLE #{cycle_count}] No activity in {cycle_duration:.3f}s"
                )

            # Wait for next cycle (with early exit check).
            # If we did work this cycle, sleep briefly (2s) then re-check; else full poll_interval.
            actual_poll_interval = poll_interval
            if self.svo_client_manager:
                circuit_state = self.svo_client_manager.get_circuit_state()
                if circuit_state == "open":
                    backoff_delay = self.svo_client_manager.get_backoff_delay()
                    if backoff_delay > poll_interval:
                        actual_poll_interval = int(backoff_delay)
                        logger.debug(
                            "Circuit breaker is OPEN, increasing poll interval "
                            "to %ss (backoff: %.1fs)",
                            actual_poll_interval,
                            backoff_delay,
                        )
            if cycle_activity:
                actual_poll_interval = min(actual_poll_interval, 2)

            write_worker_status(
                getattr(self, "status_file_path", None),
                STATUS_OPERATION_IDLE,
                current_file=None,
                extra={"phase": "sleeping", "next_cycle_in_s": actual_poll_interval},
            )
            if not self._stop_event.is_set():
                logger.info(
                    "[CYCLE #%s] Sleeping %ss before next cycle",
                    cycle_count,
                    actual_poll_interval,
                )
                for _ in range(actual_poll_interval):
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
        f"Vectorization worker stopped: {total_processed} total processed, "
        f"{total_errors} total errors over {cycle_count} cycles"
    )
    return {
        "processed": total_processed,
        "errors": total_errors,
        "cycles": cycle_count,
    }
