"""
Chunk query/update helpers for CodeDatabase. Extracted from base.py to reduce file size.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List, Optional, cast

from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE_F
from code_analysis.core.vector_search_backend import uses_pgvector_ann_for_database


def get_all_chunks_for_faiss_rebuild(
    db: Any, project_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all code chunks with embeddings for FAISS index rebuild.

    If project_id is provided, returns chunks for that project only.
    If project_id is None, returns chunks for all projects (legacy mode).

    Args:
        db: CodeDatabase instance (or duck-typed with _fetchall).
        project_id: Optional project ID to filter by.

    Returns:
        List of chunk records with embeddings.
    """
    if project_id:
        return cast(
            List[Dict[str, Any]],
            db._fetchall(
                """
            SELECT 
                cc.id,
                cc.file_id,
                cc.project_id,
                cc.chunk_uuid,
                cc.chunk_type,
                cc.chunk_text,
                cc.chunk_ordinal,
                cc.vector_id,
                cc.embedding_model,
                cc.embedding_vector,
                cc.class_id,
                cc.function_id,
                cc.method_id,
                cc.line,
                cc.ast_node_type,
                cc.source_type
            FROM code_chunks cc
            WHERE cc.project_id = ?
              AND cc.embedding_model IS NOT NULL
              AND cc.embedding_vector IS NOT NULL
            ORDER BY cc.created_at, cc.id
            """,
                (project_id,),
            ),
        )
    else:
        return cast(
            List[Dict[str, Any]],
            db._fetchall(
                """
            SELECT 
                cc.id,
                cc.file_id,
                cc.project_id,
                cc.chunk_uuid,
                cc.chunk_type,
                cc.chunk_text,
                cc.chunk_ordinal,
                cc.vector_id,
                cc.embedding_model,
                cc.embedding_vector,
                cc.class_id,
                cc.function_id,
                cc.method_id,
                cc.line,
                cc.ast_node_type,
                cc.source_type
            FROM code_chunks cc
            WHERE cc.embedding_model IS NOT NULL
              AND cc.embedding_vector IS NOT NULL
            ORDER BY cc.created_at, cc.id
                """
            ),
        )


def get_non_vectorized_chunks(
    db: Any,
    project_id: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Get chunks that have embeddings but are not yet in the ANN store.

    For FAISS backends this means ``vector_id IS NULL``; for PostgreSQL pgvector
    it means ``embedding_vec IS NULL``.
    """
    ann_pending = (
        "cc.embedding_vec IS NULL"
        if uses_pgvector_ann_for_database(db)
        else "cc.vector_id IS NULL"
    )
    return cast(
        List[Dict[str, Any]],
        db._fetchall(
            f"""
        SELECT 
            cc.id,
            cc.file_id,
            cc.project_id,
            cc.chunk_uuid,
            cc.chunk_type,
            cc.chunk_text,
            cc.chunk_ordinal,
            cc.vector_id,
            cc.embedding_model,
            cc.embedding_vector,
            cc.class_id,
            cc.function_id,
            cc.method_id,
            cc.line,
            cc.ast_node_type,
            cc.source_type
        FROM code_chunks cc
        INNER JOIN files f ON cc.file_id = f.id
        WHERE cc.project_id = ?
          AND {WHERE_FILES_ACTIVE_F}
          AND cc.embedding_vector IS NOT NULL
          AND {ann_pending}
        ORDER BY cc.created_at, cc.id
        LIMIT ?
        """,
            (project_id, limit),
        ),
    )


async def update_chunk_vector_id(
    db: Any,
    chunk_id: str,
    vector_id: int,
    embedding_model: Optional[str] = None,
) -> None:
    """
    Update chunk with vector_id and embedding_model.

    Called after adding vector to FAISS index.

    Args:
        db: CodeDatabase instance (or duck-typed with _execute, _commit).
        chunk_id: Chunk primary key (UUID string).
        vector_id: FAISS index position (vector ID).
        embedding_model: Optional embedding model name.
    """
    if embedding_model:
        db._execute(
            """
            UPDATE code_chunks
            SET vector_id = ?, embedding_model = ?
            WHERE id = ?
            """,
            (vector_id, embedding_model, chunk_id),
        )
    else:
        db._execute(
            """
            UPDATE code_chunks
            SET vector_id = ?
            WHERE id = ?
            """,
            (vector_id, chunk_id),
        )
    db._commit()
