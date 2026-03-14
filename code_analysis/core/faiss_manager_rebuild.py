"""
FAISS index rebuild from database: load vectors from code_chunks into index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from .database import CodeDatabase
from .database_client.client import DatabaseClient

logger = logging.getLogger(__name__)

REBUILD_FROM_DB_BATCH_SIZE = 500


async def rebuild_from_database_impl(
    manager: Any,
    database: Union[CodeDatabase, DatabaseClient],
    svo_client_manager: Optional[Any],
    project_id: Optional[str],
) -> int:
    """
    Rebuild FAISS index from database (implementation).

    Normalizes vector_id in DB, creates fresh index, fetches chunks with embeddings,
    optionally fetches missing embeddings via SVO, and adds vectors to the index.

    Args:
        manager: FaissIndexManager instance (add_vector, save_index, _create_index).
        database: CodeDatabase or DatabaseClient.
        svo_client_manager: Optional SVO client for fetching missing embeddings.
        project_id: Optional project ID to filter by.

    Returns:
        Number of vectors loaded.
    """
    scope_desc = f"project={project_id}" if project_id else "all projects"
    logger.info("Rebuilding FAISS index from database (%s)...", scope_desc)

    # Normalize vector_id in database (dense, unique)
    try:
        if isinstance(database, DatabaseClient):
            if project_id:
                database.execute(
                    """
                    WITH ranked AS (
                        SELECT
                            id,
                            (ROW_NUMBER() OVER (ORDER BY id) - 1) AS new_vector_id
                        FROM code_chunks
                        WHERE project_id = ?
                          AND embedding_model IS NOT NULL
                          AND embedding_vector IS NOT NULL
                    )
                    UPDATE code_chunks
                    SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
                    WHERE id IN (SELECT id FROM ranked)
                    """,
                    (project_id,),
                )
            else:
                database.execute(
                    """
                    WITH ranked AS (
                        SELECT
                            id,
                            (ROW_NUMBER() OVER (ORDER BY id) - 1) AS new_vector_id
                        FROM code_chunks
                        WHERE embedding_model IS NOT NULL
                          AND embedding_vector IS NOT NULL
                    )
                    UPDATE code_chunks
                    SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
                    WHERE id IN (SELECT id FROM ranked)
                    """,
                    None,
                )
        else:
            if project_id:
                database._execute(
                    """
                    WITH ranked AS (
                        SELECT
                            id,
                            (ROW_NUMBER() OVER (ORDER BY id) - 1) AS new_vector_id
                        FROM code_chunks
                        WHERE project_id = ?
                          AND embedding_model IS NOT NULL
                          AND embedding_vector IS NOT NULL
                    )
                    UPDATE code_chunks
                    SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
                    WHERE id IN (SELECT id FROM ranked)
                    """,
                    (project_id,),
                )
            else:
                database._execute(
                    """
                    WITH ranked AS (
                        SELECT
                            id,
                            (ROW_NUMBER() OVER (ORDER BY id) - 1) AS new_vector_id
                        FROM code_chunks
                        WHERE embedding_model IS NOT NULL
                          AND embedding_vector IS NOT NULL
                    )
                    UPDATE code_chunks
                    SET vector_id = (SELECT new_vector_id FROM ranked WHERE ranked.id = code_chunks.id)
                    WHERE id IN (SELECT id FROM ranked)
                    """
                )
            database._commit()
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

    chunks = _fetch_chunks_for_rebuild(database, project_id)
    if not chunks:
        logger.info("No chunks with embeddings found in database")
        manager.save_index()
        return 0

    loaded_count = 0
    missing_embeddings = 0

    for chunk in chunks:
        vector_id = chunk.get("vector_id")
        embedding_vector_json = chunk.get("embedding_vector")
        chunk_text = chunk.get("chunk_text", "")
        chunk_id = chunk.get("id")
        embedding_model = chunk.get("embedding_model")

        if vector_id is None:
            continue

        embedding_array = await _embedding_from_chunk(
            chunk,
            embedding_vector_json,
            chunk_text,
            chunk_id,
            embedding_model,
            database,
            svo_client_manager,
        )
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

    if not isinstance(database, DatabaseClient):
        try:
            database._commit()
        except Exception:
            pass

    manager.save_index()
    logger.info(
        "Rebuilt FAISS index: loaded %d vectors, missing %d embeddings",
        loaded_count,
        missing_embeddings,
    )
    return loaded_count


def _fetch_chunks_for_rebuild(
    database: Union[CodeDatabase, DatabaseClient],
    project_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Fetch all chunks with embeddings from database (batched for DatabaseClient)."""
    chunks: List[Dict[str, Any]] = []
    if isinstance(database, DatabaseClient):
        sql_common = """
            SELECT
                cc.id, cc.file_id, cc.project_id, cc.chunk_uuid, cc.chunk_type,
                cc.chunk_text, cc.chunk_ordinal, cc.vector_id, cc.embedding_model,
                cc.embedding_vector, cc.class_id, cc.function_id, cc.method_id,
                cc.line, cc.ast_node_type, cc.source_type
            FROM code_chunks cc
            WHERE cc.embedding_model IS NOT NULL
              AND cc.embedding_vector IS NOT NULL
        """
        if project_id:
            sql_common += " AND cc.project_id = ?"
        sql_common += " ORDER BY cc.id LIMIT ? OFFSET ?"
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
    else:
        chunks = database.get_all_chunks_for_faiss_rebuild(project_id=project_id)
    return chunks


