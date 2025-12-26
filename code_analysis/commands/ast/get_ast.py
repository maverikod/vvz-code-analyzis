"""
MCP command wrapper: get_ast.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class GetASTMCPCommand(BaseMCPCommand):
    """Retrieve stored AST for a given file."""

    name = "get_ast"
    version = "1.0.0"
    descr = "Get AST for a Python file from the analysis database"
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
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file (absolute or relative to project root)",
                },
                "include_json": {
                    "type": "boolean",
                    "description": "Include full AST JSON in response",
                    "default": True,
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        include_json: bool = True,
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

            # Get file_id first
            file_record = db.get_file_by_path(file_path, proj_id)
            if not file_record:
                db.close()
                return ErrorResult(
                    message=f"File not found: {file_path}",
                    code="FILE_NOT_FOUND",
                )

            # Get AST from database
            ast_data = await db.get_ast_tree(file_record["id"])
            db.close()

            if ast_data:
                result = {
                    "success": True,
                    "file_path": file_path,
                    "file_id": file_record["id"],
                }
                if include_json and ast_data.get("ast_json"):
                    import json
                    result["ast"] = json.loads(ast_data["ast_json"])
                return SuccessResult(data=result)
            return ErrorResult(
                message="AST not found for file",
                code="AST_NOT_FOUND",
            )
        except Exception as e:
            return self._handle_error(e, "GET_AST_ERROR", "get_ast")
