"""Repair worker status MCP command."""

import logging
from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand
from ..repair_worker_management import RepairWorkerManager

logger = logging.getLogger(__name__)


class RepairWorkerStatusMCPCommand(BaseMCPCommand):
    """Get repair worker status."""

    name = "repair_worker_status"
    version = "1.0.0"
    descr = "Get repair worker process status and recent activity"
    category = "repair_worker"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute repair worker status command.

        Args:
            project_id: Project UUID (used to resolve log path).

        Returns:
            SuccessResult with worker status or ErrorResult on failure
        """
        try:
            root_path = self._resolve_project_root(project_id)
            worker_log_path = root_path / "logs" / "repair_worker.log"

            manager = RepairWorkerManager(
                db_path=Path("/tmp/dummy.db"),  # Not used for status
                project_id="dummy",
                root_dir=Path("/tmp"),
                version_dir="/tmp",
                worker_log_path=worker_log_path,
            )
            result = manager.status()
            return SuccessResult(data=result)

        except Exception as e:
            return self._handle_error(
                e, "REPAIR_WORKER_STATUS_ERROR", "repair_worker_status"
            )

    @classmethod
    def metadata(cls: type["RepairWorkerStatusMCPCommand"]) -> Dict[str, Any]:
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
                "The repair_worker_status command monitors repair worker process status, "
                "resource usage, and recent activity. It provides comprehensive information "
                "about running repair worker processes including CPU/memory usage, uptime, "
                "and log activity.\n\n"
                "Operation flow:\n"
                "1. If root_dir provided, resolves worker log path\n"
                "2. Creates RepairWorkerManager with minimal config\n"
                "3. Searches for repair worker processes by name pattern\n"
                "4. Gets process details (PID, CPU, memory, uptime) for each process\n"
                "5. Analyzes recent log activity if log file exists\n"
                "6. Calculates summary statistics\n"
                "7. Returns comprehensive status report\n\n"
                "Process Discovery:\n"
                "- Searches for processes with 'repair_worker' or 'run_repair_worker' in cmdline\n"
                "- Uses psutil to find and query processes\n"
                "- Handles multiple worker processes if present\n\n"
                "Resource Monitoring:\n"
                "- CPU usage: Percentage of CPU time used (per process and total)\n"
                "- Memory usage: Resident Set Size (RSS) in megabytes\n"
                "- Uptime: Process uptime in seconds\n"
                "- Process status: Running state (running, sleeping, etc.)\n\n"
                "Log Activity:\n"
                "- Analyzes recent log entries (last 10 lines by default)\n"
                "- Extracts timestamp from log entries\n"
                "- Calculates age of last entry\n"
                "- Provides file size information\n"
                "- Only available if root_dir provided and log file exists\n\n"
                "Summary Statistics:\n"
                "- process_count: Number of worker processes found\n"
                "- is_running: True if any processes are running\n"
                "- total_cpu_percent: Total CPU usage across all processes\n"
                "- total_memory_mb: Total memory usage in megabytes\n"
                "- oldest_process_uptime_seconds: Uptime of oldest process\n\n"
                "Use cases:\n"
                "- Monitor worker health and resource usage\n"
                "- Check if worker is running\n"
                "- Troubleshoot worker issues\n"
                "- Monitor worker performance\n"
                "- Verify worker activity from logs\n"
                "- Debug worker startup problems\n\n"
                "Important notes:\n"
                "- Requires psutil library for process information\n"
                "- Process discovery may find multiple workers\n"
                "- Log activity requires root_dir to locate log file\n"
                "- If no processes found, is_running will be False\n"
                "- Log file path: root_dir/logs/repair_worker.log"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Optional root directory of the project. If provided, used to locate "
                        "worker log file (logs/repair_worker.log) for activity monitoring. "
                        "If omitted, process status is still available but log activity is not."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "/home/user/projects/my_project",
                        ".",
                        "./code_analysis",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Check worker status without log",
                    "command": {},
                    "explanation": (
                        "Checks repair worker process status. "
                        "Returns process information but no log activity."
                    ),
                },
                {
                    "description": "Check worker status with log activity",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Checks repair worker status and analyzes log activity. "
                        "Provides comprehensive monitoring information."
                    ),
                },
            ],
            "error_cases": {
                "REPAIR_WORKER_STATUS_ERROR": {
                    "description": "Error during status check",
                    "examples": [
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
                                "Verify log file exists and is readable. "
                                "Error is logged but doesn't fail the command."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "Status retrieved successfully",
                    "data": {
                        "worker_type": "Always 'repair'",
                        "is_running": "True if any processes are running",
                        "processes": (
                            "List of process information. Each contains:\n"
                            "- pid: Process ID\n"
                            "- cpu_percent: CPU usage percentage\n"
                            "- memory_mb: Memory usage in megabytes\n"
                            "- create_time: Process creation timestamp\n"
                            "- uptime_seconds: Process uptime in seconds\n"
                            "- status: Process status (running, sleeping, etc.)"
                        ),
                        "log_activity": (
                            "Recent log activity information (if root_dir provided). Contains:\n"
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
                        "worker_type": "repair",
                        "is_running": True,
                        "processes": [
                            {
                                "pid": 12345,
                                "cpu_percent": 2.5,
                                "memory_mb": 45.2,
                                "create_time": "2024-01-15T10:00:00",
                                "uptime_seconds": 16225,
                                "status": "running",
                            }
                        ],
                        "log_activity": {
                            "available": True,
                            "file_size_mb": 2.5,
                            "last_entry": {
                                "timestamp": "2024-01-15T14:29:50",
                                "age_seconds": 35,
                                "line": "2024-01-15 14:29:50 | INFO | Processed batch: 5 files",
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
                        "worker_type": "repair",
                        "is_running": False,
                        "processes": [],
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
                    "code": "Error code (e.g., REPAIR_WORKER_STATUS_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use root_dir parameter to enable log activity monitoring",
                "Check summary.is_running to quickly see if worker is active",
                "Monitor total_cpu_percent and total_memory_mb for resource usage",
                "Check log_activity.last_entry.age_seconds to verify recent activity",
                "Use process_count to detect multiple workers (may indicate issues)",
                "Check oldest_process_uptime_seconds to see worker stability",
                "If processes list is empty, worker is not running",
                "Monitor regularly to ensure worker is functioning correctly",
            ],
        }