async def _embedding_from_chunk(
    chunk: Dict[str, Any],
    embedding_vector_json: Any,
    chunk_text: str,
    chunk_id: Any,
    embedding_model: Any,
    database: Union[CodeDatabase, DatabaseClient],
    svo_client_manager: Optional[Any],
) -> Optional[np.ndarray]:
    """Get embedding array from chunk: DB first, then SVO if missing. Returns None if unavailable."""
    embedding_array = None

    if embedding_vector_json:
        try:
            embedding_list = json.loads(embedding_vector_json)
            embedding_array = np.array(embedding_list, dtype="float32")
        except Exception as e:
            logger.warning(
                "Failed to parse embedding_vector for chunk %s: %s",
                chunk.get("id"),
                e,
            )

    if embedding_array is None and svo_client_manager:
        embedding_array = await _fetch_embedding_from_svo(
            chunk_text,
            chunk_id,
            embedding_model,
            database,
            svo_client_manager,
            chunk.get("id"),
        )
    elif embedding_array is None:
        logger.debug(
            "Skipping chunk %s: no embedding in database and no SVO client",
            chunk.get("id"),
        )

    return embedding_array


async def _fetch_embedding_from_svo(
    chunk_text: str,
    chunk_id: Any,
    embedding_model: Any,
    database: Union[CodeDatabase, DatabaseClient],
    svo_client_manager: Any,
    chunk_id_log: Any,
) -> Optional[np.ndarray]:
    """Request embedding from SVO; optionally save to DB. Returns array or None."""

    class _TmpChunk:
        def __init__(self: "_TmpChunk", text: str) -> None:
            self.body = text
            self.text = text

    try:
        tmp = _TmpChunk(chunk_text)
        chunks_with_emb = await svo_client_manager.get_embeddings([tmp])
        if not chunks_with_emb or not hasattr(chunks_with_emb[0], "embedding"):
            return None
        embedding = getattr(chunks_with_emb[0], "embedding")
        if embedding is None:
            return None
        embedding_array = np.array(embedding, dtype="float32")
        save_model = (
            getattr(chunks_with_emb[0], "embedding_model", None) or embedding_model
        )
        if save_model and str(save_model).strip():
            try:
                embedding_json = json.dumps(embedding_array.tolist())
                if isinstance(database, CodeDatabase):
                    database._execute(
                        "UPDATE code_chunks SET embedding_vector = ?, embedding_model = ? WHERE id = ?",
                        (embedding_json, save_model, chunk_id),
                    )
            except Exception as e:
                logger.warning("Failed to save embedding to database: %s", e)
        else:
            logger.warning(
                "Embedding service returned no model; not saving vector to DB"
            )
        return embedding_array
    except Exception as e:
        logger.warning(
            "Failed to get embedding from SVO for chunk %s: %s",
            chunk_id_log,
            e,
        )
        return None
