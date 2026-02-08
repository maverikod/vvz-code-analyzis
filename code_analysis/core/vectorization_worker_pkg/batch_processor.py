"""
Batch processing helpers for VectorizationWorker.process_chunks.

This module processes only chunks that already have embedding_vector in the DB (ready vectors).
It adds them to FAISS and writes back vector_id. Chunking and embedding are done by the indexer;
the vectorization worker only performs the transfer.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


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
    chunks = (
        chunks_result.get("data", []) if isinstance(chunks_result, dict) else []
    )
    step_duration = time.time() - step_start
    logger.info(
        f"[TIMING] Retrieved {len(chunks)} chunks in {step_duration:.3f}s"
    )

    if not chunks:
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
                logger.debug(
                    f"[TIMING] FAISS index save took {faiss_save_duration:.3f}s"
                )
                batch_wall_s = time.time() - batch_start_wall
                chunks_per_sec = (
                    batch_processed / batch_wall_s if batch_wall_s > 0 else 0.0
                )
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
