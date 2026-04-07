"""
Single cycle execution for vectorization worker.

Runs one full cycle: mark old cycles ended, insert new cycle record,
query projects, process projects (or update stats if none), rebuild FAISS,
update cycle_end_time. Returns deltas and timings.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, List, Tuple

from ..worker_status_file import (
    STATUS_OPERATION_IDLE,
    write_worker_status,
)
from .processing_cycle_projects import process_projects_in_cycle

logger = logging.getLogger(__name__)

# SQL to get projects with pending items (same as in processing.py)
PROJECTS_PENDING_SQL = """
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
WHERE (p.processing_paused = 0 OR p.processing_paused IS NULL)
AND (
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
"""


async def run_one_cycle(
    worker: Any,
    database: Any,
    cycle_count: int,
    total_processed: int,
    total_errors: int,
) -> Tuple[int, int, bool, float, float, float, float, float, int]:
    """
    Run one vectorization cycle: stats, projects query, process projects,
    rebuild FAISS, update cycle_end_time.

    On database/connection error, exception propagates; caller should set
    database=None, db_available=False and reconnect.

    Returns:
        (total_processed_delta, total_errors_delta, cycle_activity,
         cycle_step0_s, cycle_step1_query_s, cycle_step1_chunking_s,
         cycle_step2_s, cycle_step3_s, cycle_chunked_files).
    """
    from ..faiss_manager import FaissIndexManager

    cycle_id = str(uuid.uuid4())
    cycle_start_time = time.time()
    logger.info(
        "[CYCLE #%s] Updating vectorization_stats (mark old cycles ended)...",
        cycle_count,
    )
    database.execute(
        """
        UPDATE vectorization_stats
        SET cycle_end_time = ?, last_updated = julianday('now')
        WHERE cycle_end_time IS NULL
        """,
        (cycle_start_time,),
    )

    chunks_result = database.execute(
        """SELECT COUNT(*) as count FROM code_chunks
           WHERE vector_id IS NULL
             AND (vectorization_skipped IS NULL OR vectorization_skipped = 0)""",
        None,
    )
    chunks_data = (
        chunks_result.get("data", []) if isinstance(chunks_result, dict) else []
    )
    chunks_total_at_start = chunks_data[0].get("count", 0) if chunks_data else 0

    files_result = database.execute(
        "SELECT COUNT(*) as count FROM files WHERE (deleted = 0 OR deleted IS NULL)",
        None,
    )
    files_data = files_result.get("data", []) if isinstance(files_result, dict) else []
    files_total_at_start = files_data[0].get("count", 0) if files_data else 0

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
        vectorized_result.get("data", []) if isinstance(vectorized_result, dict) else []
    )
    files_vectorized = vectorized_data[0].get("count", 0) if vectorized_data else 0

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
    cycle_step0_s = 0.0
    cycle_step1_query_s = 0.0
    cycle_step1_chunking_s = 0.0
    cycle_step2_s = 0.0
    cycle_step3_s = 0.0
    cycle_chunked_files = 0
    delta_processed = 0
    delta_errors = 0

    write_worker_status(
        getattr(worker, "status_file_path", None),
        "querying_projects",
        current_file=None,
        extra={"cycle": cycle_count},
    )
    projects_result = database.execute(PROJECTS_PENDING_SQL, None)
    projects: List[Any] = (
        projects_result.get("data", []) if isinstance(projects_result, dict) else []
    )
    logger.info(
        "[CYCLE #%s] Projects query returned: %d project(s)",
        cycle_count,
        len(projects),
    )

    if not projects:
        logger.info(
            "[CYCLE #%s] No projects with pending items - no work this cycle",
            cycle_count,
        )
        write_worker_status(
            getattr(worker, "status_file_path", None),
            STATUS_OPERATION_IDLE,
            current_file=None,
            extra={"reason": "no_pending_projects"},
        )
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
            "[CYCLE #%s] Found %d projects with pending items: %s",
            cycle_count,
            len(projects),
            [(p.get("project_id"), p.get("pending_count")) for p in projects],
        )
        (
            delta_processed,
            delta_errors,
            cycle_activity,
            cycle_step0_s,
            cycle_step1_query_s,
            cycle_step1_chunking_s,
            cycle_step2_s,
            cycle_chunked_files,
        ) = await process_projects_in_cycle(
            worker,
            database,
            projects,
            cycle_id,
            cycle_count,
            chunks_total_at_start,
            total_processed,
            total_errors,
        )

        t0_step3 = time.time()
        write_worker_status(
            getattr(worker, "status_file_path", None),
            "rebuilding_faiss",
            current_file=None,
            extra={"cycle": cycle_count},
        )
        logger.info(
            "[CYCLE #%s] Rebuilding FAISS indexes for all projects...",
            cycle_count,
        )
        all_projects_list = database.list_projects()
        all_projects = [
            {
                "id": p.id,
                "root_path": p.root_path,
                "name": p.name,
                "comment": p.comment,
                "processing_paused": getattr(p, "processing_paused", False),
            }
            for p in all_projects_list
        ]
        for project in all_projects:
            if project.get("processing_paused"):
                logger.info(
                    "Skipping FAISS rebuild for project %s (processing_paused)",
                    project.get("id"),
                )
                continue
            project_id = project["id"]
            project_path = project.get("root_path", "unknown")
            write_worker_status(
                getattr(worker, "status_file_path", None),
                "rebuilding_faiss",
                current_file=None,
                extra={
                    "project_id": project_id,
                    "root_path": str(project_path),
                },
            )
            try:
                index_path = worker.faiss_dir / f"{project_id}.bin"
                faiss_manager = FaissIndexManager(
                    index_path=str(index_path),
                    vector_dim=worker.vector_dim,
                )
                vectors_count = await faiss_manager.rebuild_from_database(
                    database=database,
                    svo_client_manager=worker.svo_client_manager,
                    project_id=project_id,
                )
                logger.info(
                    "FAISS index rebuilt for project %s: %s vectors",
                    project_id,
                    vectors_count,
                )
            except Exception as e:
                logger.warning(
                    "Failed to rebuild FAISS index for project %s: %s",
                    project_id,
                    e,
                    exc_info=True,
                )
        cycle_step3_s = time.time() - t0_step3

    database.execute(
        """
        UPDATE vectorization_stats
        SET cycle_end_time = ?, last_updated = julianday('now')
        WHERE cycle_id = ?
        """,
        (time.time(), cycle_id),
    )

    return (
        delta_processed,
        delta_errors,
        cycle_activity,
        cycle_step0_s,
        cycle_step1_query_s,
        cycle_step1_chunking_s,
        cycle_step2_s,
        cycle_step3_s,
        cycle_chunked_files,
    )
