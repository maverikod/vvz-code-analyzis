"""
Module chunks - database operations for code chunks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


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
    token_count: Optional[int] = None,
    class_id: Optional[int] = None,
    function_id: Optional[int] = None,
    method_id: Optional[int] = None,
    line: Optional[int] = None,
    ast_node_type: Optional[str] = None,
    source_type: Optional[str] = None,
    binding_level: int = 0,
) -> int:
    """
    Add or update code chunk. Returns chunk_id.

    Persists chunk text, embedding vector (and model), and token count.
    Uses INSERT OR REPLACE to handle updates based on chunk_uuid (UNIQUE constraint).

    Args:
        file_id: File ID
        project_id: Project ID (UUID4 string)
        chunk_uuid: Unique chunk identifier (UUID5)
        chunk_type: Type of chunk (e.g., "DocBlock")
        chunk_text: Text content of the chunk
        chunk_ordinal: Ordinal position of chunk in file
        vector_id: FAISS index ID (NULL until vectorized)
        embedding_model: Model name used for embedding (NULL until vectorized)
        bm25_score: BM25 relevance score (optional)
        embedding_vector: JSON string containing embedding vector (optional)
        token_count: Number of tokens in chunk (optional)
        class_id: AST binding - class ID (if chunk is from class docstring)
        function_id: AST binding - function ID (if chunk is from function docstring)
        method_id: AST binding - method ID (if chunk is from method docstring)
        line: AST binding - line number in source file
        ast_node_type: AST binding - type of AST node (ClassDef, FunctionDef, etc.)
        source_type: AST binding - source type ('docstring', 'comment', 'file_docstring')
        binding_level: AST binding - nesting level (0 = top level)

    Returns:
        Chunk ID
    """
    if embedding_vector is not None and not (embedding_model and str(embedding_model).strip()):
        raise ValueError(
            "embedding_model is required when embedding_vector is set; "
            "a vector without model cannot be used for search"
        )
    self._execute(
        """
            INSERT OR REPLACE INTO code_chunks
            (
                file_id, project_id, chunk_uuid, chunk_type, chunk_text,
                chunk_ordinal, vector_id, embedding_model, bm25_score,
                embedding_vector, token_count, class_id, function_id, method_id,
                line, ast_node_type, source_type, binding_level,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, julianday('now'))
        """,
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
            token_count,
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
