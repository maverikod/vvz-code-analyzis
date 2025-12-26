"""
MCP command wrapper: search_ast_nodes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class SearchASTNodesMCPCommand(BaseMCPCommand):
    """Search AST nodes across project/files."""

    name = "search_ast_nodes"
    version = "1.0.0"
    descr = "Search AST nodes (by type) in project files"
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
                "node_type": {
                    "type": "string",
                    "description": "AST node type to search (e.g., ClassDef, FunctionDef)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to limit search (absolute or relative)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 100,
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
        node_type: Optional[str] = None,
        file_path: Optional[str] = None,
        limit: int = 100,
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

            # Search AST nodes - for now return placeholder
            # This requires parsing AST JSON which is complex
            # TODO: Implement AST node search by parsing ast_json from ast_trees table
            db.close()
            return ErrorResult(
                message="AST node search not yet implemented - requires AST JSON parsing",
                code="NOT_IMPLEMENTED",
            )
        except Exception as e:
            return self._handle_error(e, "SEARCH_AST_ERROR", "search_ast_nodes")
