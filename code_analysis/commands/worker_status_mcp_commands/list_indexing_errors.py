"""
MCP command: list_indexing_errors.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from .list_indexing_errors_metadata import get_metadata


class ListIndexingErrorsMCPCommand(BaseMCPCommand):
    """List indexing errors with optional filter by file path or project."""

    name = "list_indexing_errors"
    version = "1.0.0"
    descr = "List indexing errors (failed index_file) with optional filter by file path or project_id"
    category = "monitoring"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "file_path_filter": {
                    "type": "string",
                    "description": (
                        "Optional. Only return errors whose file_path contains this string "
                        "(case-sensitive substring match via SQL LIKE '%value%'). "
                        "Use to find errors for a specific file, directory, or pattern."
                    ),
                    "examples": ["test_ftp", "vast_srv/commands", "tests/"],
                },
                "project_id": {
                    "type": "string",
                    "description": (
                        "Optional. Only return errors for this project UUID. "
                        "Use list_projects to get project_id values."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of rows to return. Default 200, capped at 1000. "
                        "Rows are ordered by created_at DESC (newest first)."
                    ),
                    "default": 200,
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        file_path_filter: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 200,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        List rows from indexing_errors table with optional filters.

        Returns:
            SuccessResult with data.list = list of {id, project_id, file_path, error_type, error_message, created_at}.
        """
        try:
            db = self._open_database_from_config(auto_analyze=False)
            try:
                sql = (
                    "SELECT id, project_id, file_path, error_type, error_message, created_at "
                    "FROM indexing_errors WHERE 1=1"
                )
                params: list = []
                if project_id:
                    sql += " AND project_id = ?"
                    params.append(project_id)
                if file_path_filter:
                    sql += " AND file_path LIKE ?"
                    params.append(f"%{file_path_filter}%")
                sql += " ORDER BY created_at DESC LIMIT ?"
                params.append(min(max(1, int(limit)), 1000))

                r = db.execute(sql, tuple(params))
                data_list = r.get("data", []) if isinstance(r, dict) else []
                if data_list and isinstance(data_list[0], (list, tuple)):
                    keys = [
                        "id",
                        "project_id",
                        "file_path",
                        "error_type",
                        "error_message",
                        "created_at",
                    ]
                    data_list = [dict(zip(keys, row)) for row in data_list]

                return SuccessResult(
                    data={
                        "total": len(data_list),
                        "list": data_list,
                    }
                )
            finally:
                db.disconnect()
        except Exception as e:
            err_msg = str(e).lower()
            if "no such table" in err_msg and "indexing_errors" in err_msg:
                return SuccessResult(
                    data={"total": 0, "list": [], "table_missing": True}
                )
            return self._handle_error(
                e, "LIST_INDEXING_ERRORS_ERROR", "list_indexing_errors"
            )

    @classmethod
    def metadata(cls: type["ListIndexingErrorsMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_metadata(cls)
