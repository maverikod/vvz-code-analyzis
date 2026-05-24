"""
MCP command: list_indexing_errors.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ...core.exceptions import ValidationError
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
                        "Maximum number of rows to return. Default 200 (1–1000). "
                        "Rows are ordered by created_at DESC (newest first)."
                    ),
                    "default": 200,
                    "minimum": 1,
                    "maximum": 1000,
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Reject ``limit`` outside schema min/max after schema validation."""
        params = super().validate_params(params)
        schema = self.get_schema()
        props = schema.get("properties") or {}
        key = "limit"
        if key not in params or params[key] is None:
            return params
        value = params[key]
        prop = props.get(key) or {}
        minimum = prop.get("minimum")
        maximum = prop.get("maximum")
        if minimum is not None and value < minimum:
            raise ValidationError(
                f"{self.name}: parameter {key!r} must be >= {minimum}, got {value!r}",
                field=key,
                details={"minimum": minimum, "maximum": maximum},
            )
        if maximum is not None and value > maximum:
            raise ValidationError(
                f"{self.name}: parameter {key!r} must be <= {maximum}, got {value!r}",
                field=key,
                details={"minimum": minimum, "maximum": maximum},
            )
        return params

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
        params: Dict[str, Any] = {
            "file_path_filter": file_path_filter,
            "project_id": project_id,
            "limit": limit,
        }
        params.update(kwargs)
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        file_path_filter = params.get("file_path_filter")
        project_id = params.get("project_id")
        limit = int(params.get("limit", 200))
        try:
            db = self._open_database_from_config(auto_analyze=False)
            try:
                sql = (
                    "SELECT id, project_id, file_path, error_type, error_message, created_at "
                    "FROM indexing_errors WHERE 1=1"
                )
                sql_params: list = []
                if project_id:
                    sql += " AND project_id = ?"
                    sql_params.append(project_id)
                if file_path_filter:
                    sql += " AND file_path LIKE ?"
                    sql_params.append(f"%{file_path_filter}%")
                sql += " ORDER BY created_at DESC LIMIT ?"
                sql_params.append(int(limit))

                r = db.execute(sql, tuple(sql_params))
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
