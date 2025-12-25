"""
MCP command wrapper: export_graph.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ._common import get_project_id, logger, open_database
from ..export_graph import ExportGraphCommand as InternalExportGraph


class ExportGraphMCPCommand(Command):
    """Export dependency graphs, class hierarchies, or call graphs in visualization formats."""

    name = "export_graph"
    version = "1.0.0"
    descr = "Export graphs (dependencies, hierarchy, call_graph) in DOT or JSON format"
    category = "ast"
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
                    "description": "Project root directory (contains data/code_analysis.db)",
                },
                "graph_type": {
                    "type": "string",
                    "description": "Type of graph: 'dependencies', 'hierarchy', or 'call_graph'",
                    "enum": ["dependencies", "hierarchy", "call_graph"],
                    "default": "dependencies",
                },
                "format": {
                    "type": "string",
                    "description": "Output format: 'dot' (Graphviz) or 'json'",
                    "enum": ["dot", "json"],
                    "default": "dot",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to limit scope",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional limit on number of nodes",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        graph_type: str = "dependencies",
        format: str = "dot",
        file_path: Optional[str] = None,
        limit: Optional[int] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            db = open_database(root_dir)
            root_path = Path(root_dir).resolve()
            proj_id = get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            cmd = InternalExportGraph(
                db,
                proj_id,
                graph_type=graph_type,
                format=format,
                file_path=file_path,
                limit=limit,
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "export_graph failed"),
                code="EXPORT_GRAPH_ERROR",
                details=result,
            )
        except Exception as e:
            logger.exception("export_graph failed: %s", e)
            return ErrorResult(
                message=f"export_graph failed: {e}", code="EXPORT_GRAPH_ERROR"
            )
