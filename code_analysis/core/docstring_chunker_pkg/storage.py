"""
Module storage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def _save_chunks(
    self,
    chunks: List[Any],
    item: Dict[str, Any],
    file_path: Path,
    file_id: int,
    project_id: str,
    binding_level: int = 0,
) -> None:
    """
    Save chunks to database with embeddings and BM25.

    Args:
        chunks: List of chunks from chunker
        item: Original item with metadata
        file_path: Path to file
        file_id: File ID in database
        project_id: Project ID
    """
    # Resolve entity IDs from database
    class_id = None
    function_id = None
    method_id = None

    if item.get("class_name"):
        with self.database._lock:
            assert self.database.conn is not None
            cursor = self.database.conn.cursor()
            cursor.execute(
                "SELECT id FROM classes WHERE file_id = ? AND name = ?",
                (file_id, item["class_name"]),
            )
            row = cursor.fetchone()
            if row:
                class_id = row[0]

                # If it's a method, get method_id
                if item.get("method_name"):
                    cursor.execute(
                        "SELECT id FROM methods WHERE class_id = ? AND name = ?",
                        (class_id, item["method_name"]),
                    )
                    row = cursor.fetchone()
                    if row:
                        method_id = row[0]

    if item.get("function_name") and not method_id:
        with self.database._lock:
            assert self.database.conn is not None
            cursor = self.database.conn.cursor()
            cursor.execute(
                "SELECT id FROM functions WHERE file_id = ? AND name = ?",
                (file_id, item["function_name"]),
            )
            row = cursor.fetchone()
            if row:
                function_id = row[0]

    # Save chunks to database with embeddings and BM25
    for idx, chunk in enumerate(chunks):
        chunk_uuid = str(uuid.uuid4())
        chunk_text = getattr(chunk, "body", "") or getattr(chunk, "text", "")
        chunk_type = getattr(chunk, "type", "DocBlock") or "DocBlock"
        chunk_ordinal = getattr(chunk, "ordinal", None)

        # Extract embedding if chunker returned it (chunker may return embeddings)
        embedding = None
        embedding_vector_json = None
        embedding_model = None
        vector_id = None

        # Check if chunk has embedding from chunker
        if (
            hasattr(chunk, "embedding")
            and getattr(chunk, "embedding", None) is not None
        ):
            embedding = getattr(chunk, "embedding")
            # Convert to JSON string for database storage
            import json

            try:
                if hasattr(embedding, "tolist"):
                    embedding_vector_json = json.dumps(embedding.tolist())
                elif isinstance(embedding, (list, tuple)):
                    embedding_vector_json = json.dumps(list(embedding))
                else:
                    embedding_vector_json = json.dumps(embedding)
                embedding_model = getattr(chunk, "embedding_model", None)
                logger.debug(
                    f"Chunk {idx+1}/{len(chunks)} has embedding from chunker "
                    f"(model={embedding_model})"
                )
            except Exception as e:
                logger.warning(f"Failed to serialize embedding for chunk {idx+1}: {e}")
        else:
            # Embedding will be obtained by vectorization worker
            logger.debug(
                f"Chunk {idx+1}/{len(chunks)} has no embedding from chunker, "
                "will be processed by vectorization worker"
            )

        # Extract BM25 score
        bm25_score = None
        if hasattr(chunk, "bm25"):
            bm25_score = getattr(chunk, "bm25", None)
        elif hasattr(chunk, "bm25_score"):
            bm25_score = getattr(chunk, "bm25_score", None)

        # Save chunk to database
        chunk_id = await self.database.add_code_chunk(
            file_id=file_id,
            project_id=project_id,
            chunk_uuid=chunk_uuid,
            chunk_type=chunk_type,
            chunk_text=chunk_text,
            chunk_ordinal=chunk_ordinal,
            vector_id=vector_id,
            embedding_model=embedding_model,
            bm25_score=bm25_score,
            embedding_vector=embedding_vector_json,
            class_id=class_id,
            function_id=function_id,
            method_id=method_id,
            line=item.get("line"),
            ast_node_type=item.get("ast_node_type"),
            source_type=item.get("type"),
            binding_level=binding_level,
        )

        logger.info(
            f"Saved chunk {idx+1}/{len(chunks)} to database: id={chunk_id}, "
            f"vector_id={vector_id}, has_embedding={embedding_vector_json is not None}, "
            f"has_bm25={bm25_score is not None}"
        )


async def close(self) -> None:
    """Close client connections."""
    # SVOClientManager handles its own cleanup
    pass
