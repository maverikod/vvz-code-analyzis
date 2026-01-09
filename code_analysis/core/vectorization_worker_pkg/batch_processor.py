"""
Batch processing helpers for VectorizationWorker.process_chunks.

This module contains the heavy inner loop that takes chunks which already have
embeddings stored in the DB (or can fetch them from SVO), adds them to FAISS,
and writes back vector_id.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


async def process_embedding_ready_chunks(
    self,
    database: Any,
) -> Tuple[int, int]:
    """
    Process chunks that are ready to be added to FAISS (have embeddings or can get them).

    Notes:
        - This function is designed to be called from VectorizationWorker.process_chunks.
        - It expects `self` to have `batch_size`, `faiss_manager`, `svo_client_manager`,
          and `_stop_event`.

    Args:
        self: VectorizationWorker instance (bound dynamically).
        database: CodeDatabase instance.

    Returns:
        Tuple of (batch_processed, batch_errors).
    """
    batch_processed = 0
    batch_errors = 0
    empty_iterations = 0
    # Get max_empty_iterations and empty_delay from worker config
    max_empty_iterations = getattr(self, "max_empty_iterations", 3)
    empty_delay = getattr(self, "empty_delay", 5.0)

    while not self._stop_event.is_set():
        # Get chunks with embeddings in DB but without vector_id
        # These are chunks where embedding was saved but FAISS add failed or wasn't done
        # Project-scoped: all chunks in project (datasets EXCLUDED)
        step_start = time.time()
        scope_desc = f"project={self.project_id}"
        logger.info(
            f"[TIMING] Step 2: Starting to get non-vectorized chunks from DB ({scope_desc})"
        )
        # get_non_vectorized_chunks is synchronous, returns List[Dict], not a coroutine
        chunks = database.get_non_vectorized_chunks(
            project_id=self.project_id,
            limit=self.batch_size,
        )
        step_duration = time.time() - step_start
        logger.info(
            f"[TIMING] Step 2: Retrieved {len(chunks)} chunks from DB in {step_duration:.3f}s"
        )

        if not chunks:
            empty_iterations += 1
            if empty_iterations >= max_empty_iterations:
                # Add delay to prevent busy-wait when no chunks available
                logger.info(
                    f"No chunks available after {empty_iterations} iterations, "
                    f"adding delay of {empty_delay}s to prevent CPU spinning"
                )
                # Wait before next check to reduce CPU load
                delay_seconds = int(empty_delay)
                for _ in range(delay_seconds):
                    if self._stop_event.is_set():
                        break
                    await asyncio.sleep(1)
            else:
                logger.info(
                    f"No chunks needing vector_id assignment in this cycle (iteration {empty_iterations}/{max_empty_iterations})"
                )
            break

        logger.info(
            f"Processing batch of {len(chunks)} chunks that have embeddings but need vector_id"
        )

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

                # Check if chunk has embedding_vector in database
                db_check_start = time.time()
                row = database._fetchone(
                    "SELECT embedding_vector, embedding_model FROM code_chunks WHERE id = ?",
                    (chunk_id,),
                )
                db_check_duration = time.time() - db_check_start
                logger.debug(
                    f"[TIMING] [CHUNK {chunk_id}] DB check took {db_check_duration:.3f}s"
                )

                embedding_array: Optional[np.ndarray] = None
                embedding_model: Optional[str] = None

                if row and row.get("embedding_vector"):  # embedding_vector exists
                    # Load embedding from database
                    load_start = time.time()
                    try:
                        embedding_list = json.loads(row["embedding_vector"])
                        embedding_array = np.array(embedding_list, dtype="float32")
                        embedding_model = row["embedding_model"]
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

                # If no embedding in DB, try to get it from chunker service (SVO)
                if embedding_array is None and self.svo_client_manager:
                    logger.info(
                        f"Chunk {chunk_id} has no embedding in DB ({ast_binding}), "
                        "requesting from chunker service (SVO)..."
                    )
                    try:
                        if not chunk_text:
                            logger.warning(f"Chunk {chunk_id} has no text, skipping")
                            continue

                        logger.debug(
                            f"[CHUNK {chunk_id}] Requesting chunks with embeddings from chunker service for text:\n"
                            f"  {chunk_text_preview!r}"
                        )

                        embedding_request_start = time.time()
                        # Use chunker service - it chunks and returns chunks with embeddings
                        chunk_type = chunk.get("chunk_type", "DocBlock")
                        chunks_with_emb = None
                        try:
                            chunks_with_emb = await self.svo_client_manager.get_chunks(
                                text=chunk_text, type=chunk_type
                            )
                            embedding_request_duration = (
                                time.time() - embedding_request_start
                            )
                            logger.debug(
                                f"[TIMING] [CHUNK {chunk_id}] Chunker service request took {embedding_request_duration:.3f}s"
                            )
                        except Exception as svo_e:
                            # Chunker service error - skip this chunk, continue processing
                            embedding_request_duration = (
                                time.time() - embedding_request_start
                            )
                            logger.debug(
                                f"[CHUNK {chunk_id}] Chunker service error after {embedding_request_duration:.3f}s: {svo_e}. "
                                "Skipping chunk, will retry in next cycle if service becomes available."
                            )
                            batch_errors += 1
                            continue  # Skip this chunk, try next one

                        if chunks_with_emb and len(chunks_with_emb) > 0:
                            embedding = getattr(chunks_with_emb[0], "embedding", None)
                            embedding_model = getattr(
                                chunks_with_emb[0], "embedding_model", None
                            )

                            if embedding:
                                embedding_array = np.array(embedding, dtype="float32")
                                logger.debug(
                                    f"[CHUNK {chunk_id}] Received embedding: dim={len(embedding_array)}, "
                                    f"model={embedding_model}"
                                )

                                # Save to DB for future use
                                save_start = time.time()
                                embedding_json = json.dumps(
                                    embedding.tolist()
                                    if hasattr(embedding, "tolist")
                                    else embedding
                                )
                                database._execute(
                                    "UPDATE code_chunks SET embedding_vector = ?, embedding_model = ? WHERE id = ?",
                                    (
                                        embedding_json,
                                        embedding_model,
                                        chunk_id,
                                    ),
                                )
                                database._commit()
                                save_duration = time.time() - save_start
                                logger.debug(
                                    f"[TIMING] [CHUNK {chunk_id}] Saved embedding to DB in {save_duration:.3f}s"
                                )
                                logger.info(
                                    f"✅ Obtained and saved embedding for chunk {chunk_id} "
                                    f"({ast_binding})"
                                )
                            else:
                                logger.warning(
                                    f"Chunk {chunk_id} embedding request returned no embedding, "
                                    "skipping (use dedicated command to process empty chunks)"
                                )
                                continue
                        else:
                            logger.warning(
                                f"Chunk {chunk_id} embedding request returned empty result, "
                                "skipping (use dedicated command to process empty chunks)"
                            )
                            continue
                    except Exception as e:
                        # This catch handles errors from the outer try block (file reading, etc.)
                        # SVO errors are already handled in the inner try-except above
                        error_type = type(e).__name__
                        error_msg = str(e)

                        # Check if it's a Model RPC server error (infrastructure issue)
                        is_model_rpc_error = (
                            "Model RPC server" in error_msg
                            or "failed after 3 attempts" in error_msg
                            or (hasattr(e, "code") and getattr(e, "code") == -32603)
                        )

                        if is_model_rpc_error:
                            # Infrastructure issue, not code issue
                            logger.warning(
                                f"Model RPC server unavailable for chunk {chunk_id} ({ast_binding}): {error_msg}. "
                                f"Chunk will be retried in next cycle. Check Model RPC server status."
                            )
                        else:
                            logger.error(
                                f"Failed to get embedding for chunk {chunk_id} ({ast_binding}): {error_type}: {error_msg}",
                                exc_info=True,
                            )
                        batch_errors += 1
                        continue

                # Skip chunks without embeddings - they should be processed via dedicated command
                if embedding_array is None:
                    logger.debug(
                        f"Chunk {chunk_id} has no embedding ({ast_binding}), skipping "
                        "(use dedicated command to process empty chunks)"
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
                logger.debug(
                    f"[TIMING] [CHUNK {chunk_id}] FAISS add_vector took {faiss_add_duration:.3f}s, "
                    f"assigned vector_id={vector_id}"
                )

                # Update database with vector_id (AST bindings are preserved)
                db_update_start = time.time()
                await database.update_chunk_vector_id(
                    chunk_id, vector_id, embedding_model
                )
                db_update_duration = time.time() - db_update_start
                logger.debug(
                    f"[TIMING] [CHUNK {chunk_id}] Database update_chunk_vector_id took {db_update_duration:.3f}s"
                )

                chunk_total_duration = time.time() - chunk_start_time
                batch_processed += 1
                logger.info(
                    f"✅ Vectorized chunk {chunk_id} → vector_id={vector_id} "
                    f"({ast_binding}) in {chunk_total_duration:.3f}s"
                )
                logger.debug(
                    f"[TIMING] [CHUNK {chunk_id}] Total processing time: {chunk_total_duration:.3f}s"
                )
                # Reset empty iterations counter when we successfully process a chunk
                empty_iterations = 0

            except Exception as e:
                logger.error(
                    f"Error processing chunk {chunk.get('id')}: {e}, "
                    "will retry in next cycle",
                    exc_info=True,
                )
                batch_errors += 1
                continue

        # Save FAISS index after batch
        if batch_processed > 0:
            faiss_save_start = time.time()
            try:
                logger.debug(
                    f"[TIMING] Saving FAISS index after processing {batch_processed} chunks"
                )
                self.faiss_manager.save_index()
                faiss_save_duration = time.time() - faiss_save_start
                logger.debug(
                    f"[TIMING] FAISS index save took {faiss_save_duration:.3f}s"
                )
            except Exception as e:
                logger.error(f"Error saving FAISS index: {e}")

    return batch_processed, batch_errors
