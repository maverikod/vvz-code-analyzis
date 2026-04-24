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
            "**CRITICAL — required parameter:** You MUST pass `worker_type` in `params` "
            '(e.g. `{"worker_type": "vectorization"}`). '
            "`params: {}` is invalid and will fail with \"required parameter 'worker_type' is missing\".\n\n"
            "The get_worker_status command monitors worker process status, resource usage, "
            "and recent activity. It supports workers: file_watcher, vectorization, and indexing. "
            "The command provides comprehensive information about worker processes including "
            "CPU/memory usage, uptime, lock file status, and log activity.\n\n"
            "Operation flow:\n"
            "1. Validates worker_type parameter (file_watcher, vectorization, or indexing)\n"
            "2. Attempts to get registered workers from WorkerManager\n"
            "3. If no registered workers, searches for processes by name pattern\n"
            "4. For file_watcher, checks lock file status if provided\n"
            "5. Reads PID from PID file if log_path provided (fallback)\n"
            "6. Collects process information (CPU, memory, uptime)\n"
            "7. Analyzes recent log activity if log_path provided\n"
            "8. Returns comprehensive status summary\n\n"
            "Worker Types:\n"
            "- file_watcher: Monitors file system changes and updates database\n"
            "- vectorization: Processes code chunks and generates embeddings\n"
            "- indexing: Indexes files with needs_chunking=1 (AST, CST, fulltext)\n\n"
            "Process Discovery Methods:\n"
            "1. WorkerManager: Gets registered workers (most reliable)\n"
            "2. Process name search: Searches running processes by cmdline pattern\n"
            "3. Lock file: For file_watcher, uses lock file PID\n"
            "4. PID file: Reads PID from <worker>.pid file (if log_path provided)\n\n"
            "Resource Monitoring:\n"
            "- CPU usage: Percentage of CPU time used (per process and total)\n"
            "- Memory usage: Resident Set Size (RSS) in megabytes\n"
            "- Uptime: Process uptime in seconds\n"
            "- Process status: Running state (running, sleeping, etc.)\n\n"
            "Lock File (file_watcher only):\n"
            "- Contains PID, creation timestamp, worker name, hostname\n"
            "- Used to identify active file watcher process\n"
            "- Validates that process is still alive\n\n"
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
            "- PID file discovery works if log_path points to .log file"
        ),
        "parameters": {
            "worker_type": {
                "description": (
                    "**REQUIRED (not optional).** Must be exactly one of: `file_watcher`, "
                    "`vectorization`, or `indexing`. Omitting this field causes command failure."
                ),
                "type": "string",
                "required": True,
                "enum": ["file_watcher", "vectorization", "indexing"],
                "examples": ["file_watcher", "vectorization", "indexing"],
            },
            "log_path": {
                "description": (
                    "Optional path to worker log file. If provided:\n"
                    "- Enables log activity analysis\n"
                    "- Enables PID file discovery (<log_name>.pid)\n"
                    "- Should point to worker's log file (e.g., file_watcher.log)"
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
                    "Optional path to lock file (for file_watcher only). "
                    "Lock file contains PID and metadata of active file watcher. "
                    "Used to identify the correct worker process."
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
                        "message": "Invalid worker_type",
                        "solution": "Use 'file_watcher', 'vectorization', or 'indexing'",
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
                        "Lock file information (file_watcher only). Contains:\n"
                        "- exists: Whether lock file exists\n"
                        "- pid: PID from lock file\n"
                        "- process_alive: Whether process is still running\n"
                        "- created_at: Lock file creation timestamp\n"
                        "- worker_name: Worker name\n"
                        "- hostname: Hostname where worker runs"
                    ),
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
