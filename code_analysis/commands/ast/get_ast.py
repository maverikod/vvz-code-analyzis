"""
MCP command wrapper: get_ast.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ._common import get_project_id, logger, open_database
from ..get_ast import GetASTCommand as InternalGetAST


class GetASTMCPCommand(Command):
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
            db = open_database(root_dir)
            root_path = Path(root_dir).resolve()
            proj_id = get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            cmd = InternalGetAST(db, proj_id, file_path, include_json=include_json)
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "AST retrieval failed"),
                code="GET_AST_ERROR",
                details=result,
            )
        except Exception as e:
            logger.exception("get_ast failed: %s", e)
            return ErrorResult(message=f"get_ast failed: {e}", code="GET_AST_ERROR")
