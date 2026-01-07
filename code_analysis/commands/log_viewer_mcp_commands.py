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

    @classmethod
    def metadata(cls: type["ViewWorkerLogsMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The view_worker_logs command views worker logs with advanced filtering capabilities. "
                "It supports filtering by time range, event types, log levels, and text search patterns. "
                "The command parses log files and returns structured log entries.\n\n"
                "Operation flow:\n"
                "1. Validates log_path exists and is readable\n"
                "2. Parses time filters (from_time, to_time) if provided\n"
                "3. Selects event patterns based on worker_type\n"
                "4. Reads log file line by line\n"
                "5. Parses each log line to extract timestamp, level, and message\n"
                "6. Applies filters:\n"
                "   - Time range filter (from_time to to_time)\n"
                "   - Event type filter (matches event patterns)\n"
                "   - Log level filter (INFO, ERROR, WARNING, etc.)\n"
                "   - Search pattern filter (regex matching)\n"
                "7. If tail specified, returns last N lines (ignores time filters)\n"
                "8. Limits results to specified limit\n"
                "9. Returns structured log entries\n\n"
                "Worker Types:\n"
                "- file_watcher: File watcher worker logs with events like new_file, changed_file, deleted_file\n"
                "- vectorization: Vectorization worker logs with events like processed, cycle, circuit_breaker\n"
                "- analysis: Analysis worker logs\n\n"
                "Event Types (file_watcher):\n"
                "- new_file: New file detected\n"
                "- changed_file: File changed\n"
                "- deleted_file: File deleted\n"
                "- cycle: Scan cycle\n"
                "- scan_start: Scan started\n"
                "- scan_end: Scan ended\n"
                "- queue: Queue operations\n"
                "- error: Error events\n"
                "- info: Info events\n"
                "- warning: Warning events\n\n"
                "Event Types (vectorization):\n"
                "- cycle: Processing cycle\n"
                "- processed: File processed/vectorized\n"
                "- error: Error events\n"
                "- info: Info events\n"
                "- warning: Warning events\n"
                "- circuit_breaker: Circuit breaker events\n\n"
                "Use cases:\n"
                "- Debug worker issues by viewing recent logs\n"
                "- Filter logs by time range to find specific events\n"
                "- Search for specific error patterns\n"
                "- Monitor worker activity\n"
                "- Analyze worker performance\n\n"
                "Important notes:\n"
                "- Time format: ISO format ('2025-01-26T10:30:00') or 'YYYY-MM-DD HH:MM:SS'\n"
                "- If tail is specified, time filters are ignored\n"
                "- Search pattern supports regex (case-insensitive)\n"
                "- Default limit is 1000 lines to prevent large responses\n"
                "- Log lines are parsed to extract timestamp, level, and message"
            ),
            "parameters": {
                "log_path": {
                    "description": (
                        "Path to log file. Can be absolute or relative. "
                        "File must exist and be readable."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "logs/file_watcher.log",
                        "/home/user/projects/my_project/logs/vectorization.log",
                    ],
                },
                "worker_type": {
                    "description": (
                        "Type of worker. Options: 'file_watcher', 'vectorization', 'analysis'. "
                        "Default is 'file_watcher'. Determines which event patterns are used."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": ["file_watcher", "vectorization", "analysis"],
                    "default": "file_watcher",
                },
                "from_time": {
                    "description": (
                        "Start time filter. ISO format ('2025-01-26T10:30:00') or "
                        "'YYYY-MM-DD HH:MM:SS'. Only logs after this time are returned."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "2025-01-26T10:30:00",
                        "2025-01-26 10:30:00",
                        "2025-01-26",
                    ],
                },
                "to_time": {
                    "description": (
                        "End time filter. ISO format ('2025-01-26T10:30:00') or "
                        "'YYYY-MM-DD HH:MM:SS'. Only logs before this time are returned."
                    ),
                    "type": "string",
                    "required": False,
                },
                "event_types": {
                    "description": (
                        "List of event types to filter. For file_watcher: new_file, changed_file, "
                        "deleted_file, cycle, scan_start, scan_end, queue, error, info, warning. "
                        "For vectorization: cycle, processed, error, info, warning, circuit_breaker."
                    ),
                    "type": "array",
                    "required": False,
                    "items": {"type": "string"},
                    "examples": [
                        ["new_file", "changed_file"],
                        ["error"],
                        ["cycle", "processed"],
                    ],
                },
                "log_levels": {
                    "description": (
                        "List of log levels to filter. Options: DEBUG, INFO, WARNING, ERROR, CRITICAL."
                    ),
                    "type": "array",
                    "required": False,
                    "items": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
                    "examples": [["ERROR", "WARNING"], ["INFO"]],
                },
                "search_pattern": {
                    "description": (
                        "Text pattern to search for. Supports regex (case-insensitive). "
                        "Only log lines matching the pattern are returned."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["error", "failed", "circuit.*breaker"],
                },
                "tail": {
                    "description": (
                        "Return last N lines. If specified, time filters are ignored. "
                        "Useful for viewing recent logs."
                    ),
                    "type": "integer",
                    "required": False,
                },
                "limit": {
                    "description": (
                        "Maximum number of lines to return. Default is 1000. "
                        "Prevents large responses for big log files."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 1000,
                },
            },
            "usage_examples": [
                {
                    "description": "View last 100 lines of log",
                    "command": {
                        "log_path": "logs/file_watcher.log",
                        "tail": 100,
                    },
                    "explanation": (
                        "Returns last 100 lines from file_watcher.log, ignoring time filters."
                    ),
                },
                {
                    "description": "View logs for specific time range",
                    "command": {
                        "log_path": "logs/file_watcher.log",
                        "from_time": "2025-01-26 10:00:00",
                        "to_time": "2025-01-26 11:00:00",
                    },
                    "explanation": (
                        "Returns logs between 10:00 and 11:00 on January 26, 2025."
                    ),
                },
                {
                    "description": "Filter by event types",
                    "command": {
                        "log_path": "logs/file_watcher.log",
                        "event_types": ["new_file", "changed_file", "deleted_file"],
                    },
                    "explanation": (
                        "Returns only logs for new_file, changed_file, and deleted_file events."
                    ),
                },
                {
                    "description": "Search for errors",
                    "command": {
                        "log_path": "logs/vectorization.log",
                        "worker_type": "vectorization",
                        "log_levels": ["ERROR"],
                        "search_pattern": "failed",
                    },
                    "explanation": (
                        "Returns ERROR level logs containing 'failed' in vectorization.log."
                    ),
                },
            ],
            "error_cases": {
                "LOG_VIEW_ERROR": {
                    "description": "General error during log viewing",
                    "example": "File not found, permission denied, or parsing error",
                    "solution": (
                        "Verify log_path exists and is readable. Check file permissions. "
                        "Ensure log file format is correct."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "entries": (
                            "List of log entries. Each entry contains:\n"
                            "- timestamp: Log timestamp (datetime)\n"
                            "- level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)\n"
                            "- message: Log message\n"
                            "- event_type: Detected event type (if matched)\n"
                            "- line_number: Line number in log file"
                        ),
                        "total_lines": "Total number of lines read from log file",
                        "filtered_lines": "Number of lines after filtering",
                        "limit": "Limit applied",
                    },
                    "example": {
                        "entries": [
                            {
                                "timestamp": "2025-01-26T10:30:00",
                                "level": "INFO",
                                "message": "[NEW FILE] src/main.py",
                                "event_type": "new_file",
                                "line_number": 42,
                            },
                        ],
                        "total_lines": 1000,
                        "filtered_lines": 1,
                        "limit": 1000,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., LOG_VIEW_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use tail parameter to view recent logs quickly",
                "Use time filters to narrow down to specific time periods",
                "Combine event_types and log_levels for precise filtering",
                "Use search_pattern for text-based searches",
                "Set appropriate limit to prevent large responses",
                "Use list_worker_logs first to find available log files",
            ],
        }


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

    @classmethod
    def metadata(cls: type["ListWorkerLogsMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The list_worker_logs command lists available worker log files in specified directories. "
                "It scans configured log directories and returns available log files for workers "
                "(file_watcher, vectorization, analysis) and server logs.\n\n"
                "Operation flow:\n"
                "1. If log_dirs provided, uses those directories\n"
                "2. If log_dirs not provided, defaults to ['logs'] directory\n"
                "3. Scans directories for log files\n"
                "4. If worker_type specified, filters by worker type:\n"
                "   - file_watcher: Finds file_watcher*.log files\n"
                "   - vectorization: Finds vectorization*.log files\n"
                "   - analysis: Finds analysis*.log files\n"
                "   - server: Finds server*.log, mcp*.log files\n"
                "5. If worker_type not specified, returns all log files\n"
                "6. Returns list of log files with metadata (path, size, modified time)\n\n"
                "Worker Types:\n"
                "- file_watcher: File watcher worker logs\n"
                "- vectorization: Vectorization worker logs\n"
                "- analysis: Analysis worker logs\n"
                "- server: Server logs (MCP proxy, etc.)\n\n"
                "Use cases:\n"
                "- Discover available log files\n"
                "- Find log files for specific workers\n"
                "- Get log file metadata (size, modified time)\n"
                "- List all logs before viewing specific ones\n\n"
                "Important notes:\n"
                "- Default log directory is 'logs' if not specified\n"
                "- Can scan multiple directories if log_dirs provided\n"
                "- Returns file metadata including path, size, and modified time\n"
                "- Filter by worker_type to find specific worker logs"
            ),
            "parameters": {
                "log_dirs": {
                    "description": (
                        "List of directories to scan for log files. Optional. "
                        "If not provided, defaults to ['logs']. "
                        "Can specify multiple directories to scan."
                    ),
                    "type": "array",
                    "required": False,
                    "items": {"type": "string"},
                    "examples": [
                        ["logs"],
                        ["logs", "custom_logs"],
                        ["/var/log/code_analysis"],
                    ],
                },
                "worker_type": {
                    "description": (
                        "Filter by worker type. Optional. Options: 'file_watcher', 'vectorization', "
                        "'analysis', 'server'. If not specified, returns all log files."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": ["file_watcher", "vectorization", "analysis", "server"],
                },
            },
            "usage_examples": [
                {
                    "description": "List all log files in default logs directory",
                    "command": {},
                    "explanation": (
                        "Lists all log files in the 'logs' directory."
                    ),
                },
                {
                    "description": "List file_watcher logs",
                    "command": {
                        "worker_type": "file_watcher",
                    },
                    "explanation": (
                        "Lists only file_watcher log files."
                    ),
                },
                {
                    "description": "List logs from custom directories",
                    "command": {
                        "log_dirs": ["logs", "custom_logs", "/var/log/code_analysis"],
                    },
                    "explanation": (
                        "Scans multiple directories for log files."
                    ),
                },
                {
                    "description": "List server logs",
                    "command": {
                        "worker_type": "server",
                    },
                    "explanation": (
                        "Lists server log files (MCP proxy, etc.)."
                    ),
                },
            ],
            "error_cases": {
                "LOG_LIST_ERROR": {
                    "description": "General error during log listing",
                    "example": "Directory not found, permission denied, or scan error",
                    "solution": (
                        "Verify log directories exist and are accessible. Check file permissions. "
                        "Ensure directories are readable."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "log_files": (
                            "List of log files. Each entry contains:\n"
                            "- path: Full path to log file\n"
                            "- name: Log file name\n"
                            "- size: File size in bytes\n"
                            "- modified_time: Last modified timestamp\n"
                            "- worker_type: Detected worker type (if applicable)"
                        ),
                        "total_files": "Total number of log files found",
                        "scanned_dirs": "List of directories that were scanned",
                    },
                    "example": {
                        "log_files": [
                            {
                                "path": "logs/file_watcher.log",
                                "name": "file_watcher.log",
                                "size": 1048576,
                                "modified_time": "2025-01-26T10:30:00",
                                "worker_type": "file_watcher",
                            },
                            {
                                "path": "logs/vectorization.log",
                                "name": "vectorization.log",
                                "size": 2048576,
                                "modified_time": "2025-01-26T10:25:00",
                                "worker_type": "vectorization",
                            },
                        ],
                        "total_files": 2,
                        "scanned_dirs": ["logs"],
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., LOG_LIST_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use this command first to discover available log files",
                "Filter by worker_type to find specific worker logs",
                "Specify custom log_dirs if logs are in non-standard locations",
                "Use returned log file paths with view_worker_logs command",
                "Check file sizes to identify large log files that may need rotation",
            ],
        }
