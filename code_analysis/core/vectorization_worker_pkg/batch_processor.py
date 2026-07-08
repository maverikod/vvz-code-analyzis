"""Batch processing helpers for VectorizationWorker.process_chunks.

- process_chunk_only_files: Fill embeddings for chunk-only rows via embed-client.
- process_embedding_ready_chunks: Add chunks that already have embedding_vector to
  FAISS/pgvector and write vector_id or embedding_vec.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import inspect
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import numpy as np

from code_analysis.core.embedding_input import EmbeddingInput
from code_analysis.core.faiss_manager import FaissIndexManager
from code_analysis.core.pgvector_embedding import numpy_embedding_to_pgvector_text
from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE_F
from code_analysis.core.worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY
from code_analysis.core.docs_markdown_vector_gate import (
    sql_and_exclude_docs_markdown_chunks,
)

from .timing_log import log_operation_timing

logger = logging.getLogger(__name__)


def _sql_exclude_docs_markdown_if_gated(worker_like: Any) -> str:
    """When Markdown docs embeddings are disabled by config, omit those chunks from SQL."""
    if getattr(worker_like, "docs_markdown_embeddings_enabled", True):
        return ""
    return sql_and_exclude_docs_markdown_chunks("cc")


def _usable_embedding(chunk: Any) -> Optional[list]:
    """Return usable embedding."""
    emb = getattr(chunk, "embedding", None)
    if isinstance(emb, list) and emb:
        return emb
    return None


def _embedding_model(chunk: Any) -> Optional[str]:
    """Return embedding model."""
    model = getattr(chunk, "embedding_model", None) or getattr(chunk, "model", None)
    return str(model) if model else None


async def recover_unvectorized_by_neighbor_merge(
    ordered_chunks: List[Any],
    embed_one: Callable[[str], Awaitable[Tuple[Optional[list], Optional[str]]]],
) -> Dict[str, Tuple[list, str]]:
    """Return per-row vector assignments for chunks still missing embeddings.

    Recovery is in-memory only: failed chunks are grouped with a neighbor,
    concatenated in file order, and the recovered vector is repeated for every
    original row id in the successful group.
    """
    assignments: Dict[str, Tuple[list, str]] = {}
    if not ordered_chunks:
        return assignments

    n_chunks = len(ordered_chunks)
    covered: set[int] = set()
    for idx, chunk in enumerate(ordered_chunks):
        if idx in covered or _usable_embedding(chunk):
            continue

        if n_chunks == 1:
            start = end = idx
        elif idx == 0:
            start, end = 0, 1
        else:
            start, end = idx - 1, idx

        while True:
            group = ordered_chunks[start : end + 1]
            text = "".join(getattr(ch, "text", "") for ch in group)
            vector, model = await embed_one(text)
            if vector and model:
                for group_idx in range(start, end + 1):
                    group_chunk = ordered_chunks[group_idx]
                    chunk_id = str(getattr(group_chunk, "id"))
                    assignments[chunk_id] = (vector, model)
                    covered.add(group_idx)
                break
            if start > 0:
                start -= 1
            elif end < n_chunks - 1:
                end += 1
            else:
                covered.update(range(start, end + 1))
                break

    return assignments


async def process_chunk_only_files(
    self: Any,
    database: Any,
) -> Tuple[int, int]:
    """Vectorize per-file chunk batches that arrived without embeddings (chunk_only mode).

    Correct DB access pattern:
    1. Build file table from DB (read-only query).
    2. For each file: fetch chunk rows snapshot (read-only).
    3. Embed through embed-client. Any per-text miss is recovered by
        re-vectorizing a growing neighbor merge, without changing chunk rows.
    4. Commit all embedding UPDATE ops for the file in one atomic
        ``execute_logical_write_operation`` call.

    All SQL params are pre-computed from the snapshot before any write.
    Every file-level mutation is one atomic transaction.

    Args:
        self: VectorizationWorker instance.
        database: Database client (DatabaseClient RPC or CodeDatabase).

    Returns:
        Tuple of (updated_count, error_count).
    """
    if not getattr(self, "chunk_only", False):
        return 0, 0

    svo_mgr = getattr(self, "svo_client_manager", None)
    if not svo_mgr:
        return 0, 0

    updated_count = 0
    error_count = 0
    project_id = getattr(self, "project_id", "")
    md_excl = _sql_exclude_docs_markdown_if_gated(self)

    # Pre-build SQL constants (no multiline strings in ops lists).
    _EMBED_UPDATE_SQL = (
        "UPDATE code_chunks"
        " SET embedding_vector = ?, embedding_model = ?"
        " WHERE id = ?"
    )
    _CHUNK_SELECT_SQL = (
        "SELECT cc.id, cc.chunk_text"
        " FROM code_chunks cc"
        " WHERE cc.file_id = ? AND cc.project_id = ?"
        "   AND cc.vector_id IS NULL"
        "   AND cc.embedding_vector IS NULL"
        "   AND cc.embedding_model IS NULL"
        "   AND (cc.vectorization_skipped IS NULL OR cc.vectorization_skipped = 0)"
        " ORDER BY cc.ordinal ASC, cc.id ASC"
    )

    # Step 1: file table - files that have un-vectorized chunks.
    file_result = database.execute(
        f"""
        SELECT cc.file_id, f.path AS file_path, COUNT(cc.id) AS cnt
        FROM code_chunks cc
        INNER JOIN files f ON cc.file_id = f.id
        WHERE cc.project_id = ?
          AND {WHERE_FILES_ACTIVE_F}{md_excl}
          AND cc.vector_id IS NULL
          AND cc.embedding_vector IS NULL
          AND cc.embedding_model IS NULL
          AND (cc.vectorization_skipped IS NULL OR cc.vectorization_skipped = 0)
        GROUP BY cc.file_id, f.path
        HAVING COUNT(cc.id) > 0
        ORDER BY MAX(cc.created_at) DESC
        LIMIT ?
        """,
        (project_id, getattr(self, "max_files_per_pass", 30)),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    files_data = file_result.get("data", []) if isinstance(file_result, dict) else []
    if not files_data:
        return 0, 0

    logger.info("[chunk_only] %d file(s) have un-vectorized chunks", len(files_data))

    for file_row in files_data:
        if getattr(self, "_stop_event", None) and self._stop_event.is_set():
            break

        file_id: str = file_row["file_id"]
        file_path: str = file_row.get("file_path", file_id)

        # Step 2: fetch chunk snapshot for this file (fixed before any write).
        chunk_result = database.execute(
            _CHUNK_SELECT_SQL,
            (file_id, project_id),
            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
        )
        chunks = chunk_result.get("data", []) if isinstance(chunk_result, dict) else []
        if not chunks:
            continue

        chunk_objs: List[EmbeddingInput] = [
            EmbeddingInput(text=r.get("chunk_text") or "", id=str(r["id"]))
            for r in chunks
        ]

        logger.info(
            "[chunk_only] file=%s: %d chunk(s) to vectorize",
            file_path,
            len(chunks),
        )

        # Step 3: attempt embed-client vectorization for the file snapshot.
        try:
            await svo_mgr.get_embeddings(chunk_objs)
        except Exception as exc:
            if getattr(svo_mgr, "_embedding_available", True) is False:
                logger.warning(
                    "[chunk_only] file=%s: embed-client unavailable; skipping file",
                    file_path,
                )
                continue
            logger.warning(
                "[chunk_only] file=%s: embed-client failed: %s",
                file_path,
                exc,
                exc_info=True,
            )
            error_count += len(chunk_objs)
            continue

        assignments: Dict[str, Tuple[list, str]] = {}
        for chunk in chunk_objs:
            emb = _usable_embedding(chunk)
            model = _embedding_model(chunk)
            if emb and model:
                assignments[chunk.id] = (emb, model)

        missing_before_recovery = len(chunk_objs) - len(assignments)
        if missing_before_recovery:
            logger.info(
                "[chunk_only] file=%s: %d chunk(s) need neighbor-merge recovery",
                file_path,
                missing_before_recovery,
            )

            async def _embed_one(text: str) -> Tuple[Optional[list], Optional[str]]:
                """Return embed one."""
                tmp = EmbeddingInput(text=text, id="__merged__")
                await svo_mgr.get_embeddings([tmp])
                return _usable_embedding(tmp), _embedding_model(tmp)

            try:
                recovered = await recover_unvectorized_by_neighbor_merge(
                    chunk_objs, _embed_one
                )
            except Exception as exc:
                if getattr(svo_mgr, "_embedding_available", True) is False:
                    logger.warning(
                        "[chunk_only] file=%s: embed-client unavailable during "
                        "neighbor-merge recovery; skipping file",
                        file_path,
                    )
                    continue
                logger.warning(
                    "[chunk_only] file=%s: neighbor-merge recovery failed: %s",
                    file_path,
                    exc,
                    exc_info=True,
                )
                error_count += missing_before_recovery
                continue
            assignments.update(recovered)

        update_ops: List[Tuple[str, Optional[tuple]]] = []
        for chunk in chunk_objs:
            assigned = assignments.get(chunk.id)
            if not assigned:
                continue
            vector, model = assigned
            update_ops.append(
                (_EMBED_UPDATE_SQL, (json.dumps(vector), model, chunk.id))
            )
        unresolved_count = len(chunk_objs) - len(update_ops)
        if not update_ops:
            logger.info(
                "[chunk_only] file=%s: no usable embeddings; leaving chunks for retry",
                file_path,
            )
            error_count += unresolved_count
            continue

        # All params known upfront. Commit atomically - counters updated only on success.
        try:
            lw = getattr(database, "execute_logical_write_operation", None)
            if callable(lw):
                if inspect.iscoroutinefunction(lw):
                    await lw({"batches": [update_ops]})
                else:
                    lw({"batches": [update_ops]})
            else:
                database.execute_batch(
                    update_ops, priority=BACKGROUND_WORKER_DB_RPC_PRIORITY
                )
            updated_count += len(update_ops)
            error_count += unresolved_count
            logger.info(
                "[chunk_only] file=%s: committed %d embedding update(s); "
                "unresolved=%d",
                file_path,
                len(update_ops),
                unresolved_count,
            )
        except Exception as exc:
            logger.error(
                "[chunk_only] file=%s: atomic UPDATE failed: %s",
                file_path,
                exc,
            )
            error_count += len(update_ops)

    if updated_count or error_count:
        logger.info(
            "[chunk_only] done: updated=%d errors=%d",
            updated_count,
            error_count,
        )
    return updated_count, error_count


async def process_embedding_ready_chunks(
    self,
    database: Any,
) -> Tuple[int, int]:
    """
    Process chunks that already have embedding_vector (ready vectors): add to FAISS + vector_id,
    or write ``embedding_vec`` (PostgreSQL pgvector) when ``vector_ann_backend`` is ``pgvector``.

    Does not create embeddings; indexer is responsible for that.

    Notes:
        - Called from VectorizationWorker.process_chunks.
        - Expects `self` to have `batch_size`, `faiss_manager` (unless pgvector), `svo_client_manager`, `_stop_event`.

    Args:
        self: VectorizationWorker instance (bound dynamically).
        database: Legacy SQL facade instance.

    Returns:
        Tuple of (batch_processed, batch_errors).
    """
    batch_processed = 0
    batch_errors = 0
    md_excl = _sql_exclude_docs_markdown_if_gated(self)
    use_pgvector = getattr(self, "vector_ann_backend", "faiss") == "pgvector"
    ann_pending = "cc.embedding_vec IS NULL" if use_pgvector else "cc.vector_id IS NULL"

    # Single query: get one set of records to process (no inner loop)
    step_start = time.time()
    scope_desc = f"project={self.project_id}"
    logger.info(
        f"[TIMING] Getting non-vectorized chunks from DB ({scope_desc}), limit={self.batch_size}"
    )
    chunks_result = database.execute(
        f"""
        SELECT cc.id, cc.chunk_text, cc.class_id, cc.function_id, cc.method_id,
               cc.line, cc.ast_node_type, cc.embedding_vector, cc.embedding_model
        FROM code_chunks cc
        INNER JOIN files f ON cc.file_id = f.id
        WHERE cc.project_id = ?
          AND {WHERE_FILES_ACTIVE_F}{md_excl}
          AND cc.embedding_vector IS NOT NULL
          AND {ann_pending}
        ORDER BY cc.created_at DESC, cc.id DESC
        LIMIT ?
        """,
        (self.project_id, self.batch_size),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    chunks = chunks_result.get("data", []) if isinstance(chunks_result, dict) else []
    step_duration = time.time() - step_start
    logger.debug(f"[TIMING] Retrieved {len(chunks)} chunks in {step_duration:.3f}s")
    log_operation_timing(
        getattr(self, "log_timing", False),
        logger,
        "Step5_SELECT_embedding_ready",
        step_duration,
        chunks=len(chunks),
    )

    if not chunks:
        logger.info(
            f"[STEP] Step 5 (embedding_ready): 0 chunks selected "
            f"(criteria: embedding_vector IS NOT NULL AND {ann_pending}, project={scope_desc}, limit={self.batch_size})"
        )
        from ..worker_status_file import (
            STATUS_OPERATION_IDLE,
            write_worker_status,
        )

        write_worker_status(
            getattr(self, "status_file_path", None),
            STATUS_OPERATION_IDLE,
            current_file=None,
            progress_percent=None,
        )
        return batch_processed, batch_errors

    logger.info(
        f"[STEP] Step 5: Processing {len(chunks)} chunks "
        f"({'pgvector embedding_vec' if use_pgvector else 'FAISS + vector_id'})"
    )
    logger.info(
        f"Processing batch of {len(chunks)} chunks that have embeddings but need ANN indexing"
    )

    # Profiling: accumulate time per phase
    batch_start_wall = time.time()
    total_db_read_s = step_duration
    total_faiss_s = 0.0
    total_db_update_s = 0.0

    # FAISS: (chunk_id, vector_id, embedding_model); pgvector: (chunk_id, vec_text, embedding_model)
    updates_faiss: List[Tuple[str, int, str]] = []
    updates_pg: List[Tuple[str, str, str]] = []

    for chunk in chunks:
        if self._stop_event.is_set():
            break

        try:
            chunk_start_time = time.time()
            chunk_id = chunk["id"]
            chunk_text = chunk.get("chunk_text", "")

            # Log chunk text (docstring) for debugging
            chunk_text_preview = (
                chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text
            )
            logger.debug(
                f"[CHUNK {chunk_id}] Processing chunk:\n"
                f"  Text preview: {chunk_text_preview!r}\n"
                f"  Text length: {len(chunk_text)} chars"
            )

            # Log AST binding information for this chunk
            ast_info = []
            if chunk.get("class_id"):
                ast_info.append(f"class_id={chunk['class_id']}")
            if chunk.get("function_id"):
                ast_info.append(f"function_id={chunk['function_id']}")
            if chunk.get("method_id"):
                ast_info.append(f"method_id={chunk['method_id']}")
            if chunk.get("line"):
                ast_info.append(f"line={chunk['line']}")
            if chunk.get("ast_node_type"):
                ast_info.append(f"node={chunk['ast_node_type']}")
            ast_binding = ", ".join(ast_info) if ast_info else "no AST binding"
            logger.debug(f"[CHUNK {chunk_id}] AST binding: {ast_binding}")

            embedding_array: Optional[np.ndarray] = None
            embedding_model: Optional[str] = None

            # Use only embedding already in DB (indexer is responsible for chunking/embedding)
            if chunk.get("embedding_vector"):
                load_start = time.time()
                try:
                    embedding_list = json.loads(chunk["embedding_vector"])
                    embedding_array = np.array(embedding_list, dtype="float32")
                    embedding_model = chunk.get("embedding_model") or ""
                    load_duration = time.time() - load_start
                    logger.debug(
                        f"[TIMING] [CHUNK {chunk_id}] Loaded embedding from DB in {load_duration:.3f}s "
                        f"(dim={len(embedding_array)}, model={embedding_model}, {ast_binding})"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to parse embedding from DB for chunk {chunk_id} "
                        f"({ast_binding}): {e}"
                    )

            if embedding_array is None:
                logger.debug(
                    f"Chunk {chunk_id} has no embedding in DB ({ast_binding}), skipping "
                    "(indexer must set embedding_vector; vectorization worker only transfers)"
                )
                continue

            norm = FaissIndexManager._normalize_vector(embedding_array)

            if use_pgvector:
                vec_txt = numpy_embedding_to_pgvector_text(norm)
                updates_pg.append((chunk_id, vec_txt, embedding_model or ""))
                chunk_total_duration = time.time() - chunk_start_time
                batch_processed += 1
                logger.info(
                    f"✅ pgvector chunk {chunk_id} ({ast_binding}) in {chunk_total_duration:.3f}s"
                )
            else:
                if self.faiss_manager is None:
                    logger.error(
                        "faiss_manager is None but vector_ann_backend is not pgvector"
                    )
                    batch_errors += 1
                    continue
                logger.debug(
                    f"[CHUNK {chunk_id}] Adding embedding to FAISS index "
                    f"(dim={len(embedding_array)}, model={embedding_model})"
                )
                faiss_add_start = time.time()
                vector_id = self.faiss_manager.add_vector(embedding_array)
                faiss_add_duration = time.time() - faiss_add_start
                total_faiss_s += faiss_add_duration
                logger.debug(
                    f"[TIMING] [CHUNK {chunk_id}] FAISS add_vector took {faiss_add_duration:.3f}s, "
                    f"assigned vector_id={vector_id}"
                )
                updates_faiss.append((chunk_id, vector_id, embedding_model or ""))
                chunk_total_duration = time.time() - chunk_start_time
                batch_processed += 1
                logger.info(
                    f"✅ Vectorized chunk {chunk_id} → vector_id={vector_id} "
                    f"({ast_binding}) in {chunk_total_duration:.3f}s"
                )
                logger.debug(
                    f"[TIMING] [CHUNK {chunk_id}] Total processing time: {chunk_total_duration:.3f}s"
                )

        except Exception as e:
            logger.error(
                f"Error processing chunk {chunk.get('id')}: {e}, "
                "will retry in next cycle",
                exc_info=True,
            )
            batch_errors += 1
            continue

    if updates_pg:
        db_batch_start = time.time()
        pg_ops: List[Tuple[str, Optional[tuple]]] = [
            (
                "UPDATE code_chunks SET embedding_vec = ?::vector, embedding_model = ? WHERE id = ?",
                (vtxt, em, cid),
            )
            for (cid, vtxt, em) in updates_pg
        ]
        database.execute_batch(pg_ops, priority=BACKGROUND_WORKER_DB_RPC_PRIORITY)
        total_db_update_s = time.time() - db_batch_start
        logger.debug(
            f"[TIMING] execute_batch: {len(pg_ops)} pgvector UPDATEs in {total_db_update_s:.3f}s"
        )
        log_operation_timing(
            getattr(self, "log_timing", False),
            logger,
            "Step5_execute_batch_UPDATE_embedding_vec",
            total_db_update_s,
            ops=len(pg_ops),
        )

    if updates_faiss:
        db_batch_start = time.time()
        update_ops: List[Tuple[str, Optional[tuple]]] = [
            (
                "UPDATE code_chunks SET vector_id = ?, embedding_model = ? WHERE id = ?",
                (vid, em, cid),
            )
            for (cid, vid, em) in updates_faiss
        ]
        database.execute_batch(update_ops, priority=BACKGROUND_WORKER_DB_RPC_PRIORITY)
        total_db_update_s = time.time() - db_batch_start
        logger.debug(
            f"[TIMING] execute_batch: {len(update_ops)} UPDATEs in {total_db_update_s:.3f}s"
        )
        log_operation_timing(
            getattr(self, "log_timing", False),
            logger,
            "Step5_execute_batch_UPDATE_vector_id",
            total_db_update_s,
            ops=len(update_ops),
        )

    # Save FAISS index after batch and log profile summary
    faiss_save_s = 0.0
    if batch_processed > 0 and not use_pgvector and self.faiss_manager is not None:
        faiss_save_start = time.time()
        try:
            logger.debug(
                f"[TIMING] Saving FAISS index after processing {batch_processed} chunks"
            )
            self.faiss_manager.save_index()
            faiss_save_duration = time.time() - faiss_save_start
            faiss_save_s = faiss_save_duration
            logger.debug(f"[TIMING] FAISS index save took {faiss_save_duration:.3f}s")
            log_operation_timing(
                getattr(self, "log_timing", False),
                logger,
                "Step5_FAISS_save_index",
                faiss_save_duration,
                chunks_processed=batch_processed,
            )
            batch_wall_s = time.time() - batch_start_wall
            chunks_per_sec = batch_processed / batch_wall_s if batch_wall_s > 0 else 0.0
            logger.info(
                "[PROFILE] batch_size=%s processed=%s errors=%s total_s=%.3f "
                "chunks_per_sec=%.2f db_read_s=%.3f faiss_s=%.3f db_update_s=%.3f faiss_save_s=%.3f",
                len(chunks),
                batch_processed,
                batch_errors,
                batch_wall_s,
                chunks_per_sec,
                total_db_read_s,
                total_faiss_s,
                total_db_update_s,
                faiss_save_s,
            )
        except Exception as e:
            logger.error(f"Error saving FAISS index: {e}")

    return batch_processed, batch_errors
