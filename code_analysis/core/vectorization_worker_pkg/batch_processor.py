"""
Batch processing helpers for VectorizationWorker.process_chunks.

- process_chunks_missing_embedding_params: Re-embed chunks that have at least one of
  (embedding_model, embedding_vector) missing; then they are picked up by
  process_embedding_ready_chunks for FAISS and vector_id.
- process_embedding_ready_chunks: Add chunks that already have embedding_vector to FAISS
  and write vector_id.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np

from .timing_log import log_operation_timing

logger = logging.getLogger(__name__)

# Logger for blocks sent to chunker (separate file, blocks tied to files)
_chunking_blocks_logger: Optional[logging.Logger] = None


def _get_chunking_blocks_logger(log_dir: Optional[Path] = None) -> logging.Logger:
    """Return logger that writes to logs/chunking_blocks_sent.log (one log per batch, blocks tied to files)."""
    global _chunking_blocks_logger
    if _chunking_blocks_logger is None:
        _chunking_blocks_logger = logging.getLogger(
            "code_analysis.chunking_blocks_sent"
        )
        _chunking_blocks_logger.setLevel(logging.INFO)
        _chunking_blocks_logger.propagate = False
        if not _chunking_blocks_logger.handlers:
            if log_dir is None:
                log_dir = (
                    Path.cwd() / "logs"
                    if (Path.cwd() / "config.json").exists()
                    else Path("logs")
                )
            else:
                log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(
                log_dir / "chunking_blocks_sent.log", encoding="utf-8"
            )
            handler.setLevel(logging.INFO)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
                )
            )
            _chunking_blocks_logger.addHandler(handler)
    return _chunking_blocks_logger


def _log_blocks_sent_to_chunker(
    rows: List[dict],
    texts: List[str],
    project_id: Optional[str] = None,
    log_dir: Optional[Path] = None,
    max_text_len: int = 5000,
) -> None:
    """Write to chunking_blocks_sent.log: for each block, file_id, file_path, chunk_id, length, and full text (for manual check)."""
    if not rows or len(rows) != len(texts):
        return
    log = _get_chunking_blocks_logger(log_dir)
    log.info("--- BATCH | count=%d | project=%s ---", len(rows), project_id or "?")
    for i, row in enumerate(rows):
        file_id = row.get("file_id")
        file_path = row.get("file_path") or ""
        chunk_id = row.get("id")
        text = texts[i] if i < len(texts) else ""
        log.info(
            "  file_id=%s file_path=%s chunk_id=%s len=%d",
            file_id,
            file_path,
            chunk_id,
            len(text),
        )
        log.info("  --- text ---")
        if len(text) <= max_text_len:
            log.info("%s", text)
        else:
            log.info("%s", text[:max_text_len])
            log.info("  ... (truncated, total %d chars)", len(text))
    log.info("--- END BATCH ---")


def _token_count_heuristic(text: str) -> int:
    """Heuristic token count (words). Used when chunker does not return token_count."""
    if not text or not text.strip():
        return 0
    return len(text.split())


async def process_chunks_missing_embedding_params(
    self: Any,
    database: Any,
) -> Tuple[int, int]:
    """
    Re-embed chunks that are missing at least one of embedding_model or embedding_vector.

    Selects rows where (embedding_model IS NULL OR embedding_vector IS NULL) AND vector_id IS NULL.
    Sends chunk_text batch to chunker/embedding service, then UPDATEs DB with
    embedding_vector, embedding_model, token_count. Order is preserved (response index = row index)
    so vectors are identified by position. Afterwards, process_embedding_ready_chunks will
    add them to FAISS and set vector_id.

    Expects `self` to have: batch_size, project_id, svo_client_manager, _stop_event.

    Args:
        self: VectorizationWorker instance (bound dynamically).
        database: DatabaseClient/CodeDatabase instance.

    Returns:
        Tuple of (updated_count, error_count).
    """
    updated_count = 0
    error_count = 0

    if not getattr(self, "svo_client_manager", None):
        logger.debug(
            "process_chunks_missing_embedding_params: no svo_client_manager, skipping"
        )
        return updated_count, error_count

    step_start = time.time()
    scope_desc = f"project={getattr(self, 'project_id', '?')}"
    logger.info(
        f"[TIMING] Getting chunks missing embedding params ({scope_desc}), "
        f"limit={getattr(self, 'batch_size', 10)}"
    )
    rows_result = database.execute(
        """
        SELECT cc.id, cc.chunk_text, cc.file_id, f.path AS file_path
        FROM code_chunks cc
        INNER JOIN files f ON cc.file_id = f.id
        WHERE cc.project_id = ?
          AND (f.deleted = 0 OR f.deleted IS NULL)
          AND cc.vector_id IS NULL
          AND (cc.embedding_model IS NULL OR cc.embedding_vector IS NULL)
        ORDER BY cc.id
        LIMIT ?
        """,
        (self.project_id, self.batch_size),
    )
    rows = rows_result.get("data", []) if isinstance(rows_result, dict) else []
    step_duration = time.time() - step_start
    logger.info(
        f"[TIMING] Retrieved {len(rows)} chunks missing params in {step_duration:.3f}s"
    )
    log_operation_timing(
        getattr(self, "log_timing", False),
        logger,
        "Step0_SELECT_missing_params",
        step_duration,
        rows=len(rows),
    )

    logger.info(f"[STEP] Step 0: Retrieved {len(rows)} chunks missing params")
    if not rows:
        return updated_count, error_count

    logger.info(f"[STEP] Step 0: Sending batch of {len(rows)} texts to chunker")
    texts = [r.get("chunk_text") or "" for r in rows]
    _log_blocks_sent_to_chunker(
        rows, texts, project_id=getattr(self, "project_id", None)
    )
    try:
        t0_batch = time.time()
        batch_results = await self.svo_client_manager.get_chunks_batch(
            texts, type="DocBlock"
        )
        log_operation_timing(
            getattr(self, "log_timing", False),
            logger,
            "Step0_get_chunks_batch",
            time.time() - t0_batch,
            texts=len(texts),
        )
    except Exception as e:
        logger.warning(
            f"get_chunks_batch failed for {len(texts)} texts ({scope_desc}): {e}",
            exc_info=True,
        )
        return updated_count, len(rows)

    update_ops: List[Tuple[str, Optional[tuple]]] = []
    for i, row in enumerate(rows):
        if self._stop_event.is_set():
            break
        chunk_id = row["id"]
        chunk_text = texts[i]
        chunks_i = (
            batch_results[i] if i < len(batch_results) and batch_results[i] else []
        )
        embedding_json: Optional[str] = None
        embedding_model: Optional[str] = None
        token_count: Optional[int] = None

        if chunks_i:
            ch = chunks_i[0]
            emb = getattr(ch, "embedding", None) or getattr(ch, "vector", None)
            if emb is not None:
                embedding_json = json.dumps(emb)
            embedding_model = getattr(ch, "embedding_model", None) or getattr(
                ch, "model", None
            )
            token_count = getattr(ch, "token_count", None)
        if token_count is None and chunk_text:
            token_count = _token_count_heuristic(chunk_text)

        if embedding_json and embedding_model:
            update_ops.append(
                (
                    "UPDATE code_chunks SET embedding_vector = ?, embedding_model = ?, token_count = ? WHERE id = ?",
                    (embedding_json, embedding_model, token_count, chunk_id),
                )
            )
            updated_count += 1
        else:
            logger.debug(
                f"Chunk {chunk_id}: no embedding from chunker (empty or no model), skipping"
            )
            error_count += 1

    if update_ops:
        try:
            t0_db = time.time()
            database.execute_batch(update_ops)
            log_operation_timing(
                getattr(self, "log_timing", False),
                logger,
                "Step0_execute_batch_UPDATE",
                time.time() - t0_db,
                ops=len(update_ops),
            )
            logger.info(
                f"[STEP] Step 0 done: updated {updated_count} rows with embedding_vector/model/token_count"
            )
            logger.info(
                f"Updated {updated_count} chunks with embedding_vector/model/token_count "
                f"({scope_desc})"
            )
        except Exception as e:
            logger.error(
                f"execute_batch failed for {len(update_ops)} chunk updates: {e}",
                exc_info=True,
            )
            error_count += updated_count
            updated_count = 0

    return updated_count, error_count


async def process_embedding_ready_chunks(
    self,
    database: Any,
) -> Tuple[int, int]:
    """
    Process chunks that already have embedding_vector (ready vectors): add to FAISS, set vector_id.

    Only selects rows where embedding_vector IS NOT NULL and vector_id IS NULL.
    Does not create embeddings; indexer is responsible for that.

    Notes:
        - Called from VectorizationWorker.process_chunks.
        - Expects `self` to have `batch_size`, `faiss_manager`, `svo_client_manager`, `_stop_event`.

    Args:
        self: VectorizationWorker instance (bound dynamically).
        database: CodeDatabase instance.

    Returns:
        Tuple of (batch_processed, batch_errors).
    """
    batch_processed = 0
    batch_errors = 0

    # Single query: get one set of records to process (no inner loop)
    step_start = time.time()
    scope_desc = f"project={self.project_id}"
    logger.info(
        f"[TIMING] Getting non-vectorized chunks from DB ({scope_desc}), limit={self.batch_size}"
    )
    chunks_result = database.execute(
        """
        SELECT cc.id, cc.chunk_text, cc.class_id, cc.function_id, cc.method_id,
               cc.line, cc.ast_node_type, cc.embedding_vector, cc.embedding_model
        FROM code_chunks cc
        INNER JOIN files f ON cc.file_id = f.id
        WHERE cc.project_id = ?
          AND (f.deleted = 0 OR f.deleted IS NULL)
          AND cc.embedding_vector IS NOT NULL
          AND cc.vector_id IS NULL
        LIMIT ?
        """,
        (self.project_id, self.batch_size),
    )
    chunks = chunks_result.get("data", []) if isinstance(chunks_result, dict) else []
    step_duration = time.time() - step_start
    logger.info(f"[TIMING] Retrieved {len(chunks)} chunks in {step_duration:.3f}s")
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
            f"(criteria: embedding_vector IS NOT NULL AND vector_id IS NULL, project={scope_desc}, limit={self.batch_size})"
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
        f"[STEP] Step 5: Processing {len(chunks)} chunks (add to FAISS, set vector_id)"
    )
    logger.info(
        f"Processing batch of {len(chunks)} chunks that have embeddings but need vector_id"
    )

    # Profiling: accumulate time per phase
    batch_start_wall = time.time()
    total_db_read_s = step_duration
    total_faiss_s = 0.0
    total_db_update_s = 0.0

    # Collect (chunk_id, vector_id, embedding_model) for batch UPDATE at the end
    updates_to_apply: List[Tuple[int, int, str]] = []

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

            # Add to FAISS index
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

            # Collect for batch UPDATE (single execute_batch after loop)
            updates_to_apply.append((chunk_id, vector_id, embedding_model or ""))

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

    # Batch update: write all vector_id and embedding_model in one execute_batch
    if updates_to_apply:
        db_batch_start = time.time()
        update_ops: List[Tuple[str, Optional[tuple]]] = [
            (
                "UPDATE code_chunks SET vector_id = ?, embedding_model = ? WHERE id = ?",
                (vid, em, cid),
            )
            for (cid, vid, em) in updates_to_apply
        ]
        database.execute_batch(update_ops)
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
    if batch_processed > 0:
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
