"""
FAISS index rebuild from database: load vectors from code_chunks into index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .database_client.client import DatabaseClient
from .embedding_input import EmbeddingInput
from code_analysis.core.docs_markdown_vector_gate import (
    DOCS_MARKDOWN_SOURCE_TYPE,
    sql_and_exclude_docs_markdown_chunks,
)

logger = logging.getLogger(__name__)

REBUILD_FROM_DB_BATCH_SIZE = 500


def _sql_omit_docs_markdown_normalized_chunk_rows() -> str:
    """Exclude ``docs_markdown`` from ``WITH ranked`` (no ``cc`` alias in subquery body)."""
    return (
        f" AND (source_type IS NULL OR source_type != '{DOCS_MARKDOWN_SOURCE_TYPE}') "
    )


async def rebuild_from_database_impl(
    manager: Any,
    database: DatabaseClient,
    svo_client_manager: Optional[Any],
    project_id: Optional[str],
    *,
    omit_docs_markdown: bool = False,
) -> int:
    """
    Rebuild FAISS index from database (implementation).

    Normalizes vector_id in DB, creates fresh index, fetches chunks with embeddings,
    optionally fetches missing embeddings via SVO, and adds vectors to the index.

    Args:
        manager: FaissIndexManager instance (add_vector, save_index, _create_index).
        database: DatabaseClient.
        svo_client_manager: Optional SVO client for fetching missing embeddings.
        project_id: Optional project ID to filter by.
        omit_docs_markdown: When True, exclude ``source_type=docs_markdown`` rows from the
            rebuilt index and from vector_id normalization (aligned with ``docs_indexing``).

    Returns:
        Number of vectors loaded.
    """
    scope_desc = f"project={project_id}" if project_id else "all projects"
    logger.info(
        "Rebuilding FAISS index from database (%s, omit_docs_markdown=%s)...",
        scope_desc,
        omit_docs_markdown,
    )

    norm_omit_sql = ""
    if omit_docs_markdown:
        norm_omit_sql = _sql_omit_docs_markdown_normalized_chunk_rows()

    # Normalize vector_id in database (dense, unique)
    try:
        if project_id:
            database.execute(
                f"""
                WITH ranked AS (
                    SELECT
                        id,
                        (ROW_NUMBER() OVER (ORDER BY created_at, id) - 1) AS new_vector_id
                    FROM code_chunks
                    WHERE project_id = ?
                      AND embedding_model IS NOT NULL
                      AND embedding_vector IS NOT NULL
                      AND (vectorization_skipped IS NULL OR vectorization_skipped = 0)
                      {norm_omit_sql}
                )
                UPDATE code_chunks
                SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
                WHERE id IN (SELECT id FROM ranked)
                """,
                (project_id,),
            )
        else:
            database.execute(
                f"""
                WITH ranked AS (
                    SELECT
                        id,
                        (ROW_NUMBER() OVER (ORDER BY created_at, id) - 1) AS new_vector_id
                    FROM code_chunks
                    WHERE embedding_model IS NOT NULL
                      AND embedding_vector IS NOT NULL
                      AND (vectorization_skipped IS NULL OR vectorization_skipped = 0)
                      {norm_omit_sql}
                )
                UPDATE code_chunks
                SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
                WHERE id IN (SELECT id FROM ranked)
                """,
                None,
            )
    except Exception as e:
        logger.warning(
            "Failed to normalize code_chunks.vector_id mapping: %s",
            e,
            exc_info=True,
        )

    old_vector_count = int(manager.index.ntotal) if manager.index is not None else 0
    manager._create_index()
    if old_vector_count > 0:
        logger.info("Cleared %d vectors from FAISS index (rebuild)", old_vector_count)

    chunks = _fetch_chunks_for_rebuild(
        database, project_id, omit_docs_markdown=omit_docs_markdown
    )
    if not chunks:
        logger.info("No chunks with embeddings found in database")
        manager.save_index()
        return 0

    loaded_count = 0
    missing_embeddings = 0

    # Pass 1: resolve embeddings from the DB-stored embedding_vector where possible;
    # collect the (rare - the fetch SQL already requires embedding_vector IS NOT
    # NULL) chunks with a missing/unparseable stored vector for a single batched
    # SVO fallback call instead of one SVO round-trip per chunk.
    resolved: Dict[Any, np.ndarray] = {}
    svo_fallback_items: List[Tuple[str, Any, Any]] = []

    for chunk in chunks:
        if chunk.get("vector_id") is None:
            continue
        chunk_id = chunk.get("id")
        embedding_vector_json = chunk.get("embedding_vector")
        if embedding_vector_json:
            try:
                embedding_list = json.loads(embedding_vector_json)
                resolved[chunk_id] = np.array(embedding_list, dtype="float32")
                continue
            except Exception as e:
                logger.warning(
                    "Failed to parse embedding_vector for chunk %s: %s",
                    chunk_id,
                    e,
                )
        if svo_client_manager:
            svo_fallback_items.append(
                (chunk.get("chunk_text", ""), chunk_id, chunk.get("embedding_model"))
            )
        else:
            logger.debug(
                "Skipping chunk %s: no embedding in database and no SVO client",
                chunk_id,
            )

    if svo_fallback_items:
        logger.info(
            "Batch-fetching %d embedding(s) from SVO for chunks with missing/"
            "unparseable stored embedding_vector",
            len(svo_fallback_items),
        )
        resolved.update(
            await _fetch_embeddings_from_svo_batch(
                svo_fallback_items, database, svo_client_manager
            )
        )

    # Pass 2: add every resolved embedding to the FAISS index, in original order.
    for chunk in chunks:
        vector_id = chunk.get("vector_id")
        if vector_id is None:
            continue
        embedding_array = resolved.get(chunk.get("id"))
        if embedding_array is None:
            missing_embeddings += 1
            continue

        try:
            manager.add_vector(embedding_array, vector_id=int(vector_id))
            loaded_count += 1
        except Exception as e:
            logger.error(
                "Failed to add vector to FAISS index for chunk %s: %s",
                chunk.get("id"),
                e,
            )
            missing_embeddings += 1

    manager.save_index()
    logger.info(
        "Rebuilt FAISS index: loaded %d vectors, missing %d embeddings",
        loaded_count,
        missing_embeddings,
    )
    return loaded_count


def _fetch_chunks_for_rebuild(
    database: DatabaseClient,
    project_id: Optional[str],
    *,
    omit_docs_markdown: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch all chunks with embeddings from database (batched for DatabaseClient)."""
    chunks: List[Dict[str, Any]] = []
    md_frag = sql_and_exclude_docs_markdown_chunks("cc") if omit_docs_markdown else ""
    sql_common = f"""
        SELECT
            cc.id, cc.file_id, cc.project_id, cc.chunk_uuid, cc.chunk_type,
            cc.chunk_text, cc.chunk_ordinal, cc.vector_id, cc.embedding_model,
            cc.embedding_vector, cc.class_id, cc.function_id, cc.method_id,
            cc.line, cc.ast_node_type, cc.source_type
        FROM code_chunks cc
        WHERE cc.embedding_model IS NOT NULL
          AND cc.embedding_vector IS NOT NULL
          AND (cc.vectorization_skipped IS NULL OR cc.vectorization_skipped = 0)
          {md_frag}
    """
    if project_id:
        sql_common += " AND cc.project_id = ?"
    sql_common += " ORDER BY cc.created_at, cc.id LIMIT ? OFFSET ?"
    offset = 0
    while True:
        params: Tuple[Any, ...]
        if project_id:
            params = (project_id, REBUILD_FROM_DB_BATCH_SIZE, offset)
        else:
            params = (REBUILD_FROM_DB_BATCH_SIZE, offset)
        result = database.execute(sql_common, params)
        batch = result.get("data", []) if isinstance(result, dict) else []
        if not batch:
            break
        chunks.extend(batch)
        offset += len(batch)
        if len(batch) < REBUILD_FROM_DB_BATCH_SIZE:
            break
    return chunks


