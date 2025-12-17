"""
Semantic search command implementation.

Provides semantic search functionality using FAISS vector index.
Returns AST nodes with full context for matched code chunks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import numpy as np

from ..core import CodeDatabase

logger = logging.getLogger(__name__)


class SemanticSearchCommand:
    """
    Command for semantic search using vector embeddings.
    
    Searches code by semantic similarity and returns AST nodes with context.
    """

    def __init__(
        self,
        database: CodeDatabase,
        project_id: str,
        faiss_manager=None,
        svo_client_manager=None,
    ):
        """
        Initialize semantic search command.

        Args:
            database: Database instance
            project_id: Project UUID
            faiss_manager: FAISS index manager (optional)
            svo_client_manager: SVO client manager for embeddings (optional)
        """
        self.database = database
        self.project_id = project_id
        self.faiss_manager = faiss_manager
        self.svo_client_manager = svo_client_manager

    async def search(
        self,
        query: str,
        k: int = 10,
        max_distance: Optional[float] = None,
        include_ast_node: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search.

        Args:
            query: Text query to search for
            k: Number of results to return (default: 10)
            max_distance: Maximum distance threshold (optional)
            include_ast_node: If True, include full AST node JSON (default: False)

        Returns:
            List of search results, each containing:
            - file_path: Path to file
            - line: Line number
            - ast_node_type: Type of AST node
            - ast_node_name: Name of node (if applicable)
            - class_name: Class name (if chunk is bound to class)
            - function_name: Function name (if chunk is bound to function)
            - method_name: Method name (if chunk is bound to method)
            - chunk_text: Text content of the chunk
            - source_type: Source type ('docstring', 'comment', 'file_docstring')
            - relevance_score: Distance score (lower is better)
            - ast_node: Full AST node JSON (if include_ast_node=True)
        """
        if not self.faiss_manager:
            raise RuntimeError("FAISS manager is not available. Semantic search requires FAISS index.")

        if not self.svo_client_manager:
            raise RuntimeError("SVO client manager is not available. Semantic search requires embedding service.")

        # Get embedding for query
        try:
            # Create dummy chunk for query
            class QueryChunk:
                def __init__(self, text):
                    self.body = text
                    self.text = text

            query_chunks = [QueryChunk(query)]
            chunks_with_emb = await self.svo_client_manager.get_embeddings(query_chunks)
            
            if not chunks_with_emb or len(chunks_with_emb) == 0:
                logger.warning("Failed to get embedding for query")
                return []

            query_embedding = getattr(chunks_with_emb[0], "embedding", None)
            if query_embedding is None:
                logger.warning("Query chunk has no embedding")
                return []

            query_vector = np.array(query_embedding, dtype="float32")

        except Exception as e:
            logger.error(f"Error getting embedding for query: {e}")
            return []

        # Search in FAISS index
        try:
            distances, vector_ids = self.faiss_manager.search(query_vector, k=k * 2)  # Get more to filter
        except Exception as e:
            logger.error(f"Error searching FAISS index: {e}")
            return []

        if len(vector_ids) == 0:
            return []

        # Filter by max_distance if specified
        if max_distance is not None:
            filtered_indices = [i for i, dist in enumerate(distances) if dist <= max_distance]
            vector_ids = vector_ids[filtered_indices]
            distances = distances[filtered_indices]

        # Get chunks from database by vector_ids
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()
        
        # Build query to get chunks with all context
        placeholders = ",".join("?" * len(vector_ids))
        query_sql = f"""
            SELECT 
                cc.id,
                cc.file_id,
                cc.project_id,
                cc.chunk_text,
                cc.vector_id,
                cc.line,
                cc.ast_node_type,
                cc.source_type,
                cc.class_id,
                cc.function_id,
                cc.method_id,
                f.path as file_path,
                c.name as class_name,
                func.name as function_name,
                m.name as method_name
            FROM code_chunks cc
            JOIN files f ON cc.file_id = f.id
            LEFT JOIN classes c ON cc.class_id = c.id
            LEFT JOIN functions func ON cc.function_id = func.id
            LEFT JOIN methods m ON cc.method_id = m.id
            WHERE cc.vector_id IN ({placeholders})
            AND cc.project_id = ?
            ORDER BY cc.vector_id
        """
        
        cursor.execute(query_sql, [int(vid) for vid in vector_ids] + [self.project_id])
        chunks = cursor.fetchall()

        # Create mapping from vector_id to chunk data
        vector_id_to_chunk = {}
        for chunk in chunks:
            vector_id = chunk[4]  # vector_id column
            vector_id_to_chunk[vector_id] = {
                "id": chunk[0],
                "file_id": chunk[1],
                "project_id": chunk[2],
                "chunk_text": chunk[3],
                "vector_id": chunk[4],
                "line": chunk[5],
                "ast_node_type": chunk[6],
                "source_type": chunk[7],
                "class_id": chunk[8],
                "function_id": chunk[9],
                "method_id": chunk[10],
                "file_path": chunk[11],
                "class_name": chunk[12],
                "function_name": chunk[13],
                "method_name": chunk[14],
            }

        # Build results in order of relevance
        results = []
        for i, vector_id in enumerate(vector_ids):
            if vector_id not in vector_id_to_chunk:
                continue  # Skip if chunk not found (might be from different project)

            chunk_data = vector_id_to_chunk[vector_id]
            distance = float(distances[i])

            result = {
                "file_path": chunk_data["file_path"],
                "file_id": chunk_data["file_id"],
                "line": chunk_data["line"],
                "ast_node_type": chunk_data["ast_node_type"],
                "class_name": chunk_data["class_name"],
                "function_name": chunk_data["function_name"],
                "method_name": chunk_data["method_name"],
                "chunk_text": chunk_data["chunk_text"],
                "source_type": chunk_data["source_type"],
                "relevance_score": distance,
            }

            # Get AST node name if available
            ast_node_name = None
            if chunk_data["class_name"]:
                ast_node_name = chunk_data["class_name"]
            elif chunk_data["method_name"]:
                ast_node_name = chunk_data["method_name"]
            elif chunk_data["function_name"]:
                ast_node_name = chunk_data["function_name"]
            
            if ast_node_name:
                result["ast_node_name"] = ast_node_name

            # Get full AST node if requested
            if include_ast_node:
                try:
                    ast_record = await self.database.get_ast_tree(chunk_data["file_id"])
                    if ast_record and ast_record.get("ast_json"):
                        ast_json = json.loads(ast_record["ast_json"])
                        # Find the specific node by line and type
                        ast_node = self._find_ast_node(
                            ast_json, chunk_data["line"], chunk_data["ast_node_type"]
                        )
                        if ast_node:
                            result["ast_node"] = ast_node
                except Exception as e:
                    logger.debug(f"Failed to get AST node: {e}")

            results.append(result)

            if len(results) >= k:
                break

        return results

    def _find_ast_node(
        self, ast_dict: Dict[str, Any], line: Optional[int], node_type: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Find specific AST node in AST dictionary by line and type.

        Args:
            ast_dict: AST tree as dictionary
            line: Line number to search for
            node_type: Type of node to search for

        Returns:
            AST node dictionary or None
        """
        if not isinstance(ast_dict, dict):
            return None

        # Check if this node matches
        current_type = ast_dict.get("_type")
        current_line = ast_dict.get("lineno")

        if line and current_line == line:
            if node_type is None or current_type == node_type:
                return ast_dict

        # Recursively search children
        for key, value in ast_dict.items():
            if key == "_type":
                continue
            if isinstance(value, dict):
                found = self._find_ast_node(value, line, node_type)
                if found:
                    return found
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        found = self._find_ast_node(item, line, node_type)
                        if found:
                            return found

        return None

