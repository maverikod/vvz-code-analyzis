"""
MCP command wrapper for semantic search.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult
from mcp_proxy_adapter.config import get_config as get_adapter_config

from ..core.database import CodeDatabase
from ..core.config import ServerConfig
from ..core.faiss_manager import FaissIndexManager
from ..core.svo_client_manager import SVOClientManager
from .semantic_search import SemanticSearchCommand

logger = logging.getLogger(__name__)


def _load_server_config() -> ServerConfig:
    adapter_config = get_adapter_config()
    adapter_config_data = getattr(adapter_config, "config_data", {}) if adapter_config else {}
    code_analysis_config = adapter_config_data.get("code_analysis", {})
    return ServerConfig(**code_analysis_config) if code_analysis_config else ServerConfig()


class SemanticSearchMCPCommand(Command):
    """Run semantic search with optional filters."""

    name = "semantic_search"
    version = "1.0.0"
    descr = "Semantic search over code/docstrings using embeddings and FAISS"
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root (contains data/code_analysis.db)",
                },
                "query": {
                    "type": "string",
                    "description": "Query text for semantic search",
                },
                "k": {
                    "type": "integer",
                    "description": "Number of results",
                    "default": 10,
                },
                "max_distance": {
                    "type": "number",
                    "description": "Optional distance threshold",
                },
                "include_ast_node": {
                    "type": "boolean",
                    "description": "Include full AST node JSON in results",
                    "default": False,
                },
                "source_type": {
                    "type": "string",
                    "description": "Filter by source_type (e.g., docstring, file_docstring, comment)",
                },
                "bm25_min": {
                    "type": "number",
                    "description": "Minimum bm25 score to include result",
                },
                "file_path_substring": {
                    "type": "string",
                    "description": "Substring to filter file paths",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; inferred from root_dir if omitted",
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
        max_distance: Optional[float] = None,
        include_ast_node: bool = False,
        source_type: Optional[str] = None,
        bm25_min: Optional[float] = None,
        file_path_substring: Optional[str] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = Path(root_dir).resolve()
            data_dir = root_path / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "code_analysis.db"
            database = CodeDatabase(db_path)

            proj_id = project_id or database.get_or_create_project(
                str(root_path), name=root_path.name
            )
            if not proj_id:
                return ErrorResult(message="Project not found", code="PROJECT_NOT_FOUND")

            server_config = _load_server_config()
            if not server_config.vector_dim:
                return ErrorResult(message="vector_dim not configured", code="INVALID_CONFIG")

            svo_client_manager = SVOClientManager(server_config)
            await svo_client_manager.initialize()

            faiss_path = (
                Path(server_config.faiss_index_path)
                if server_config.faiss_index_path
                else root_path / "data" / "faiss_index"
            )
            faiss_manager = FaissIndexManager(str(faiss_path), server_config.vector_dim)

            search_cmd = SemanticSearchCommand(
                database=database,
                project_id=proj_id,
                faiss_manager=faiss_manager,
                svo_client_manager=svo_client_manager,
            )

            results = await search_cmd.search(
                query=query,
                k=k,
                max_distance=max_distance,
                include_ast_node=include_ast_node,
                source_type=source_type,
                bm25_min=bm25_min,
                file_path_substring=file_path_substring,
            )

            await svo_client_manager.close()
            database.close()

            return SuccessResult(data={"results": results, "count": len(results)})
        except Exception as e:
            logger.exception("Semantic search failed: %s", e)
            return ErrorResult(message=f"Semantic search failed: {e}", code="SEMANTIC_SEARCH_ERROR")

