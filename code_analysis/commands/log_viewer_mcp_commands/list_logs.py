"""
List logs by identifier (log_id) MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..log_viewer import ListLogsByIdCommand

from ...core.list_pagination import (
    apply_list_pagination_defaults,
    apply_pagination_fields,
    list_pagination_schema_properties,
)
from ...core.storage_paths import load_raw_config


class ListLogsMCPCommand(BaseMCPCommand):
    """List available logs by identifier (log_id). Path-independent; use log_id in view_worker_logs."""

    name = "list_logs"
    version = "1.1.0"
    descr = (
        "List available logs by identifier (log_id); path-independent. "
        "Returns paginated ``items`` / ``logs`` (default ``page_size`` 20)."
    )
    category = "logging"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "include_paths": {
                    "type": "boolean",
                    "description": "If true, include current path for each log (optional)",
                    "default": False,
                },
                **list_pagination_schema_properties(),
            },
            "required": [],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize pagination params after schema validation."""
        params = super().validate_params(params)
        apply_list_pagination_defaults(params)
        return params

    async def execute(
        self,
        include_paths: bool = False,
        page_size: Optional[int] = None,
        block_position: Optional[int] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute list logs by id command."""
        try:
            params = self.validate_params(
                {
                    "include_paths": include_paths,
                    "page_size": page_size,
                    "block_position": block_position,
                    "limit": limit,
                    "offset": offset,
                    **kwargs,
                }
            )
            include_paths = bool(params.get("include_paths", False))
            page_size_val = int(params["page_size"])
            offset_val = int(params["offset"])
            block_position_val = int(params["block_position"])
            config_path = BaseMCPCommand._resolve_config_path()
            config_data = load_raw_config(config_path)
            config_dir = Path(config_path).resolve().parent
            command = ListLogsByIdCommand(
                config_data=config_data,
                config_dir=config_dir,
                include_paths=include_paths,
            )
            result = await command.execute()
            if isinstance(result, dict):
                all_logs = list(result.get("logs") or [])
                apply_pagination_fields(
                    result,
                    all_items=all_logs,
                    legacy_items_key="logs",
                    page_size=page_size_val,
                    block_position=block_position_val,
                    offset=offset_val,
                )
                result["message"] = (
                    f"Found {result['total']} log(s); "
                    f"returning page {block_position_val} ({result['count']} rows)"
                )
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "LOG_LIST_ERROR", "list_logs")

    @classmethod
    def metadata(cls: type["ListLogsMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The list_logs command returns available logs by identifier (log_id), not by path. "
                "Use these log_id values with view_worker_logs (log_id parameter). "
                "Identifiers are stable and do not change when logs are rotated. "
                "Reading in view_worker_logs includes rotated files (.1, .2, .gz).\n\n"
                "There is no filename glob here — to scan log **files** on disk with optional "
                "``file_pattern`` / ``glob``, use ``list_worker_logs``.\n\n"
                "Log identifiers: mcp_server, code_analysis, vectorization, file_watcher, indexing_worker."
            ),
            "parameters": {
                "include_paths": {
                    "description": "If true, include current path for each log.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
        }
