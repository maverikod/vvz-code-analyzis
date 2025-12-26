"""
MCP command wrapper: get_imports.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..get_imports import GetImportsCommand as InternalGetImports


class GetImportsMCPCommand(BaseMCPCommand):
    """Get imports information from files or project."""

    name = "get_imports"
    version = "1.0.0"
    descr = "Get list of imports in a file or project with filtering options"
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
                    "description": "Optional file path to filter by (absolute or relative)",
                },
                "import_type": {
                    "type": "string",
                    "description": "Type of import: 'import' or 'import_from'",
                    "enum": ["import", "import_from"],
                },
                "module_name": {
                    "type": "string",
                    "description": "Optional module name to filter by",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional limit on number of results",
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination",
                    "default": 0,
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
        file_path: Optional[str] = None,
        import_type: Optional[str] = None,
        module_name: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
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

            cmd = InternalGetImports(
                db,
                proj_id,
                file_path=file_path,
                import_type=import_type,
                module_name=module_name,
                limit=limit,
                offset=offset,
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "get_imports failed"),
                code="GET_IMPORTS_ERROR",
                details=result,
            )
        except Exception as e:
            return self._handle_error(e, "GET_IMPORTS_ERROR", "get_imports")
