"""
List logs by identifier (log_id) MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..log_viewer import ListLogsByIdCommand

from ...core.storage_paths import load_raw_config


class ListLogsMCPCommand(BaseMCPCommand):
    """List available logs by identifier (log_id). Path-independent; use log_id in view_worker_logs."""

    name = "list_logs"
    version = "1.0.0"
    descr = "List available logs by identifier (log_id); path-independent"
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
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        include_paths: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute list logs by id command."""
        try:
            config_path = BaseMCPCommand._resolve_config_path()
            config_data = load_raw_config(config_path)
            config_dir = Path(config_path).resolve().parent
            command = ListLogsByIdCommand(
                config_data=config_data,
                config_dir=config_dir,
                include_paths=include_paths,
            )
            result = await command.execute()
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
