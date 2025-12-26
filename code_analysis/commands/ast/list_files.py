"""
MCP command wrapper: list_project_files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class ListProjectFilesMCPCommand(BaseMCPCommand):
    """List all files in a project with metadata."""

    name = "list_project_files"
    version = "1.0.0"
    descr = (
        "List all files in a project with statistics (classes, functions, chunks, AST)"
    )
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
                "file_pattern": {
                    "type": "string",
                    "description": "Optional pattern to filter files (e.g., '*.py', 'core/*')",
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
        file_pattern: Optional[str] = None,
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

            # Get files from database
            files = db.get_project_files(proj_id, include_deleted=False)
            
            # Apply file_pattern filter if provided
            if file_pattern:
                import fnmatch
                files = [f for f in files if fnmatch.fnmatch(f["path"], file_pattern)]
            
            # Apply pagination
            total = len(files)
            if offset > 0 or limit:
                files = files[offset : offset + limit if limit else None]
            
            db.close()
            
            return SuccessResult(
                data={
                    "success": True,
                    "files": files,
                    "count": len(files),
                    "total": total,
                    "offset": offset,
                }
            )
        except Exception as e:
            return self._handle_error(e, "LIST_FILES_ERROR", "list_project_files")
