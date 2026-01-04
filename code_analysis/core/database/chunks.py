"""
Module chunks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Dict, List, Any, Optional


async def add_vector_index(
    self,
    project_id: str,
    entity_type: str,
    entity_id: int,
    vector_id: int,
    vector_dim: int,
    embedding_model: Optional[str] = None,
) -> int:
    """
    Add vector index metadata.

    Args:
        project_id: Project ID
        entity_type: Type of entity (file, class, method, function, chunk)
        entity_id: ID of the entity
        vector_id: FAISS vector index ID
        vector_dim: Vector dimension
        embedding_model: Model used for embedding

    Returns:
        Vector index record ID
    """
    existing = self._fetchone(
        "\n            SELECT id FROM vector_index\n            WHERE project_id = ? AND entity_type = ? AND entity_id = ?\n        ",
        (project_id, entity_type, entity_id),
    )
    if existing:
        self._execute(
            "\n                UPDATE vector_index\n                SET vector_id = ?, vector_dim = ?, embedding_model = ?\n                WHERE id = ?\n            ",
            (vector_id, vector_dim, embedding_model, existing["id"]),
        )
        self._commit()
        return existing["id"]
    else:
        self._execute(
            "\n                INSERT INTO vector_index\n                (project_id, entity_type, entity_id, vector_id, vector_dim, embedding_model)\n                VALUES (?, ?, ?, ?, ?, ?)\n            ",
            (
                project_id,
                entity_type,
                entity_id,
                vector_id,
                vector_dim,
                embedding_model,
            ),
        )
        self._commit()
        result = self._lastrowid()
        assert result is not None
        return result


async def get_vector_index(
    self, project_id: str, entity_type: str, entity_id: int
) -> Optional[Dict[str, Any]]:
    """
    Get vector index metadata.

    Args:
        project_id: Project ID
        entity_type: Type of entity
        entity_id: ID of the entity

    Returns:
        Vector index record or None
    """
    return self._fetchone(
        "\n            SELECT * FROM vector_index\n            WHERE project_id = ? AND entity_type = ? AND entity_id = ?\n        ",
        (project_id, entity_type, entity_id),
    )


async def add_code_chunk(
    self,
    file_id: int,
    project_id: str,
    chunk_uuid: str,
    chunk_type: str,
    chunk_text: str,
    chunk_ordinal: Optional[int] = None,
    vector_id: Optional[int] = None,
    embedding_model: Optional[str] = None,
    bm25_score: Optional[float] = None,
    embedding_vector: Optional[str] = None,
    class_id: Optional[int] = None,
    function_id: Optional[int] = None,
    method_id: Optional[int] = None,
    line: Optional[int] = None,
    ast_node_type: Optional[str] = None,
    source_type: Optional[str] = None,
    binding_level: int = 0,
) -> int:
    """
    Add code chunk from semantic chunker with AST node binding.

    Args:
        file_id: File ID
        project_id: Project ID
        chunk_uuid: UUID of the chunk
        chunk_type: Type of chunk (DocBlock, CodeBlock, etc.)
        chunk_text: Chunk text content
        chunk_ordinal: Order of chunk in original text
        vector_id: FAISS vector index ID
        embedding_model: Model used for embedding
        class_id: Class ID if chunk is bound to a class
        function_id: Function ID if chunk is bound to a function
        method_id: Method ID if chunk is bound to a method
        line: Line number in file
        ast_node_type: Type of AST node (ClassDef, FunctionDef, etc.)
        source_type: Source type ('docstring', 'comment', 'file_docstring')

    Returns:
        Chunk ID
    """
    existing = self._fetchone(
        "\n                SELECT id FROM code_chunks\n                WHERE chunk_uuid = ?\n            ",
        (chunk_uuid,),
    )
    if existing:
        self._execute(
            "\n                    UPDATE code_chunks\n                    SET chunk_text = ?, chunk_type = ?, chunk_ordinal = ?,\n                        vector_id = ?, embedding_model = ?,\n                        bm25_score = ?, embedding_vector = ?,\n                        class_id = ?, function_id = ?, method_id = ?,\n                        line = ?, ast_node_type = ?, source_type = ?,\n                        binding_level = ?\n                    WHERE id = ?\n                ",
            (
                chunk_text,
                chunk_type,
                chunk_ordinal,
                vector_id,
                embedding_model,
                bm25_score,
                embedding_vector,
                class_id,
                function_id,
                method_id,
                line,
                ast_node_type,
                source_type,
                binding_level,
                existing["id"],
            ),
        )
        self._commit()
        return existing["id"]
    else:
        self._execute(
            "\n                    INSERT INTO code_chunks\n                    (file_id, project_id, chunk_uuid, chunk_type, chunk_text,\n                     chunk_ordinal, vector_id, embedding_model, bm25_score, embedding_vector,\n                     class_id, function_id, method_id, line, ast_node_type, source_type, binding_level)\n                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n                ",
            (
                file_id,
                project_id,
                chunk_uuid,
                chunk_type,
                chunk_text,
                chunk_ordinal,
                vector_id,
                embedding_model,
                bm25_score,
                embedding_vector,
                class_id,
                function_id,
                method_id,
                line,
                ast_node_type,
                source_type,
                binding_level,
            ),
        )
        self._commit()
        result = self._lastrowid()
        assert result is not None
        return result


async def get_code_chunks(
    self,
    file_id: Optional[int] = None,
    project_id: Optional[str] = None,
    limit: int = 100,
    include_deleted: bool = False,
) -> List[Dict[str, Any]]:
    """
    Get code chunks.

    Args:
        file_id: Filter by file ID (optional)
        project_id: Filter by project ID (optional)
        limit: Maximum results
        include_deleted: If True, include chunks from deleted files (default: False)

    Returns:
        List of chunk records
    """
    if include_deleted:
        query = "SELECT * FROM code_chunks WHERE 1=1"
    else:
        query = """
            SELECT cc.* FROM code_chunks cc
            JOIN files f ON cc.file_id = f.id
            WHERE (f.deleted = 0 OR f.deleted IS NULL)
        """
    params = []
    if file_id:
        query += " AND cc.file_id = ?" if not include_deleted else " AND file_id = ?"
        params.append(file_id)
    if project_id:
        query += (
            " AND cc.project_id = ?" if not include_deleted else " AND project_id = ?"
        )
        params.append(project_id)
    query += " ORDER BY chunk_ordinal, id LIMIT ?"
    params.append(limit)
    return self._fetchall(query, tuple(params))


def get_all_chunks_for_faiss_rebuild(self) -> List[Dict[str, Any]]:
    """
    Get all code chunks with embeddings for FAISS index rebuild.

    Returns chunks that have vector_id and embedding_model.
    Used on server startup to rebuild FAISS index from database.

    NOTE: This method should be called when FaissIndexManager initializes.
    It will:
    1. Get all chunks with vector_id and embedding_model
    2. For each chunk, get embedding from SVO service (if not cached)
    3. Add to FAISS index with corresponding vector_id

    Returns:
        List of chunk records with vector_id and embedding_model
    """
    return self._fetchall(
        "\n                SELECT id, file_id, project_id, chunk_uuid, chunk_text,\n                       vector_id, embedding_model, chunk_type, embedding_vector\n                FROM code_chunks\n                WHERE embedding_model IS NOT NULL\n                  AND embedding_vector IS NOT NULL\n                ORDER BY id\n                "
    )


async def get_non_vectorized_chunks(
    self, project_id: Optional[str] = None, limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get code chunks that are not yet vectorized (vector_id IS NULL).

    Uses index idx_code_chunks_not_vectorized for fast lookup.

    **Important**: Always excludes chunks from deleted files (deleted=1).

    Args:
        project_id: Filter by project ID (optional)
        limit: Maximum number of chunks to return

    Returns:
        List of chunk records without vector_id (only from non-deleted files)
    """
    if project_id:
        return self._fetchall(
            "\n                    SELECT cc.id, cc.file_id, cc.project_id, cc.chunk_uuid, cc.chunk_text,\n                           cc.chunk_type, cc.chunk_ordinal, cc.embedding_model,\n                           cc.class_id, cc.function_id, cc.method_id, cc.line, cc.ast_node_type, cc.source_type\n                    FROM code_chunks cc\n                    JOIN files f ON cc.file_id = f.id\n                    WHERE cc.vector_id IS NULL AND cc.project_id = ?\n                    AND (f.deleted = 0 OR f.deleted IS NULL)\n                    ORDER BY (cc.embedding_vector IS NOT NULL) DESC, cc.id\n                    LIMIT ?\n                    ",
            (project_id, limit),
        )
    else:
        return self._fetchall(
            "\n                    SELECT cc.id, cc.file_id, cc.project_id, cc.chunk_uuid, cc.chunk_text,\n                           cc.chunk_type, cc.chunk_ordinal, cc.embedding_model,\n                           cc.class_id, cc.function_id, cc.method_id, cc.line, cc.ast_node_type, cc.source_type\n                    FROM code_chunks cc\n                    JOIN files f ON cc.file_id = f.id\n                    WHERE cc.vector_id IS NULL\n                    AND (f.deleted = 0 OR f.deleted IS NULL)\n                    ORDER BY (cc.embedding_vector IS NOT NULL) DESC, cc.id\n                    LIMIT ?\n                    ",
            (limit,),
        )


async def update_chunk_vector_id(
    self, chunk_id: int, vector_id: int, embedding_model: Optional[str] = None
) -> None:
    """
    Update vector_id for a chunk after vectorization.

    After this update, the chunk will automatically be excluded from
    the partial index idx_code_chunks_not_vectorized (WHERE vector_id IS NULL).

    Args:
        chunk_id: Chunk ID
        vector_id: FAISS vector index ID
        embedding_model: Optional embedding model name
    """
    if embedding_model:
        self._execute(
            "\n                    UPDATE code_chunks\n                    SET vector_id = ?, embedding_model = ?\n                    WHERE id = ?\n                    ",
            (vector_id, embedding_model, chunk_id),
        )
    else:
        self._execute(
            "\n                    UPDATE code_chunks\n                    SET vector_id = ?\n                    WHERE id = ?\n                    ",
            (vector_id, chunk_id),
        )
    self._commit()
