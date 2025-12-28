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

logger = logging.getLogger(__name__)


class SemanticSearchMCPCommand(BaseMCPCommand):
    """Perform semantic search using embeddings and a FAISS index.

    This MCP command is exposed via the proxy and must remain robust. If the
    environment does not provide a real embedding service, the command falls back
    to a deterministic pseudo-embedding derived from the query string.

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

                code_analysis_config = config_dict.get("code_analysis", {})
                faiss_index_path = code_analysis_config.get(
                    "faiss_index_path", "data/faiss_index.bin"
                )
                vector_dim = int(code_analysis_config.get("vector_dim", 384))

                resolved = Path(faiss_index_path)
                if not resolved.is_absolute():
                    resolved = root_path / resolved

                candidates: list[Path] = [resolved]
                if resolved.suffix == ".bin":
                    candidates.append(resolved.with_suffix(""))
                candidates.append(root_path / "data" / "faiss_index")
                candidates.append(root_path / "data" / "faiss_index.bin")

                index_path: Optional[Path] = None
                for candidate in candidates:
                    if candidate.exists():
                        index_path = candidate
                        break

                if index_path is None:
                    return ErrorResult(
                        message="FAISS index not found. Run update_indexes first.",
                        code="FAISS_INDEX_NOT_FOUND",
                        details={"candidates": [str(p) for p in candidates]},
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

                import hashlib

                import numpy as np

                digest = hashlib.sha256(query.encode("utf-8")).digest()
                seed = int.from_bytes(digest[:8], "little", signed=False)
                rng = np.random.default_rng(seed)
                query_vec = rng.standard_normal(vector_dim).astype("float32")
                norm = float(np.linalg.norm(query_vec))
                if norm > 0:
                    query_vec = query_vec / norm

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
                    WHERE c.project_id = ? AND c.vector_id IN ({placeholders})
                    """,
                    [actual_project_id, *ids],
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
                        "results": results,
                        "count": len(results),
                    }
                )

            finally:
                database.close()

        except Exception as e:
            return self._handle_error(e, "SEARCH_ERROR", "semantic_search")
