"""
MCP command wrappers for log viewer operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from .log_viewer import (
    ListLogFilesCommand,
    LogViewerCommand,
    RotateLogsCommand,
    parse_log_timestamp,
    parse_timing_line,
)

logger = logging.getLogger(__name__)

# Default log filenames per worker type (one log per worker)
WORKER_LOG_FILENAMES = {
    "file_watcher": "file_watcher.log",
    "vectorization": "vectorization_worker.log",
    "indexing": "indexing_worker.log",
    "database_driver": "database_driver.log",
    "analysis": "comprehensive_analysis.log",
    "server": "mcp_server.log",
}


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

    async def execute(
        self,
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
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute view worker logs command.

        Args:
            log_path: Path to log file (optional if worker_type given and config available)
            worker_type: Type of worker (file_watcher, vectorization, indexing, database_driver, analysis)
            from_time: Start time filter
            to_time: End time filter
            event_types: List of event types to filter
            log_levels: List of log levels to filter
            search_pattern: Text pattern to search for (regex)
            importance_min: Minimum importance 0-10 (inclusive)
            importance_max: Maximum importance 0-10 (inclusive)
            tail: Return last N lines
            limit: Maximum number of lines to return

        Returns:
            SuccessResult with log entries or ErrorResult on failure
        """
        try:
            resolved_path = log_path
            if not resolved_path:
                resolved_path = self._resolve_worker_log_path(worker_type)
            if not resolved_path:
                return ErrorResult(
                    code="MISSING_LOG_PATH",
                    message="Provide log_path or ensure worker_type is set and server config is available to resolve default log path",
                )
            command = LogViewerCommand(
                log_path=resolved_path,
                worker_type=worker_type,
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
        """Resolve default log path for worker_type from server config (config_dir/logs/<name>)."""
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
                "5. Parses each log line (unified or legacy format) to extract timestamp, level, importance (0-10), and message\n"
                "6. Applies filters:\n"
                "   - Time range filter (from_time to to_time; partial interval supported)\n"
                "   - Event type filter (matches event patterns)\n"
                "   - Log level filter (INFO, ERROR, WARNING, etc.)\n"
                "   - Importance filter (importance_min, importance_max 0-10)\n"
                "   - Search pattern filter (regex on message)\n"
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
                "- Log lines are parsed to extract timestamp, level, importance (0-10), and message\n"
                "- importance_min/importance_max are filters only (they select which lines are returned); "
                "importance is assigned when logs are written. As logs gradually fill up, filtering by "
                "importance becomes more useful (e.g. importance_min=6 for warnings and above)."
            ),
            "parameters": {
                "log_path": {
                    "description": (
                        "Path to log file. Optional if worker_type is set and server config "
                        "provides config_dir (then default is config_dir/logs/<worker>.log). "
                        "Can be absolute or relative. File must exist and be readable."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "logs/file_watcher.log",
                        "/home/user/projects/my_project/logs/vectorization_worker.log",
                    ],
                },
                "worker_type": {
                    "description": (
                        "Type of worker. Options: 'file_watcher', 'vectorization', 'indexing', "
                        "'database_driver', 'analysis'. Default is 'file_watcher'. "
                        "Used to resolve default log path when log_path is omitted and for event patterns."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": [
                        "file_watcher",
                        "vectorization",
                        "indexing",
                        "database_driver",
                        "analysis",
                    ],
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
                    "items": {
                        "type": "string",
                        "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    },
                    "examples": [["ERROR", "WARNING"], ["INFO"]],
                },
                "search_pattern": {
                    "description": (
                        "Text pattern to search for. Supports regex (case-insensitive). "
                        "Only log lines whose message matches the pattern are returned."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["error", "failed", "circuit.*breaker"],
                },
                "importance_min": {
                    "description": (
                        "Minimum importance 0-10 (inclusive). See LOG_IMPORTANCE_CRITERIA.md. "
                        "If log line has no explicit importance, it is derived from level (DEBUG=2, INFO=4, WARNING=6, ERROR=8, CRITICAL=10)."
                    ),
                    "type": "integer",
                    "required": False,
                    "minimum": 0,
                    "maximum": 10,
                },
                "importance_max": {
                    "description": (
                        "Maximum importance 0-10 (inclusive). Use with importance_min to filter by importance range."
                    ),
                    "type": "integer",
                    "required": False,
                    "minimum": 0,
                    "maximum": 10,
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
                {
                    "description": "Filter by importance (errors and above)",
                    "command": {
                        "worker_type": "file_watcher",
                        "importance_min": 8,
                    },
                    "explanation": (
                        "Returns log entries with importance >= 8 (errors and critical)."
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
                            "- timestamp: Log timestamp (ISO format)\n"
                            "- level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)\n"
                            "- importance: Importance 0-10 (see LOG_IMPORTANCE_CRITERIA.md)\n"
                            "- message: Log message\n"
                            "- raw: Original log line"
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
                                "importance": 4,
                                "message": "[NEW FILE] src/main.py",
                                "raw": "2025-01-26 10:30:00 | INFO | 4 | [NEW FILE] src/main.py",
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
                "Use search_pattern for regex search on message",
                "Use importance_min/importance_max to filter by severity (0-10)",
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
                    "enum": [
                        "file_watcher",
                        "vectorization",
                        "indexing",
                        "database_driver",
                        "analysis",
                        "server",
                    ],
                    "description": "Filter by worker type (optional)",
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
            resolved_dirs = log_dirs
            if not resolved_dirs:
                try:
                    storage = BaseMCPCommand._get_shared_storage()
                    config_logs = str(storage.config_dir / "logs")
                    resolved_dirs = [config_logs, "logs"]
                except Exception:
                    resolved_dirs = ["logs"]
            command = ListLogFilesCommand(
                log_dirs=resolved_dirs, worker_type=worker_type
            )
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
                        "'indexing', 'database_driver', 'analysis', 'server'. If not specified, returns all log files."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": [
                        "file_watcher",
                        "vectorization",
                        "indexing",
                        "database_driver",
                        "analysis",
                        "server",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "List all log files in default logs directory",
                    "command": {},
                    "explanation": ("Lists all log files in the 'logs' directory."),
                },
                {
                    "description": "List file_watcher logs",
                    "command": {
                        "worker_type": "file_watcher",
                    },
                    "explanation": ("Lists only file_watcher log files."),
                },
                {
                    "description": "List logs from custom directories",
                    "command": {
                        "log_dirs": ["logs", "custom_logs", "/var/log/code_analysis"],
                    },
                    "explanation": ("Scans multiple directories for log files."),
                },
                {
                    "description": "List server logs",
                    "command": {
                        "worker_type": "server",
                    },
                    "explanation": ("Lists server log files (MCP proxy, etc.)."),
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


class RotateWorkerLogsMCPCommand(BaseMCPCommand):
    """Manually rotate a worker log file (current -> .1, .1 -> .2, ... new empty log)."""

    name = "rotate_worker_logs"
    version = "1.0.0"
    descr = "Manually rotate a worker log file"
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
                    "description": "Path to log file to rotate (optional if worker_type given)",
                },
                "worker_type": {
                    "type": "string",
                    "enum": [
                        "file_watcher",
                        "vectorization",
                        "indexing",
                        "database_driver",
                        "analysis",
                        "server",
                    ],
                    "description": "Worker type to resolve default log path (optional)",
                },
                "backup_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 99,
                    "description": "Number of backup files to keep (default 5)",
                    "default": 5,
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        log_path: Optional[str] = None,
        worker_type: Optional[str] = None,
        backup_count: int = 5,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute manual log rotation.

        Args:
            log_path: Path to log file (optional if worker_type and config available)
            worker_type: Resolve default log path by worker type
            backup_count: Number of backup files to keep (1-99)

        Returns:
            SuccessResult with rotated_paths and message or ErrorResult on failure
        """
        try:
            resolved_path = log_path
            if not resolved_path and worker_type:
                resolved_path = self._resolve_worker_log_path(worker_type)
            if not resolved_path:
                return ErrorResult(
                    code="MISSING_LOG_PATH",
                    message="Provide log_path or worker_type to resolve default log path",
                )
            command = RotateLogsCommand(
                log_path=resolved_path,
                backup_count=backup_count,
            )
            result = await command.execute()
            if result.get("error"):
                return ErrorResult(
                    code="ROTATE_LOG_ERROR",
                    message=result["error"],
                )
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "ROTATE_LOG_ERROR", "rotate_worker_logs")

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

    @classmethod
    def metadata(cls: type["RotateWorkerLogsMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The rotate_worker_logs command manually rotates a worker log file: "
                "the current log is renamed to .1, .1 to .2, etc. (same as RotatingFileHandler), "
                "then a new empty log file is created. Use when you want to archive logs without "
                "waiting for size-based rotation. The running worker may continue writing to the "
                "previous file (now .1) until it restarts or reopens the log.\n\n"
                "Parameters: log_path (optional if worker_type set), worker_type, backup_count (default 5)."
            ),
            "parameters": {
                "log_path": {
                    "description": "Path to the log file to rotate. Optional if worker_type is set.",
                    "type": "string",
                    "required": False,
                },
                "worker_type": {
                    "description": (
                        "Worker type to resolve default log path (e.g. file_watcher -> config_dir/logs/file_watcher.log). "
                        "Use when log_path is omitted."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": [
                        "file_watcher",
                        "vectorization",
                        "indexing",
                        "database_driver",
                        "analysis",
                        "server",
                    ],
                },
                "backup_count": {
                    "description": "Number of backup files to keep (1-99). Default 5.",
                    "type": "integer",
                    "required": False,
                    "default": 5,
                },
            },
            "usage_examples": [
                {
                    "description": "Rotate file_watcher log",
                    "command": {"worker_type": "file_watcher"},
                    "explanation": "Rotates the default file_watcher log (e.g. logs/file_watcher.log -> .1, new empty log).",
                },
                {
                    "description": "Rotate by path with 3 backups",
                    "command": {
                        "log_path": "logs/vectorization_worker.log",
                        "backup_count": 3,
                    },
                    "explanation": "Rotates the given log file and keeps 3 backup copies.",
                },
            ],
            "error_cases": {
                "MISSING_LOG_PATH": {
                    "description": "Neither log_path nor worker_type provided or path could not be resolved",
                    "solution": "Provide log_path or worker_type and ensure server config is available.",
                },
                "ROTATE_LOG_ERROR": {
                    "description": "OS error during rotation (permission, disk, etc.)",
                    "solution": "Check file permissions and disk space.",
                },
            },
            "return_value": {
                "success": {
                    "data": {
                        "log_path": "Path that was rotated",
                        "backup_count": "Number of backups kept",
                        "rotated_paths": "List of paths after rotation (e.g. [log.1, log.2])",
                        "message": "Human-readable summary",
                    },
                },
            },
        }


def _parse_time_optional(time_str: Optional[str]) -> Optional[datetime]:
    """Parse time string to datetime. ISO or YYYY-MM-DD HH:MM:SS or YYYY-MM-DD."""
    if not time_str:
        return None
    try:
        return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    try:
        return datetime.strptime(time_str, "%Y-%m-%d")
    except ValueError:
        return None


class AnalyzeTimingBottlenecksMCPCommand(BaseMCPCommand):
    """
    Collect [TIMING] lines from a worker log and compute bottlenecks by operation.

    Requires log_all_operations_timing enabled for the worker that produced the log.
    """

    name = "analyze_timing_bottlenecks"
    version = "1.0.0"
    descr = (
        "Collect [TIMING] lines from this server's worker logs and report bottlenecks "
        "by internal operation (server-side only; not about user projects the server serves)."
    )
    category = "logging"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters (exact same structure as other commands)."""
        return {
            "type": "object",
            "properties": {
                "log_path": {
                    "type": "string",
                    "description": "Path to log file (optional if worker_type is set and config available)",
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
                    "description": "Worker type to resolve default log path; default vectorization",
                    "default": "vectorization",
                },
                "from_time": {
                    "type": "string",
                    "description": "Start time filter (ISO or YYYY-MM-DD HH:MM:SS); only lines on or after this time",
                },
                "to_time": {
                    "type": "string",
                    "description": "End time filter (ISO or YYYY-MM-DD HH:MM:SS); only lines before this time",
                },
                "tail": {
                    "type": "integer",
                    "description": "Analyze only last N lines of the log (ignores time filters when set)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of log lines to scan (default 50000)",
                    "default": 50000,
                },
                "top_n": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Number of top bottlenecks to return by total and by average time (default 10)",
                    "default": 10,
                },
            },
            "required": [],
            "additionalProperties": False,
        }

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

    def _is_timing_enabled(self) -> bool:
        """Return True if log_all_operations_timing is enabled in code_analysis.worker config."""
        try:
            from ..core.storage_paths import load_raw_config

            config_path = BaseMCPCommand._resolve_config_path()
            config_data = load_raw_config(config_path)
            worker_config = config_data.get("code_analysis", {}).get("worker", {})
            return bool(worker_config.get("log_all_operations_timing", False))
        except Exception:
            return False

    async def execute(
        self,
        log_path: Optional[str] = None,
        worker_type: str = "vectorization",
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        tail: Optional[int] = None,
        limit: int = 50000,
        top_n: int = 10,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute analyze timing bottlenecks: read log, parse [TIMING] lines, aggregate by op_name.
        """
        from collections import deque
        from pathlib import Path

        if not self._is_timing_enabled():
            return ErrorResult(
                code="TIMING_DISABLED",
                message=(
                    "Timing is disabled. Enable log_all_operations_timing in code_analysis.worker config "
                    "to log [TIMING] lines and use this command."
                ),
            )
        resolved_path = log_path
        if not resolved_path:
            resolved_path = self._resolve_worker_log_path(worker_type)
        if not resolved_path:
            return ErrorResult(
                code="MISSING_LOG_PATH",
                message="Provide log_path or worker_type with server config to resolve default log path",
            )
        path = Path(resolved_path)
        if not path.exists() or not path.is_file():
            return ErrorResult(
                code="LOG_FILE_NOT_FOUND",
                message=f"Log file not found or not a file: {resolved_path}",
            )
        dt_from = _parse_time_optional(from_time)
        dt_to = _parse_time_optional(to_time)
        top_n = max(1, min(100, top_n))
        limit = max(1, min(1_000_000, limit))

        # Aggregate: op_name -> list of durations (seconds)
        agg: Dict[str, List[float]] = {}
        lines_scanned = 0
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                if tail is not None and tail > 0:
                    buf = deque(f, maxlen=min(tail, limit))
                    lines_scanned = len(buf)
                    for line in buf:
                        parsed = parse_timing_line(line)
                        if parsed is None:
                            continue
                        op_name, duration = parsed
                        agg.setdefault(op_name, []).append(duration)
                else:
                    for line in f:
                        if lines_scanned >= limit:
                            break
                        lines_scanned += 1
                        if dt_from is not None or dt_to is not None:
                            ts = parse_log_timestamp(line)
                            if ts is not None:
                                if dt_from is not None and ts < dt_from:
                                    continue
                                if dt_to is not None and ts > dt_to:
                                    continue
                        parsed = parse_timing_line(line)
                        if parsed is None:
                            continue
                        op_name, duration = parsed
                        agg.setdefault(op_name, []).append(duration)
        except OSError as e:
            return self._handle_error(e, "LOG_READ_ERROR", "analyze_timing_bottlenecks")

        # Build operations list: op_name, count, total_sec, avg_sec, min_sec, max_sec
        operations: List[Dict[str, Any]] = []
        for op_name, durations in agg.items():
            total_sec = sum(durations)
            count = len(durations)
            operations.append(
                {
                    "op_name": op_name,
                    "count": count,
                    "total_sec": round(total_sec, 3),
                    "avg_sec": round(total_sec / count, 3),
                    "min_sec": round(min(durations), 3),
                    "max_sec": round(max(durations), 3),
                }
            )
        operations.sort(key=lambda x: x["total_sec"], reverse=True)
        total_events = sum(len(d) for d in agg.values())
        total_duration_sec = sum(sum(d) for d in agg.values())

        bottlenecks_by_total = operations[:top_n]
        bottlenecks_by_avg = sorted(
            operations, key=lambda x: x["avg_sec"], reverse=True
        )[:top_n]

        data: Dict[str, Any] = {
            "log_path": resolved_path,
            "from_time": from_time,
            "to_time": to_time,
            "tail": tail,
            "lines_scanned": lines_scanned,
            "timing_events": total_events,
            "total_duration_sec": round(total_duration_sec, 3),
            "operations": operations,
            "bottlenecks_by_total": bottlenecks_by_total,
            "bottlenecks_by_avg": bottlenecks_by_avg,
            "message": (
                f"Parsed {total_events} timing events from {lines_scanned} lines; "
                f"total time {total_duration_sec:.1f}s across {len(operations)} operations."
            ),
        }
        return SuccessResult(data=data)

    @classmethod
    def metadata(cls: type["AnalyzeTimingBottlenecksMCPCommand"]) -> Dict[str, Any]:
        """
        Detailed command metadata for AI models (man-page style).
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "SCOPE — This command is about THIS SERVER's own internal operations (the code-analysis "
                "server process: its workers, chunking, embedding, DB access, etc.). It does NOT analyze "
                "or time user projects that the server indexes or serves. Use it to find performance "
                "bottlenecks in the server implementation, not in client/watched project code.\n\n"
                "The analyze_timing_bottlenecks command reads a worker log file produced by this server, "
                "collects every line that contains a [TIMING] entry (format: [TIMING] op_name duration=X.XXXs "
                "[key=value ...]), and aggregates them by operation name. It reports total time, average time, "
                "count, min, and max per operation, and returns two bottleneck lists: by total time "
                "(operations that consume the most time overall) and by average time (slowest per call).\n\n"
                "Operation flow:\n"
                "1. Resolve log file path: use log_path if provided, otherwise resolve from worker_type "
                "and server config (e.g. vectorization -> config_dir/logs/vectorization_worker.log).\n"
                "2. Open log file for reading (UTF-8, errors replaced).\n"
                "3. If tail is set: read only the last tail lines (and cap at limit).\n"
                "4. Otherwise: read lines sequentially up to limit; optionally filter by from_time and to_time "
                "using the timestamp at the start of each line (YYYY-MM-DD HH:MM:SS).\n"
                "5. For each line, detect [TIMING] and parse op_name and duration=X.XXXs with a regex.\n"
                "6. Aggregate by op_name: collect all durations, then compute count, sum, avg, min, max.\n"
                "7. Sort operations by total_sec descending; take first top_n as bottlenecks_by_total.\n"
                "8. Sort operations by avg_sec descending; take first top_n as bottlenecks_by_avg.\n"
                "9. Return all operations plus the two bottleneck lists and summary counts.\n\n"
                "When to use:\n"
                "- To optimize or debug THIS SERVER's performance (e.g. vectorization worker, indexing, "
                "chunking, embedding calls), enable log_all_operations_timing in code_analysis.worker config "
                "so that [TIMING] lines are written. Then run this command on the server's worker log to find "
                "which internal operations dominate total time or have the highest per-call latency.\n"
                "- Use tail for the most recent activity; use from_time/to_time for a specific time window.\n\n"
                "Log format:\n"
                "Lines must contain the substring [TIMING] and the pattern 'op_name duration=X.XXXs' "
                "(op_name is any non-whitespace token, X.XXX is a float). Unified log format "
                "'YYYY-MM-DD HH:MM:SS | LEVEL | importance | message' is supported; the message part is "
                "searched for [TIMING]. Other formats that contain [TIMING] and duration=...s are also "
                "accepted if the regex matches."
            ),
            "parameters": {
                "log_path": {
                    "description": (
                        "Path to THIS SERVER's worker log file (server logs, not project logs). Optional if "
                        "worker_type is set and server config provides config_dir (default: config_dir/logs/"
                        "<worker>.log). File must exist and be readable."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "logs/vectorization_worker.log",
                        "/var/log/code_analysis/vectorization_worker.log",
                    ],
                },
                "worker_type": {
                    "description": (
                        "Type of THIS SERVER's worker whose log to analyze (server-side only; not project-specific). "
                        "Options: file_watcher, vectorization, indexing, database_driver, analysis. "
                        "Default: vectorization. Used to resolve default log path when log_path is omitted. "
                        "Timing lines are typically emitted by the vectorization worker when "
                        "log_all_operations_timing is true."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": [
                        "file_watcher",
                        "vectorization",
                        "indexing",
                        "database_driver",
                        "analysis",
                    ],
                    "default": "vectorization",
                },
                "from_time": {
                    "description": (
                        "Start of time window. Only log lines with a timestamp on or after this time "
                        "are considered. ISO format ('2025-02-08T10:00:00') or 'YYYY-MM-DD HH:MM:SS' or "
                        "'YYYY-MM-DD'. When tail is set, time filters are ignored."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "2025-02-08T10:00:00",
                        "2025-02-08 10:00:00",
                        "2025-02-08",
                    ],
                },
                "to_time": {
                    "description": (
                        "End of time window. Only log lines with a timestamp before this time are considered. "
                        "Same formats as from_time."
                    ),
                    "type": "string",
                    "required": False,
                },
                "tail": {
                    "description": (
                        "If set, only the last N lines of the log file are read and analyzed. "
                        "When tail is set, from_time and to_time are ignored. Useful for quick "
                        "bottleneck analysis on recent activity."
                    ),
                    "type": "integer",
                    "required": False,
                    "examples": [1000, 50000],
                },
                "limit": {
                    "description": (
                        "Maximum number of log lines to scan when not using tail. Default 50000. "
                        "Prevents excessive I/O on very large log files."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 50000,
                },
                "top_n": {
                    "description": (
                        "Number of top operations to return in bottlenecks_by_total and "
                        "bottlenecks_by_avg. Between 1 and 100. Default 10."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "usage_examples": [
                {
                    "description": "Analyze last 10k lines of vectorization log",
                    "command": {"worker_type": "vectorization", "tail": 10000},
                    "explanation": "Reads last 10000 lines from default vectorization log and reports bottlenecks.",
                },
                {
                    "description": "Analyze by time window",
                    "command": {
                        "log_path": "logs/vectorization_worker.log",
                        "from_time": "2025-02-08 00:00:00",
                        "to_time": "2025-02-08 23:59:59",
                    },
                    "explanation": "Analyzes only lines within the given day.",
                },
                {
                    "description": "Top 20 bottlenecks by total and average",
                    "command": {
                        "worker_type": "vectorization",
                        "tail": 50000,
                        "top_n": 20,
                    },
                    "explanation": "Last 50k lines, return top 20 operations by total time and by average time.",
                },
            ],
            "error_cases": {
                "TIMING_DISABLED": {
                    "description": "log_all_operations_timing is false in code_analysis.worker config; server does not write [TIMING] lines",
                    "solution": "Set log_all_operations_timing to true in config and restart the server (or the worker) so that timing lines are written. Then run this command again.",
                },
                "MISSING_LOG_PATH": {
                    "description": "Neither log_path nor worker_type provided, or path could not be resolved from config",
                    "solution": "Provide log_path explicitly or set worker_type and ensure server config is available.",
                },
                "LOG_FILE_NOT_FOUND": {
                    "description": "The resolved log file does not exist or is not a regular file",
                    "solution": "Check path and that the worker has written to the log (e.g. enable log_all_operations_timing and run the worker).",
                },
                "LOG_READ_ERROR": {
                    "description": "OS error while reading the log file (permission, I/O, etc.)",
                    "solution": "Ensure file is readable and disk is accessible.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully.",
                    "data": {
                        "log_path": "Resolved path of the analyzed log file.",
                        "from_time": "from_time parameter (or null).",
                        "to_time": "to_time parameter (or null).",
                        "tail": "tail parameter (or null).",
                        "lines_scanned": "Number of log lines read.",
                        "timing_events": "Number of [TIMING] lines parsed and aggregated.",
                        "total_duration_sec": "Sum of all operation durations (seconds).",
                        "operations": (
                            "List of all operations, each with: op_name, count, total_sec, avg_sec, min_sec, max_sec. "
                            "Sorted by total_sec descending."
                        ),
                        "bottlenecks_by_total": (
                            "First top_n operations when sorted by total_sec (biggest time consumers overall)."
                        ),
                        "bottlenecks_by_avg": (
                            "First top_n operations when sorted by avg_sec (slowest per call)."
                        ),
                        "message": "Human-readable summary.",
                    },
                    "example": {
                        "log_path": "logs/vectorization_worker.log",
                        "tail": 10000,
                        "lines_scanned": 10000,
                        "timing_events": 1523,
                        "total_duration_sec": 456.789,
                        "operations": [
                            {
                                "op_name": "Step0_get_chunks_batch",
                                "count": 100,
                                "total_sec": 120.5,
                                "avg_sec": 1.205,
                                "min_sec": 0.5,
                                "max_sec": 3.2,
                            },
                        ],
                        "bottlenecks_by_total": "[... top_n by total_sec ...]",
                        "bottlenecks_by_avg": "[... top_n by avg_sec ...]",
                        "message": "Parsed 1523 timing events from 10000 lines; total time 456.8s across 12 operations.",
                    },
                },
                "error": {
                    "description": "Command failed.",
                    "code": "One of TIMING_DISABLED, MISSING_LOG_PATH, LOG_FILE_NOT_FOUND, LOG_READ_ERROR.",
                    "message": "Human-readable error message.",
                },
            },
            "best_practices": [
                "Remember: this analyzes the server's own code (workers, chunking, DB), not user projects.",
                "Enable log_all_operations_timing in worker config before collecting data.",
                "Use tail for recent bottleneck analysis; use from_time/to_time for a specific window.",
                "Compare bottlenecks_by_total (where time is spent) with bottlenecks_by_avg (slow per call).",
                "Let the worker run for a while to accumulate timing data before analyzing.",
            ],
        }
