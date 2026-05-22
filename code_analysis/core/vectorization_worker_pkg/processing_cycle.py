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

from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY
from ..worker_status_file import (
    STATUS_OPERATION_IDLE,
    write_worker_status,
)
from code_analysis.core.sql_portable import (
    WHERE_FILES_ACTIVE,
    WHERE_FILES_ACTIVE_F,
    WHERE_HAS_DOCSTRING_F,
    WHERE_PROCESSING_ACTIVE_P,
    sql_julian_timestamp_now_expr,
)
from code_analysis.core.docs_markdown_vector_gate import (
    sql_and_exclude_docs_markdown_chunks,
)
from .processing_cycle_projects import process_projects_in_cycle

logger = logging.getLogger(__name__)


def projects_pending_sql(
    docs_markdown_embeddings_enabled: bool = True,
    *,
    use_pgvector_ann: bool = False,
) -> str:
    """
    SQL listing projects that have pending vectorization/chunking work.

    When ``docs_markdown_embeddings_enabled`` is false (``docs_indexing`` policy),
    excludes ``docs_markdown`` chunks from embedding-related pending counts so the
    worker does not spin on Markdown-only embedding backlog.

    When ``use_pgvector_ann`` is true (PostgreSQL + pgvector), rows that still need
    a DB vector use ``embedding_vec IS NULL`` instead of ``vector_id IS NULL``, and
    the "needs embedding" subquery does not gate on ``vector_id``.
    """
    frag = ""
    if not docs_markdown_embeddings_enabled:
        frag = sql_and_exclude_docs_markdown_chunks("cc")
    ann_ready_pending = (
        "cc.embedding_vec IS NULL" if use_pgvector_ann else "cc.vector_id IS NULL"
    )
    needs_emb_prefix = "" if use_pgvector_ann else "cc.vector_id IS NULL AND "
    return f"""
SELECT
    p.id AS project_id,
    p.root_path,
    (
        (SELECT COUNT(DISTINCT f.id)
         FROM files f
         WHERE f.project_id = p.id
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
           AND NOT EXISTS (
               SELECT 1 FROM code_chunks cc
               WHERE cc.file_id = f.id
           ))
        +
        (SELECT COUNT(cc.id)
         FROM code_chunks cc
         INNER JOIN files f ON cc.file_id = f.id
         WHERE cc.project_id = p.id
           AND {WHERE_FILES_ACTIVE_F}{frag}
           AND cc.embedding_vector IS NOT NULL
           AND {ann_ready_pending})
        +
        (SELECT COUNT(cc.id)
         FROM code_chunks cc
         INNER JOIN files f ON cc.file_id = f.id
         WHERE cc.project_id = p.id
           AND {WHERE_FILES_ACTIVE_F}{frag}
           AND {needs_emb_prefix}(cc.embedding_vector IS NULL OR cc.embedding_model IS NULL)
           AND (cc.vectorization_skipped IS NULL OR cc.vectorization_skipped = 0))
    ) AS pending_count,
    (SELECT MAX(f2.updated_at) FROM files f2
     WHERE f2.project_id = p.id
       AND {WHERE_FILES_ACTIVE_F.replace("f.", "f2.")}) AS max_file_updated_at
FROM projects p
WHERE {WHERE_PROCESSING_ACTIVE_P}
AND (
    (SELECT COUNT(DISTINCT f.id)
     FROM files f
     WHERE f.project_id = p.id
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
       AND NOT EXISTS (
           SELECT 1 FROM code_chunks cc
           WHERE cc.file_id = f.id
       ))
    +
    (SELECT COUNT(cc.id)
     FROM code_chunks cc
     INNER JOIN files f ON cc.file_id = f.id
     WHERE cc.project_id = p.id
       AND {WHERE_FILES_ACTIVE_F}{frag}
       AND cc.embedding_vector IS NOT NULL
       AND {ann_ready_pending})
    +
    (SELECT COUNT(cc.id)
     FROM code_chunks cc
     INNER JOIN files f ON cc.file_id = f.id
     WHERE cc.project_id = p.id
       AND {WHERE_FILES_ACTIVE_F}{frag}
       AND {needs_emb_prefix}(cc.embedding_vector IS NULL OR cc.embedding_model IS NULL)
       AND (cc.vectorization_skipped IS NULL OR cc.vectorization_skipped = 0))
) > 0
ORDER BY max_file_updated_at DESC, pending_count ASC, p.id DESC
"""


