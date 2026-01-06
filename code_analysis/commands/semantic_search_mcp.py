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
from ..core.project_resolution import normalize_root_dir

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
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
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
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "query"],
            "additionalProperties": False,
        }

    async def execute(
        self: "SemanticSearchMCPCommand",
        root_dir: str,
        query: str,
        k: int = 10,
        min_score: Optional[float] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """Execute semantic search.

        Args:
            self: Command instance.
            root_dir: Root directory of the project.
            query: Search query text.
            k: Number of results to return.
            min_score: Optional minimum similarity score threshold.
            project_id: Optional project UUID.

        Returns:
            SuccessResult with search results or ErrorResult on failure.
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            database = self._open_database(root_dir)
            try:
                actual_project_id = self._get_project_id(
                    database, root_path, project_id
                )
                if not actual_project_id:
                    return ErrorResult(
                        message=(
                            f"Project not found: {project_id}"
                            if project_id
                            else "Failed to get or create project"
                        ),
                        code="PROJECT_NOT_FOUND",
                    )

                config_path = root_path / "config.json"
                if not config_path.exists():
                    return ErrorResult(
                        message=f"Configuration file not found: {config_path}",
                        code="CONFIG_NOT_FOUND",
                    )

                import json

                with open(config_path, "r", encoding="utf-8") as f:
                    config_dict = json.load(f)

                # Extract code_analysis config (may be nested)
                code_analysis_config = config_dict.get("code_analysis", config_dict)
                vector_dim = int(code_analysis_config.get("vector_dim", 384))

                # Resolve storage paths (Step 2: dataset-scoped FAISS)
                storage_paths = resolve_storage_paths(
                    config_data=config_dict, config_path=config_path
                )

                # Get dataset_id for root_dir (normalized absolute path)
                normalized_root = str(normalize_root_dir(root_dir))
                dataset_id = database.get_dataset_id(actual_project_id, normalized_root)
                if not dataset_id:
                    # Create dataset if it doesn't exist
                    dataset_id = database.get_or_create_dataset(
                        actual_project_id, normalized_root
                    )

                # Get dataset-scoped FAISS index path (Step 2)
                index_path = get_faiss_index_path(
                    storage_paths.faiss_dir, actual_project_id, dataset_id
                )

                if not index_path.exists():
                    return ErrorResult(
                        message="FAISS index not found. Run update_indexes first.",
                        code="FAISS_INDEX_NOT_FOUND",
                        details={
                            "index_path": str(index_path),
                            "project_id": actual_project_id,
                            "dataset_id": dataset_id,
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

                # Create SVOClientManager from config
                # Pass the full config_dict and root_dir - SVOClientManager will extract code_analysis.embedding
                svo_client_manager = SVOClientManager(config_dict, root_dir=root_path)
                await svo_client_manager.initialize()

                try:
                    # Create dummy chunk object for embedding
                    class QueryChunk:
                        def __init__(self, text: str):
                            self.body = text
                            self.text = text

                    query_chunk = QueryChunk(query)
                    chunks_with_emb = await svo_client_manager.get_embeddings([query_chunk])

                    if not chunks_with_emb or not hasattr(chunks_with_emb[0], "embedding"):
                        error_msg = "Failed to get embedding for query from real service"
                        logger.error(
                            "%s: chunks_with_emb=%s, has_embedding=%s",
                            error_msg,
                            chunks_with_emb is not None,
                            hasattr(chunks_with_emb[0], "embedding") if chunks_with_emb else False,
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

                # Filter results by dataset_id to ensure dataset-scoped search
                placeholders = ",".join(["?"] * len(ids))
                rows = database._fetchall(
                    f"""
                    SELECT
                        c.vector_id,
                        c.chunk_uuid,
                        c.chunk_type,
                        c.chunk_text,
                        c.line,
                        f.path AS file_path
                    FROM code_chunks c
                    JOIN files f ON f.id = c.file_id
                    WHERE c.project_id = ? 
                      AND f.dataset_id = ?
                      AND c.vector_id IN ({placeholders})
                    """,
                    [actual_project_id, dataset_id, *ids],
                )
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
                    results.append(
                        {
                            "score": score,
                            "distance": float(dist),
                            "vector_id": int(vid),
                            "chunk_uuid": row.get("chunk_uuid"),
                            "chunk_type": row.get("chunk_type"),
                            "file_path": row.get("file_path"),
                            "line": row.get("line"),
                            "text": row.get("chunk_text"),
                        }
                    )

                return SuccessResult(
                    data={
                        "query": query,
                        "k": int(k),
                        "min_score": min_score,
                        "index_path": str(index_path),
                        "project_id": actual_project_id,
                        "dataset_id": dataset_id,
                        "results": results,
                        "count": len(results),
                    }
                )

            finally:
                database.close()

        except Exception as e:
            return self._handle_error(e, "SEARCH_ERROR", "semantic_search")
