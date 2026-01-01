"""
MCP command wrappers for log viewer operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from .log_viewer import LogViewerCommand, ListLogFilesCommand

logger = logging.getLogger(__name__)


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
                "log_path": {
                    "type": "string",
                    "description": "Path to log file",
                },
                "worker_type": {
                    "type": "string",
                    "enum": ["file_watcher", "vectorization", "analysis"],
                    "description": "Type of worker (file_watcher, vectorization, or analysis)",
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
            "required": ["log_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        log_path: str,
        worker_type: str = "file_watcher",
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        log_levels: Optional[List[str]] = None,
        search_pattern: Optional[str] = None,
        tail: Optional[int] = None,
        limit: int = 1000,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute view worker logs command.

        Args:
            log_path: Path to log file
            worker_type: Type of worker (file_watcher or vectorization)
            from_time: Start time filter
            to_time: End time filter
            event_types: List of event types to filter
            log_levels: List of log levels to filter
            search_pattern: Text pattern to search for
            tail: Return last N lines
            limit: Maximum number of lines to return

        Returns:
            SuccessResult with log entries or ErrorResult on failure
        """
        try:
            command = LogViewerCommand(
                log_path=log_path,
                worker_type=worker_type,
                from_time=from_time,
                to_time=to_time,
                event_types=event_types,
                log_levels=log_levels,
                search_pattern=search_pattern,
                tail=tail,
                limit=limit,
            )
            result = await command.execute()
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "LOG_VIEW_ERROR", "view_worker_logs")


class ListWorkerLogsMCPCommand(BaseMCPCommand):
    """List available worker log files."""

    name = "list_worker_logs"
    version = "1.0.0"
    descr = "List available worker log files"
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
                "log_dirs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of directories to scan for log files (optional, defaults to ['logs'])",
                },
                "worker_type": {
                    "type": "string",
                    "enum": ["file_watcher", "vectorization", "analysis", "server"],
                    "description": "Filter by worker type (file_watcher, vectorization, analysis) or server logs (optional)",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        log_dirs: Optional[List[str]] = None,
        worker_type: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute list worker logs command.

        Args:
            log_dirs: List of directories to scan for log files
            worker_type: Filter by worker type

        Returns:
            SuccessResult with log files list or ErrorResult on failure
        """
        try:
            command = ListLogFilesCommand(log_dirs=log_dirs, worker_type=worker_type)
            result = await command.execute()
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "LOG_LIST_ERROR", "list_worker_logs")
