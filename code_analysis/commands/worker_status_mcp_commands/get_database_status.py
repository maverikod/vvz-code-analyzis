"""
MCP command: get_database_status.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from .get_database_status_build import build_database_status_result
from .get_database_status_metadata import get_metadata


class GetDatabaseStatusMCPCommand(BaseMCPCommand):
    """Get database state and statistics."""

    name = "get_database_status"
    version = "1.0.0"
    descr = "Get database state, statistics, and pending work"
    category = "monitoring"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute get database status command. Database path from server config.

        Returns:
            SuccessResult with database status or ErrorResult on failure
        """
        try:
            from ...core.config import get_driver_config
            from ...core.storage_paths import (
                load_raw_config,
                resolve_storage_paths,
                ensure_storage_dirs,
            )
            from ...core.vector_search_backend import effective_vector_search_backend

            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            ensure_storage_dirs(storage)
            db_path = storage.db_path

            dc = get_driver_config(config_data)
            driver_type = (dc or {}).get("type") if isinstance(dc, dict) else None
            if not isinstance(driver_type, str):
                driver_type = "postgres"

            code_analysis_config = config_data.get("code_analysis", config_data)
            vector_ann_backend = effective_vector_search_backend(
                str(driver_type),
                code_analysis_config.get("vector_search_backend"),
            )

            db = self._open_database_from_config(auto_analyze=False)
            try:
                result = build_database_status_result(
                    db,
                    db_path,
                    driver_type=driver_type,
                    vector_ann_backend=vector_ann_backend,
                )
                return SuccessResult(data=result)
            finally:
                db.disconnect()
        except Exception as e:
            return self._handle_error(e, "DATABASE_STATUS_ERROR", "get_database_status")

    @classmethod
    def metadata(cls: type["GetDatabaseStatusMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_metadata(cls)
