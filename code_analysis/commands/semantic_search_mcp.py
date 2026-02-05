"""
MCP command wrapper for semantic search.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from ..core.faiss_manager import FaissIndexManager
from ..core.storage_paths import resolve_storage_paths, get_faiss_index_path

logger = logging.getLogger(__name__)


class SemanticSearchMCPCommand(BaseMCPCommand):
    """Perform semantic search using embeddings and a FAISS index.

    This MCP command requires real embedding service to be available.
    No fallback mechanisms - raises exception if service is unavailable.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Human readable description.
        category: Command category.
        author: Author name.
        email: Author email.
        use_queue: Whether command runs via queue.
    """

    name = "semantic_search"
    version = "1.0.0"
    descr = "Perform semantic search using embeddings and FAISS vectors"
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["SemanticSearchMCPCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema describing command parameters.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "query": {
                    "type": "string",
                    "description": "Search query text",
                },
                "k": {
                    "type": "integer",
                    "description": "Number of results to return (1-100)",
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum similarity score (0.0-1.0)",
                },
            },
            "required": ["project_id", "query"],
            "additionalProperties": False,
        }

    async def execute(
        self: "SemanticSearchMCPCommand",
        project_id: str,
        query: str,
        k: int = 10,
        min_score: Optional[float] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """Execute semantic search.

        Args:
            self: Command instance.
            project_id: Project UUID (from create_project or list_projects).
            query: Search query text.
            k: Number of results to return.
            min_score: Optional minimum similarity score threshold.

        Returns:
            SuccessResult with search results or ErrorResult on failure.
        """
        try:
            root_path = self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)
            try:
                import json

                config_path = self._resolve_config_path()
                if not config_path.exists():
                    return ErrorResult(
                        message=f"Server configuration file not found: {config_path}",
                        code="CONFIG_NOT_FOUND",
                    )
                with open(config_path, "r", encoding="utf-8") as f:
                    config_dict = json.load(f)

                # Extract code_analysis config (may be nested)
                code_analysis_config = config_dict.get("code_analysis", config_dict)
                vector_dim = int(code_analysis_config.get("vector_dim", 384))

                # Resolve storage paths (one index per project)
                storage_paths = resolve_storage_paths(
                    config_data=config_dict, config_path=config_path
                )

                # One index per project: {faiss_dir}/{project_id}.bin
                index_path = get_faiss_index_path(storage_paths.faiss_dir, project_id)

                if not index_path.exists():
                    return ErrorResult(
                        message="FAISS index not found. Run update_indexes first.",
                        code="FAISS_INDEX_NOT_FOUND",
                        details={
                            "index_path": str(index_path),
                            "project_id": project_id,
                        },
                    )

                try:
                    faiss_manager = FaissIndexManager(
                        index_path=str(index_path),
                        vector_dim=vector_dim,
                    )
                    faiss_manager._load_index()
                except ImportError as e:
                    return SuccessResult(
                        data={
                            "query": query,
                            "results": [],
                            "count": 0,
                            "warning": "FAISS is not installed; returning empty results",
                            "details": {"error": str(e), "index_path": str(index_path)},
                        }
                    )

                # Get query embedding using real embedding service
                from ..core.svo_client_manager import SVOClientManager

                # Config and cert paths in config are relative to config file directory (server root)
                config_root = config_path.parent
                svo_client_manager = SVOClientManager(config_dict, root_dir=config_root)
                await svo_client_manager.initialize()

                try:
                    # Create dummy chunk object for embedding
                    class QueryChunk:
                        def __init__(self, text: str):
                            self.body = text
                            self.text = text

                    query_chunk = QueryChunk(query)
                    chunks_with_emb = await svo_client_manager.get_embeddings(
                        [query_chunk]
                    )

                    if not chunks_with_emb or not hasattr(
                        chunks_with_emb[0], "embedding"
                    ):
                        error_msg = (
                            "Failed to get embedding for query from real service"
                        )
                        logger.error(
                            "%s: chunks_with_emb=%s, has_embedding=%s",
                            error_msg,
                            chunks_with_emb is not None,
                            (
                                hasattr(chunks_with_emb[0], "embedding")
                                if chunks_with_emb
                                else False
                            ),
                        )
                        return ErrorResult(
                            message=error_msg,
                            code="EMBEDDING_SERVICE_ERROR",
                        )

                    # Use real embedding
                    import numpy as np

                    embedding = getattr(chunks_with_emb[0], "embedding")
                    query_vec = np.array(embedding, dtype="float32")
                    norm = float(np.linalg.norm(query_vec))
                    if norm > 0:
                        query_vec = query_vec / norm
                    else:
                        error_msg = "Invalid embedding vector (zero norm)"
                        logger.error(
                            "%s: embedding vector has zero norm (dim=%d)",
                            error_msg,
                            len(query_vec),
                        )
                        return ErrorResult(
                            message=error_msg,
                            code="EMBEDDING_SERVICE_ERROR",
                        )
                finally:
                    await svo_client_manager.close()

                distances, vector_ids = faiss_manager.search(query_vec, k=int(k))

                ids: list[int] = (
                    [int(i) for i in vector_ids.tolist()]
                    if hasattr(vector_ids, "tolist")
                    else []
                )
                if not ids:
                    return SuccessResult(
                        data={
                            "query": query,
                            "results": [],
                            "count": 0,
                            "index_path": str(index_path),
                        }
                    )

                # Resolve chunk metadata by project_id (one index per project)
                placeholders = ",".join(["?"] * len(ids))
                result = database.execute(
                    f"""
                    SELECT
                        c.vector_id,
                        c.chunk_uuid,
                        c.chunk_type,
                        c.chunk_text,
                        c.line,
                        f.path AS file_path,
                        c.bm25_score,
                        c.token_count
                    FROM code_chunks c
                    JOIN files f ON f.id = c.file_id
                    WHERE c.project_id = ?
                      AND c.vector_id IN ({placeholders})
                    """,
                    [project_id, *ids],
                )
                rows = result.get("data", [])
                by_vector_id: dict[int, dict[str, Any]] = {
                    int(r["vector_id"]): dict(r) for r in rows
                }

                results: list[dict[str, Any]] = []
                for dist, vid in zip(distances.tolist(), ids):
                    score = 1.0 / (1.0 + float(dist))
                    if min_score is not None and score < float(min_score):
                        continue
                    row = by_vector_id.get(int(vid))
                    if not row:
                        continue
                    item: dict[str, Any] = {
                        "score": score,
                        "distance": float(dist),
                        "vector_id": int(vid),
                        "chunk_uuid": row.get("chunk_uuid"),
                        "chunk_type": row.get("chunk_type"),
                        "file_path": row.get("file_path"),
                        "line": row.get("line"),
                        "text": row.get("chunk_text"),
                    }
                    if row.get("bm25_score") is not None:
                        item["bm25_score"] = float(row["bm25_score"])
                    if row.get("token_count") is not None:
                        item["token_count"] = int(row["token_count"])
                    results.append(item)

                return SuccessResult(
                    data={
                        "query": query,
                        "k": int(k),
                        "min_score": min_score,
                        "index_path": str(index_path),
                        "project_id": project_id,
                        "results": results,
                        "count": len(results),
                    }
                )

            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "SEARCH_ERROR", "semantic_search")

    @classmethod
    def metadata(cls: type["SemanticSearchMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The semantic_search command performs semantic search using embeddings and FAISS vector index. "
                "It converts the query text to an embedding vector using an embedding service, "
                "then searches for similar code chunks in the FAISS index.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Loads server config to get vector_dim and embedding service config\n"
                "5. Resolves FAISS index path (one index per project: {faiss_dir}/{project_id}.bin)\n"
                "6. Loads FAISS index using FaissIndexManager\n"
                "7. Gets query embedding from embedding service (SVOClientManager)\n"
                "8. Normalizes embedding vector\n"
                "9. Searches FAISS index for k nearest neighbors\n"
                "10. Filters results by min_score (if provided)\n"
                "11. Returns similar code chunks with similarity scores\n\n"
                "Semantic Search:\n"
                "- Uses embedding vectors to find semantically similar code\n"
                "- Query is converted to embedding using embedding service\n"
                "- Searches in FAISS index for similar vectors\n"
                "- Returns chunks ranked by similarity (distance)\n"
                "- Similarity score: 1.0 / (1.0 + distance)\n\n"
                "FAISS Index:\n"
                "- One index per project: {faiss_dir}/{project_id}.bin\n"
                "- Must be built with update_indexes first\n"
                "- Uses cosine similarity (normalized vectors)\n"
                "- Supports k-nearest neighbor search\n\n"
                "Important notes:\n"
                "- Requires embedding service to be available\n"
                "- Requires FAISS index (run update_indexes first)\n"
                "- Similarity scores range from 0.0 to 1.0 (higher is better)\n"
                "- min_score filters results by similarity threshold"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db (or project registered in server DB). Embedding/config from server only."
                    ),
                    "type": "string",
                    "required": True,
                },
                "query": {
                    "description": (
                        "Search query text. Will be converted to embedding vector using embedding service. "
                        "Searches for semantically similar code chunks."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "database connection",
                        "file processing",
                        "error handling",
                        "authentication logic",
                    ],
                },
                "k": {
                    "description": (
                        "Number of results to return. Range: 1-100. Default is 10. "
                        "Returns k nearest neighbors from FAISS index."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
                "min_score": {
                    "description": (
                        "Optional minimum similarity score threshold (0.0-1.0). "
                        "Only results with score >= min_score are returned. "
                        "Score is calculated as 1.0 / (1.0 + distance)."
                    ),
                    "type": "number",
                    "required": False,
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "examples": [0.5, 0.7, 0.9],
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. If omitted, inferred from root_dir."
                    ),
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Basic semantic search",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "query": "database connection",
                        "k": 10,
                    },
                    "explanation": (
                        "Searches for code chunks semantically similar to 'database connection', "
                        "returning top 10 results."
                    ),
                },
                {
                    "description": "Search with minimum score threshold",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "query": "error handling",
                        "k": 20,
                        "min_score": 0.7,
                    },
                    "explanation": (
                        "Searches for similar code with minimum similarity score of 0.7, "
                        "returning up to 20 results."
                    ),
                },
                {
                    "description": "Find highly similar code",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "query": "file processing",
                        "k": 5,
                        "min_score": 0.9,
                    },
                    "explanation": (
                        "Finds highly similar code (score >= 0.9) related to 'file processing', "
                        "returning top 5 results."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "CONFIG_NOT_FOUND": {
                    "description": "Configuration file not found",
                    "example": "Server config.json missing",
                    "solution": "Ensure server config has embedding service configuration (code_analysis.embedding).",
                },
                "FAISS_INDEX_NOT_FOUND": {
                    "description": "FAISS index not found",
                    "example": "Index file doesn't exist for project",
                    "solution": (
                        "Run update_indexes first to build the FAISS index. "
                        "One index per project: {faiss_dir}/{project_id}.bin"
                    ),
                },
                "EMBEDDING_SERVICE_ERROR": {
                    "description": "Failed to get embedding from service",
                    "example": "Service unavailable, invalid response, or zero norm vector",
                    "solution": (
                        "Check embedding service configuration in server config. "
                        "Ensure service is available and responding correctly."
                    ),
                },
                "SEARCH_ERROR": {
                    "description": "General error during search",
                    "example": "Database error, FAISS error, or vector dimension mismatch",
                    "solution": (
                        "Check database integrity, verify FAISS index is valid, "
                        "ensure vector_dim matches index configuration."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "query": "Search query that was used",
                        "k": "Number of results requested",
                        "min_score": "Minimum score threshold (if provided)",
                        "index_path": "Path to FAISS index file ({faiss_dir}/{project_id}.bin)",
                        "project_id": "Project UUID",
                        "results": (
                            "List of similar code chunks. Each contains:\n"
                            "- score: Similarity score (0.0-1.0, higher is better)\n"
                            "- distance: Distance in vector space (lower is better)\n"
                            "- vector_id: Vector ID in FAISS index\n"
                            "- chunk_uuid: Chunk UUID\n"
                            "- chunk_type: Type of chunk\n"
                            "- file_path: Path to file containing the chunk\n"
                            "- line: Line number in file\n"
                            "- text: Text content of chunk"
                        ),
                        "count": "Number of results returned (after min_score filtering)",
                    },
                    "example": {
                        "query": "database connection",
                        "k": 10,
                        "min_score": None,
                        "index_path": "data/faiss/928bcf10-db1c-47a3-8341-f60a6d997fe7.bin",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "results": [
                            {
                                "score": 0.85,
                                "distance": 0.176,
                                "vector_id": 42,
                                "chunk_uuid": "chunk123...",
                                "chunk_type": "function",
                                "file_path": "src/db.py",
                                "line": 10,
                                "text": "def connect_to_database(...)",
                            },
                        ],
                        "count": 1,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": (
                        "Error code (e.g., PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, "
                        "FAISS_INDEX_NOT_FOUND, EMBEDDING_SERVICE_ERROR, SEARCH_ERROR)"
                    ),
                    "message": "Human-readable error message",
                    "details": "Additional error details (if available)",
                },
            },
            "best_practices": [
                "Run update_indexes first to build the FAISS index",
                "Ensure embedding service is configured and available",
                "Use min_score to filter low-quality results",
                "Adjust k based on expected result count",
                "Similarity scores help identify most relevant matches",
                "Query text should describe the concept you're searching for",
            ],
        }
