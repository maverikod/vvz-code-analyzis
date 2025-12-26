"""
MCP command wrapper: export_graph.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class ExportGraphMCPCommand(BaseMCPCommand):
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
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            # Export graph - requires complex graph building logic
            # For now, return placeholder
            db.close()
            return ErrorResult(
                message="Graph export requires graph building logic from dependencies/hierarchy data",
                code="NOT_IMPLEMENTED",
            )
        except Exception as e:
            return self._handle_error(e, "EXPORT_GRAPH_ERROR", "export_graph")
