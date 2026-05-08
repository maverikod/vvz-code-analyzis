"""
View worker logs MCP command (filter by time, event type, search).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..log_viewer import LogViewerCommand

from ._shared import WORKER_LOG_FILENAMES
from .view_worker_logs_metadata import get_view_worker_logs_metadata

logger = logging.getLogger(__name__)

_LOG_ID_ENUM = frozenset(
    {
        "mcp_server",
        "code_analysis",
        "vectorization",
        "file_watcher",
        "indexing_worker",
    }
)


class ViewWorkerLogsMCPCommand(BaseMCPCommand):
    """View worker logs with filtering by time and event type."""

    name = "view_worker_logs"
    version = "1.0.0"
    descr = "View worker logs with filtering by time, event type, and search pattern"
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
                "log_id": {
                    "type": "string",
                    "enum": [
                        "mcp_server",
                        "code_analysis",
                        "vectorization",
                        "file_watcher",
                        "indexing_worker",
                    ],
                    "description": (
                        "Log identifier (preferred over path). Resolves path from config; "
                        "reading includes rotated files (.1, .2, .gz)."
                    ),
                },
                "log_path": {
                    "type": "string",
                    "description": "Path to log file (optional if log_id or worker_type set)",
                },
                "worker_type": {
                    "type": "string",
                    "enum": [
                        "file_watcher",
                        "vectorization",
                        "indexing",
                        "database_driver",
                        "analysis",
                    ],
                    "description": "Type of worker (file_watcher, vectorization, indexing, database_driver, or analysis)",
                    "default": "file_watcher",
                },
                "from_time": {
                    "type": "string",
                    "description": "Start time filter (ISO format or 'YYYY-MM-DD HH:MM:SS')",
                },
                "to_time": {
                    "type": "string",
                    "description": "End time filter (ISO format or 'YYYY-MM-DD HH:MM:SS')",
                },
                "event_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of event types to filter (e.g., ['new_file', 'changed_file', 'deleted_file', 'cycle', 'error'])",
                },
                "log_levels": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    },
                    "description": "List of log levels to filter (e.g., ['INFO', 'ERROR'])",
                },
                "search_pattern": {
                    "type": "string",
                    "description": "Text pattern to search for (regex supported)",
                },
                "importance_min": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "description": "Minimum importance 0-10 (inclusive)",
                },
                "importance_max": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "description": "Maximum importance 0-10 (inclusive)",
                },
                "tail": {
                    "type": "integer",
                    "description": "Return last N lines (if specified, ignores time filters)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to return",
                    "default": 1000,
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Accept log_id with optional ``.log`` suffix (e.g. ``mcp_server.log``)."""
        normalized = dict(params)
        lid = normalized.get("log_id")
        if isinstance(lid, str):
            s = lid.strip()
            if s.endswith(".log"):
                base = s[:-4].strip()
                if base in _LOG_ID_ENUM:
                    normalized["log_id"] = base
        return super().validate_params(normalized)

    async def execute(
        self,
        log_id: Optional[str] = None,
        log_path: Optional[str] = None,
        worker_type: str = "file_watcher",
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        log_levels: Optional[List[str]] = None,
        search_pattern: Optional[str] = None,
        importance_min: Optional[int] = None,
        importance_max: Optional[int] = None,
        tail: Optional[int] = None,
        limit: int = 1000,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute view worker logs command."""
        try:
            resolved_path = log_path
            resolved_worker_type = worker_type
            if log_id:
                resolved_path = self._resolve_log_path_by_id(log_id)
                resolved_worker_type = self._log_id_to_worker_type(log_id)
            if not resolved_path and not log_id:
                resolved_path = self._resolve_worker_log_path(worker_type)
            if not resolved_path:
                return ErrorResult(
                    code="MISSING_LOG_PATH",
                    message="Provide log_id, log_path, or worker_type and server config to resolve log path",
                )
            command = LogViewerCommand(
                log_path=resolved_path,
                worker_type=resolved_worker_type,
                from_time=from_time,
                to_time=to_time,
                event_types=event_types,
                log_levels=log_levels,
                search_pattern=search_pattern,
                importance_min=importance_min,
                importance_max=importance_max,
                tail=tail,
                limit=limit,
            )
            result = await command.execute()
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "LOG_VIEW_ERROR", "view_worker_logs")

    def _resolve_worker_log_path(self, worker_type: str) -> Optional[str]:
        """Resolve default log path for worker_type from server config."""
        try:
            storage = BaseMCPCommand._get_shared_storage()
            log_name = WORKER_LOG_FILENAMES.get(worker_type)
            if not log_name:
                return None
            path = storage.config_dir / "logs" / log_name
            return str(path)
        except Exception as e:
            logger.debug("Could not resolve worker log path from config: %s", e)
            return None

    def _resolve_log_path_by_id(self, log_id: str) -> Optional[str]:
        """Resolve log path from config by log identifier."""
        try:
            from pathlib import Path

            from ...core.log_rotation_all import collect_log_paths
            from ...core.storage_paths import load_raw_config

            config_path = BaseMCPCommand._resolve_config_path()
            config_data = load_raw_config(config_path)
            config_dir = Path(config_path).resolve().parent
            for path, label in collect_log_paths(
                config_data, config_dir, log_filter=None
            ):
                if label == log_id:
                    return str(path)
            return None
        except Exception as e:
            logger.debug("Could not resolve log path by id %s: %s", log_id, e)
            return None

    def _log_id_to_worker_type(self, log_id: str) -> str:
        """Map log_id to worker_type for event patterns."""
        m = {
            "mcp_server": "server",
            "code_analysis": "server",
            "vectorization": "vectorization",
            "file_watcher": "file_watcher",
            "indexing_worker": "indexing",
        }
        return m.get(log_id, "server")

    @classmethod
    def metadata(cls: type["ViewWorkerLogsMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_view_worker_logs_metadata(cls)
