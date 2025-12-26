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
    """Perform semantic search using embeddings and FAISS vectors."""

    name = "semantic_search"
    version = "1.0.0"
    descr = "Perform semantic search using embeddings and FAISS vectors"
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
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
        self,
        root_dir: str,
        query: str,
        k: int = 10,
        min_score: Optional[float] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute semantic search.

        Args:
            root_dir: Root directory of the project
            query: Search query text
            k: Number of results to return
            min_score: Optional minimum similarity score
            project_id: Optional project UUID

        Returns:
            SuccessResult with search results or ErrorResult on failure
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

                # Get config for FAISS and SVO
                from ..core.config import ServerConfig

                config_path = root_path / "config.json"
                if not config_path.exists():
                    return ErrorResult(
                        message="Configuration file not found",
                        code="CONFIG_NOT_FOUND",
                    )

                # Load config
                import json

                with open(config_path, "r") as f:
                    config_dict = json.load(f)

                code_analysis_config = config_dict.get("code_analysis", {})
                faiss_index_path = code_analysis_config.get(
                    "faiss_index_path", "data/faiss_index.bin"
                )
                vector_dim = code_analysis_config.get("vector_dim", 384)

                # Resolve relative paths
                if not Path(faiss_index_path).is_absolute():
                    faiss_index_path = str(root_path / faiss_index_path)

                # Create server config for SVO client manager
                server_config = ServerConfig(**code_analysis_config)

                # Initialize SVO client manager
                from ..core.svo_client_manager import SVOClientManager

                svo_client_manager = SVOClientManager(server_config)
                await svo_client_manager.initialize()

                try:
                    # Create search command
                    search_cmd = SemanticSearchCommand(
                        database=database,
                        project_id=actual_project_id,
                        faiss_index_path=faiss_index_path,
                        vector_dim=vector_dim,
                        svo_client_manager=svo_client_manager,
                    )

                    # Perform search
                    results = await search_cmd.search(query, k=k, min_score=min_score)

                    return SuccessResult(
                        data={
                            "query": query,
                            "results": results,
                            "count": len(results),
                        }
                    )
                finally:
                    await svo_client_manager.close()

            finally:
                database.close()

        except Exception as e:
            return self._handle_error(e, "SEARCH_ERROR", "semantic_search")

