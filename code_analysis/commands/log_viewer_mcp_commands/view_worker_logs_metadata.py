"""
Metadata for view_worker_logs command (AI/man page style).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict


def get_view_worker_logs_metadata(cls: Any) -> Dict[str, Any]:
    """Build metadata dict for ViewWorkerLogsMCPCommand (uses cls.name, cls.version, etc.)."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "parameters_summary": (
            "Optional: log_id, log_path, worker_type, from_time, to_time, event_types, log_levels, "
            "search_pattern, importance_min, importance_max, tail, limit. Use tail or limit (not 'lines')."
        ),
        "detailed_description": (
            "The view_worker_logs command views worker logs with advanced filtering capabilities. "
            "It supports filtering by time range, event types, log levels, and text search patterns. "
            "The command parses log files and returns structured log entries.\n\n"
            "Operation flow:\n"
            "1. Resolves path: if log_id given, from config (same as rotate_all_logs); else log_path or worker_type\n"
            "2. Reads current log and rotated files (.1, .2, ... and .gz) in chronological order\n"
            "3. Parses time filters (from_time, to_time) if provided\n"
            "4. Selects event patterns based on worker_type (or derived from log_id)\n"
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
            "log_id": {
                "description": (
                    "Log identifier (preferred over path). Values: mcp_server, code_analysis, "
                    "vectorization, file_watcher, indexing_worker. Path is resolved from config; "
                    "reading includes rotated files (.1, .2, .gz). Use list_logs to get identifiers."
                ),
                "type": "string",
                "required": False,
                "enum": [
                    "mcp_server",
                    "code_analysis",
                    "vectorization",
                    "file_watcher",
                    "indexing_worker",
                ],
            },
            "log_path": {
                "description": (
                    "Path to log file. Optional if log_id or worker_type is set and server config "
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
            "Use list_logs to get log identifiers (log_id), then view_worker_logs with log_id to avoid paths",
            "Use list_worker_logs to find log files by path if needed",
        ],
    }
