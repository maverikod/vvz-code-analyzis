"""
MCP command wrapper: ast_statistics.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class ASTStatisticsMCPCommand(BaseMCPCommand):
    """Get AST statistics for project or a specific file."""

    name = "ast_statistics"
    version = "1.0.0"
    descr = "Collect AST statistics for project or single file"
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
                    "description": "Optional file path to compute stats for (absolute or relative)",
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

            # Get AST statistics from database
            if file_path:
                file_record = db.get_file_by_path(file_path, proj_id)
                if not file_record:
                    db.close()
                    return ErrorResult(
                        message=f"File not found: {file_path}",
                        code="FILE_NOT_FOUND",
                    )
                row = db._fetchone(
                    "SELECT COUNT(*) as count FROM ast_trees WHERE file_id = ?",
                    (file_record["id"],),
                )
                ast_count = row["count"] if row else 0
                db.close()
                return SuccessResult(
                    data={
                        "success": True,
                        "file_path": file_path,
                        "ast_trees_count": ast_count,
                    }
                )
            else:
                # Project-wide stats
                row = db._fetchone(
                    "SELECT COUNT(*) as count FROM ast_trees WHERE project_id = ?",
                    (proj_id,),
                )
                ast_count = row["count"] if row else 0
                row = db._fetchone(
                    "SELECT COUNT(*) as count FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
                    (proj_id,),
                )
                file_count = row["count"] if row else 0
                db.close()
                return SuccessResult(
                    data={
                        "success": True,
                        "project_id": proj_id,
                        "files_count": file_count,
                        "ast_trees_count": ast_count,
                    }
                )
        except Exception as e:
            return self._handle_error(e, "AST_STATS_ERROR", "ast_statistics")