PROJECTS_PENDING_SQL = projects_pending_sql(True, use_pgvector_ann=False)


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
    _now_sql = sql_julian_timestamp_now_expr(database)
    logger.debug(
        "[CYCLE #%s] Updating vectorization_stats (mark old cycles ended)...",
        cycle_count,
    )
    database.execute(
        f"""
        UPDATE vectorization_stats
        SET cycle_end_time = ?, last_updated = {_now_sql}
        WHERE cycle_end_time IS NULL
        """,
        (cycle_start_time,),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )

    use_pgvector_ann = getattr(worker, "vector_ann_backend", "faiss") == "pgvector"
    chunk_unindexed_clause = (
        "embedding_vec IS NULL" if use_pgvector_ann else "vector_id IS NULL"
    )
    chunk_indexed_clause = (
        "cc.embedding_vec IS NOT NULL"
        if use_pgvector_ann
        else "cc.vector_id IS NOT NULL"
    )

    chunks_result = database.execute(
        f"""SELECT COUNT(*) as count FROM code_chunks
           WHERE {chunk_unindexed_clause}
             AND (vectorization_skipped IS NULL OR vectorization_skipped = 0)""",
        None,
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    chunks_data = (
        chunks_result.get("data", []) if isinstance(chunks_result, dict) else []
    )
    chunks_total_at_start = chunks_data[0].get("count", 0) if chunks_data else 0

    files_result = database.execute(
        f"SELECT COUNT(*) as count FROM files WHERE {WHERE_FILES_ACTIVE}",
        None,
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    files_data = files_result.get("data", []) if isinstance(files_result, dict) else []
    files_total_at_start = files_data[0].get("count", 0) if files_data else 0

    vectorized_result = database.execute(
        f"""
        SELECT COUNT(DISTINCT f.id) as count
        FROM files f
        INNER JOIN code_chunks cc ON f.id = cc.file_id
        WHERE {WHERE_FILES_ACTIVE_F}
        AND {chunk_indexed_clause}
        """,
        None,
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    vectorized_data = (
        vectorized_result.get("data", []) if isinstance(vectorized_result, dict) else []
    )
    files_vectorized = vectorized_data[0].get("count", 0) if vectorized_data else 0

    database.execute(
        f"""
        INSERT INTO vectorization_stats (
            cycle_id, cycle_start_time, chunks_total_at_start,
            files_total_at_start, files_vectorized, last_updated
        ) VALUES (?, ?, ?, ?, ?, {_now_sql})
        """,
        (
            cycle_id,
            cycle_start_time,
            chunks_total_at_start,
            files_total_at_start,
            files_vectorized,
        ),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
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
    projects_result = database.execute(
        projects_pending_sql(
            bool(getattr(worker, "docs_markdown_embeddings_enabled", True)),
            use_pgvector_ann=use_pgvector_ann,
        ),
        None,
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    projects: List[Any] = (
        projects_result.get("data", []) if isinstance(projects_result, dict) else []
    )
    logger.debug(
        "[CYCLE #%s] Projects query returned: %d project(s)",
        cycle_count,
        len(projects),
    )

    if not projects:
        logger.debug(
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
            f"""
            UPDATE vectorization_stats
            SET
                chunks_processed = chunks_processed + ?,
                chunks_skipped = chunks_skipped + ?,
                chunks_failed = chunks_failed + ?,
                total_processing_time_seconds = total_processing_time_seconds + ?,
                last_updated = {_now_sql}
            WHERE cycle_id = ?
            """,
            (0, 0, 0, 0.0, cycle_id),
            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
        )
    else:
        logger.debug(
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
        if use_pgvector_ann:
            logger.debug(
                "[CYCLE #%s] Skipping per-project FAISS rebuild (pgvector ANN backend)",
                cycle_count,
            )
            write_worker_status(
                getattr(worker, "status_file_path", None),
                STATUS_OPERATION_IDLE,
                current_file=None,
                extra={"cycle": cycle_count, "reason": "pgvector_no_faiss_rebuild"},
            )
        else:
            write_worker_status(
                getattr(worker, "status_file_path", None),
                "rebuilding_faiss",
                current_file=None,
                extra={"cycle": cycle_count},
            )
            logger.debug(
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
                        omit_docs_markdown=not bool(
                            getattr(worker, "docs_markdown_embeddings_enabled", True)
                        ),
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
        f"""
        UPDATE vectorization_stats
        SET cycle_end_time = ?, last_updated = {_now_sql}
        WHERE cycle_id = ?
        """,
        (time.time(), cycle_id),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
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
