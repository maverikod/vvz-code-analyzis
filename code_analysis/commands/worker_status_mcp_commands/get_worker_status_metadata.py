"""
Metadata for get_worker_status MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Type


def get_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return full metadata dict for GetWorkerStatusMCPCommand."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "**Optional `worker_type`:** Omit it or set `worker_type` to `all` to aggregate every "
            "registered worker in one response. Pass a specific type to scope processes, log "
            "activity, and DB cycle stats to that worker only.\n\n"
            "The get_worker_status command monitors worker process status, resource usage, "
            "and recent activity. It supports workers: file_watcher, vectorization, indexing, "
            "and aggregate mode `all` (or omit `worker_type`). "
            "The command provides information about processes registered in WorkerManager, "
            "optional lock file metadata, log tail activity when `log_path` resolves, and "
            "optional DB-backed `cycle_stats` from the MCP layer.\n\n"
            "Operation flow:\n"
            "1. Validates optional worker_type (file_watcher, vectorization, indexing, or all)\n"
            "2. Resolves default log_path from server config when omitted and worker_type is a single type\n"
            "3. WorkerStatusCommand reads PIDs from WorkerManager registry (by_type); no cmdline scan\n"
            "4. For each PID, collects psutil process fields (CPU, memory, uptime, status)\n"
            "5. If lock_file_path is set: for worker_type file_watcher or all, reads lock JSON (informational)\n"
            "6. If log_path points to an existing .log file: analyzes last lines for log_activity\n"
            "7. If log_path follows the .log convention: may read sibling .status.json for progress fields\n"
            "8. Optionally compares known PID files under logs/ to registry and logs if mismatched\n"
            "9. MCP layer may attach cycle_stats from DB (single object per type, or dict keyed by type when all)\n\n"
            "Worker Types:\n"
            "- file_watcher: Monitors file system changes and updates database\n"
            "- vectorization: Processes code chunks and generates embeddings\n"
            "- indexing: Indexes files with needs_chunking=1 (AST, CST, fulltext)\n"
            "- all / omitted worker_type: Same registry query merged across all registered types\n\n"
            "Process / PID sources:\n"
            "1. WorkerManager registry (primary; processes list is built only from registered PIDs)\n"
            "2. PID files next to logs (vectorization_worker.pid, file_watcher_worker.pid, indexing_worker.pid): "
            "consistency check vs registry only, not used to populate processes\n"
            "3. Lock file: optional metadata when lock_file_path is provided (file_watcher semantics)\n\n"
            "Resource Monitoring:\n"
            "- CPU usage: Percentage of CPU time used (per process and total)\n"
            "- Memory usage: Resident Set Size (RSS) in megabytes\n"
            "- Uptime: Process uptime in seconds\n"
            "- Process status: Running state (running, sleeping, etc.)\n\n"
            "Lock File (when lock_file_path set):\n"
            "- JSON with PID, creation timestamp, worker name, hostname\n"
            "- Response includes process_alive check; does not add processes to the list\n\n"
            "Log Activity:\n"
            "- Analyzes recent log entries (last 10 lines by default)\n"
            "- Extracts timestamp from log entries\n"
            "- Calculates age of last entry\n"
            "- Provides file size information\n\n"
            "Use cases:\n"
            "- Monitor worker health and resource usage\n"
            "- Troubleshoot worker issues\n"
            "- Check if workers are running\n"
            "- Monitor worker performance\n"
            "- Verify worker activity from logs\n"
            "- Debug worker startup problems\n\n"
            "Important notes:\n"
            "- Requires psutil library for process information\n"
            "- Process discovery may find multiple workers of same type\n"
            "- Lock file is optional but recommended for file_watcher\n"
            "- Log path is optional but enables activity monitoring\n"
            "- Sibling .pid / .status.json are derived from log_path basename when log_path ends with .log\n"
            "- cycle_stats: present when DB exposes stats getters; shape is one object per worker_type, "
            "or an object with keys file_watcher / vectorization / indexing when worker_type is all"
        ),
        "parameters": {
            "worker_type": {
                "description": (
                    "Optional. One of `file_watcher`, `vectorization`, `indexing`, or `all`. "
                    "Omit or use `all` to include every registered worker; DB `cycle_stats` is "
                    "then keyed by worker type when available."
                ),
                "type": "string",
                "required": False,
                "enum": ["file_watcher", "vectorization", "indexing", "all"],
                "examples": ["file_watcher", "vectorization", "indexing", "all"],
            },
            "log_path": {
                "description": (
                    "Optional path to worker log file. If provided and the file exists:\n"
                    "- Enables log_activity (tail of last lines)\n"
                    "- If path ends with .log, enables sibling <name>.status.json for progress fields\n"
                    "- Sibling <name>.pid may be checked against WorkerManager for diagnostics (not used "
                    "to build the processes list)\n"
                    "- When worker_type is a single type and this param is omitted, the server may fill "
                    "it from config (code_analysis.worker / file_watcher / indexing_worker log_path)"
                ),
                "type": "string",
                "required": False,
                "examples": [
                    "/home/user/projects/my_project/logs/file_watcher.log",
                    "logs/vectorization.log",
                ],
            },
            "lock_file_path": {
                "description": (
                    "Optional path to lock file (file_watcher semantics). "
                    "Read when worker_type is file_watcher or all. "
                    "Returns lock JSON metadata only; process list still comes from WorkerManager."
                ),
                "type": "string",
                "required": False,
                "examples": [
                    "/home/user/projects/my_project/data/file_watcher.lock",
                ],
            },
        },
        "usage_examples": [
            {
                "description": "Check all workers (omit worker_type)",
                "command": {},
                "explanation": (
                    "Returns combined process list from WorkerManager for every registered type; "
                    "optional cycle_stats object keyed by worker type when the DB exposes stats."
                ),
            },
            {
                "description": "Explicit all workers",
                "command": {"worker_type": "all"},
                "explanation": "Same as empty params: aggregate every registered worker.",
            },
            {
                "description": "Check file watcher status",
                "command": {"worker_type": "file_watcher"},
                "explanation": (
                    "Checks status of file watcher workers. "
                    "Searches for processes and returns status information."
                ),
            },
            {
                "description": "Check vectorization worker with log",
                "command": {
                    "worker_type": "vectorization",
                    "log_path": "/home/user/projects/my_project/logs/vectorization.log",
                },
                "explanation": (
                    "Checks vectorization worker status and analyzes log activity. "
                    "Also attempts PID file discovery from log path."
                ),
            },
            {
                "description": "Check file watcher with lock file",
                "command": {
                    "worker_type": "file_watcher",
                    "lock_file_path": "/home/user/projects/my_project/data/file_watcher.lock",
                    "log_path": "/home/user/projects/my_project/logs/file_watcher.log",
                },
                "explanation": (
                    "Checks file watcher using lock file for process identification "
                    "and log file for activity monitoring."
                ),
            },
        ],
        "error_cases": {
            "WORKER_STATUS_ERROR": {
                "description": "Error during worker status check",
                "examples": [
                    {
                        "case": "Invalid worker type",
                        "message": "parameter 'worker_type' must be one of enum values",
                        "solution": (
                            "Use 'file_watcher', 'vectorization', 'indexing', or 'all'; "
                            "or omit worker_type for the same behavior as 'all'."
                        ),
                    },
                    {
                        "case": "Permission denied",
                        "message": "Access denied to process",
                        "solution": (
                            "Check process permissions. May need elevated privileges "
                            "to access other users' processes."
                        ),
                    },
                    {
                        "case": "Log file read error",
                        "message": "Error reading log file",
                        "solution": (
                            "Verify log_path is correct and file is readable. "
                            "Error is logged but doesn't fail the command."
                        ),
                    },
                ],
            },
        },
        "return_value": {
            "success": {
                "description": "Worker status retrieved successfully",
                "data": {
                    "worker_type": "Type of worker checked",
                    "timestamp": "ISO timestamp of status check",
                    "processes": (
                        "List of worker process information. Each contains:\n"
                        "- pid: Process ID\n"
                        "- status: Process status (running, sleeping, etc.)\n"
                        "- cpu_percent: CPU usage percentage\n"
                        "- memory_mb: Memory usage in megabytes\n"
                        "- create_time: Process creation timestamp\n"
                        "- uptime_seconds: Process uptime in seconds\n"
                        "- cmdline: Process command line (first 3 args)"
                    ),
                    "lock_file": (
                        "Lock file JSON when lock_file_path was provided and worker_type is "
                        "file_watcher or all. Informational only; not merged into processes list. "
                        "Fields: exists, pid, process_alive, created_at, worker_name, hostname (or error)."
                    ),
                    "cycle_stats": (
                        "Optional. From DB after status: one enriched stats object when worker_type is "
                        "a single type; when worker_type is all or omitted, a dict with keys among "
                        "file_watcher, vectorization, indexing (only keys with data)."
                    ),
                    "current_operation": "Optional string from sibling .status.json of log_path",
                    "current_file": "Optional string from status file",
                    "progress_percent": "Optional number from status file",
                    "progress_updated_at": "Optional ISO timestamp from status file",
                    "log_activity": (
                        "Recent log activity information. Contains:\n"
                        "- available: Whether log file is available\n"
                        "- file_size_mb: Log file size in megabytes\n"
                        "- last_entry: Last log entry with timestamp and age\n"
                        "- recent_lines_count: Number of recent lines analyzed"
                    ),
                    "summary": {
                        "process_count": "Number of worker processes found",
                        "is_running": "True if any processes are running",
                        "total_cpu_percent": "Total CPU usage across all processes",
                        "total_memory_mb": "Total memory usage in megabytes",
                        "oldest_process_uptime_seconds": "Uptime of oldest process",
                    },
                },
                "example_running": {
                    "worker_type": "file_watcher",
                    "timestamp": "2024-01-15T14:30:25",
                    "processes": [
                        {
                            "pid": 12345,
                            "status": "running",
                            "cpu_percent": 2.5,
                            "memory_mb": 45.2,
                            "create_time": "2024-01-15T10:00:00",
                            "uptime_seconds": 16225,
                            "cmdline": "python -m code_analysis.workers.file_watcher",
                        }
                    ],
                    "lock_file": {
                        "exists": True,
                        "pid": 12345,
                        "process_alive": True,
                        "created_at": "2024-01-15T10:00:00",
                        "worker_name": "file_watcher",
                        "hostname": "server1",
                    },
                    "log_activity": {
                        "available": True,
                        "file_size_mb": 2.5,
                        "last_entry": {
                            "timestamp": "2024-01-15T14:29:50",
                            "age_seconds": 35,
                            "line": "2024-01-15 14:29:50 | INFO | Processed file: src/main.py",
                        },
                        "recent_lines_count": 10,
                    },
                    "summary": {
                        "process_count": 1,
                        "is_running": True,
                        "total_cpu_percent": 2.5,
                        "total_memory_mb": 45.2,
                        "oldest_process_uptime_seconds": 16225,
                    },
                },
                "example_not_running": {
                    "worker_type": "vectorization",
                    "timestamp": "2024-01-15T14:30:25",
                    "processes": [],
                    "lock_file": None,
                    "log_activity": {"available": False},
                    "summary": {
                        "process_count": 0,
                        "is_running": False,
                        "total_cpu_percent": 0,
                        "total_memory_mb": 0,
                    },
                },
            },
            "error": {
                "description": "Command failed",
                "code": "Error code (e.g., WORKER_STATUS_ERROR)",
                "message": "Human-readable error message",
            },
        },
        "best_practices": [
            "Use log_path to enable log activity monitoring",
            "Use lock_file_path for file_watcher to get accurate process identification",
            "Check summary.is_running to quickly see if workers are active",
            "Monitor total_cpu_percent and total_memory_mb for resource usage",
            "Check log_activity.last_entry.age_seconds to verify recent activity",
            "Use process_count to detect multiple workers (may indicate issues)",
            "Check oldest_process_uptime_seconds to see worker stability",
            "If processes list is empty, worker may not be running",
        ],
    }