async def _fetch_embeddings_from_svo_batch(
    items: List[Tuple[str, Any, Any]],
    database: DatabaseClient,
    svo_client_manager: Any,
) -> Dict[Any, np.ndarray]:
    """Batch-request embeddings from SVO for chunks with no usable stored vector.

    ``items`` is a list of ``(chunk_text, chunk_id, embedding_model)``. Issues a
    single ``svo_client_manager.get_embeddings`` call for every item (rather than
    one call per chunk) and saves each successful result back to
    ``code_chunks.embedding_vector`` / ``embedding_model``. Returns a
    ``chunk_id -> embedding array`` map covering only the chunks that succeeded;
    a failure of the whole batch call (e.g. SVO unavailable) yields an empty map
    and every affected chunk is reported as a missing embedding by the caller.
    """
    if not items:
        return {}

    try:
        inputs = [EmbeddingInput(text=text) for text, _chunk_id, _model in items]
        chunks_with_emb = await svo_client_manager.get_embeddings(inputs)
    except Exception as e:
        logger.warning(
            "Failed to get embeddings from SVO for %d chunk(s): %s",
            len(items),
            e,
        )
        return {}

    result: Dict[Any, np.ndarray] = {}
    for (_text, chunk_id, embedding_model), tmp in zip(items, chunks_with_emb):
        embedding = getattr(tmp, "embedding", None)
        if embedding is None:
            continue
        embedding_array = np.array(embedding, dtype="float32")
        save_model = getattr(tmp, "embedding_model", None) or embedding_model
        if save_model and str(save_model).strip():
            try:
                embedding_json = json.dumps(embedding_array.tolist())
                database.execute(
                    "UPDATE code_chunks SET embedding_vector = ?, embedding_model = ? WHERE id = ?",
                    (embedding_json, save_model, chunk_id),
                )
            except Exception as e:
                logger.warning(
                    "Failed to save recovered embedding for chunk %s: %s",
                    chunk_id,
                    e,
                )
        else:
            logger.warning(
                "Embedding service returned no model for chunk %s; not saving "
                "vector to DB",
                chunk_id,
            )
        result[chunk_id] = embedding_array
    return result
