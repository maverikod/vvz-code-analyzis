"""
MCP command wrappers for repair worker management.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from .repair_worker_management import RepairWorkerManager

logger = logging.getLogger(__name__)


class StartRepairWorkerMCPCommand(BaseMCPCommand):
    """Start repair worker process."""

    name = "start_repair_worker"
    version = "1.0.0"
    descr = "Start repair worker process for database integrity restoration"
    category = "repair_worker"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
                "version_dir": {
                    "type": "string",
                    "description": "Version directory for deleted files (default: data/versions)",
                    "default": "data/versions",
                },
                "batch_size": {
                    "type": "integer",
                    "description": "Number of files to process per batch (default: 10)",
                    "default": 10,
                },
                "poll_interval": {
                    "type": "integer",
                    "description": "Interval in seconds between repair cycles (default: 30)",
                    "default": 30,
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        project_id: Optional[str] = None,
        version_dir: str = "data/versions",
        batch_size: int = 10,
        poll_interval: int = 30,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute start repair worker command.

        Args:
            root_dir: Root directory of the project
            project_id: Optional project UUID
            version_dir: Version directory for deleted files
            batch_size: Number of files to process per batch
            poll_interval: Interval in seconds between repair cycles

        Returns:
            SuccessResult with start result or ErrorResult on failure
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            database = self._open_database(root_dir, auto_analyze=False)

            actual_project_id = self._get_project_id(database, root_path, project_id)
            if not actual_project_id:
                return ErrorResult(
                    message=(
                        f"Project not found: {project_id}"
                        if project_id
                        else "Failed to get or create project"
                    ),
                    code="PROJECT_NOT_FOUND",
                )

            # Resolve paths
            if not Path(version_dir).is_absolute():
                version_dir = str(root_path / version_dir)

            db_path = (
                root_path / database.db_path
                if hasattr(database, "db_path")
                else root_path / "data" / "code_analysis.db"
            )
            worker_log_path = root_path / "logs" / "repair_worker.log"

            try:
                manager = RepairWorkerManager(
                    db_path=db_path,
                    project_id=actual_project_id,
                    root_dir=root_path,
                    version_dir=version_dir,
                    worker_log_path=worker_log_path,
                    batch_size=batch_size,
                    poll_interval=poll_interval,
                )
                result = manager.start()
                return SuccessResult(data=result)
            finally:
                database.close()

        except Exception as e:
            return self._handle_error(
                e, "START_REPAIR_WORKER_ERROR", "start_repair_worker"
            )

    @classmethod
    def metadata(cls: type["StartRepairWorkerMCPCommand"]) -> Dict[str, Any]:
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
                "The start_repair_worker command starts a repair worker process that "
                "automatically restores database integrity by processing deleted files "
                "and restoring them from version directories. The worker runs in a "
                "separate process and operates continuously in the background.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Verifies project exists in database\n"
                "5. Resolves version_dir path (relative to root_dir if not absolute)\n"
                "6. Resolves database path and worker log path\n"
                "7. Checks if repair worker is already running\n"
                "8. Starts worker process using multiprocessing\n"
                "9. Registers worker in WorkerManager\n"
                "10. Returns start result with PID\n\n"
                "Repair Worker Functionality:\n"
                "- Processes deleted files in batches\n"
                "- Restores files from version directories\n"
                "- Updates database to mark files as active\n"
                "- Runs continuously with configurable poll interval\n"
                "- Logs activity to repair_worker.log\n\n"
                "Worker Configuration:\n"
                "- batch_size: Number of files processed per batch (default: 10)\n"
                "- poll_interval: Seconds between repair cycles (default: 30)\n"
                "- version_dir: Directory containing file versions (default: data/versions)\n"
                "- worker_log_path: Path to log file (default: logs/repair_worker.log)\n\n"
                "Process Management:\n"
                "- Worker runs as daemon process\n"
                "- Process is registered in WorkerManager\n"
                "- PID is returned for monitoring\n"
                "- Worker can be stopped with stop_repair_worker\n\n"
                "Use cases:\n"
                "- Automatically restore deleted files\n"
                "- Maintain database integrity\n"
                "- Recover from accidental file deletions\n"
                "- Continuous background repair operations\n"
                "- Automated database maintenance\n\n"
                "Important notes:\n"
                "- Only one repair worker can run at a time\n"
                "- Worker runs continuously until stopped\n"
                "- Worker processes files in batches to avoid overload\n"
                "- Log file is created automatically if it doesn't exist\n"
                "- Worker is registered in WorkerManager for centralized management"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db file."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/my_project",
                        ".",
                        "./code_analysis",
                    ],
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. If omitted, inferred from root_dir. "
                        "Project must exist in database."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "123e4567-e89b-12d3-a456-426614174000",
                    ],
                },
                "version_dir": {
                    "description": (
                        "Version directory for deleted files. Can be absolute or relative to root_dir. "
                        "Contains file versions for restoration. Default is 'data/versions'."
                    ),
                    "type": "string",
                    "required": False,
                    "default": "data/versions",
                    "examples": [
                        "data/versions",
                        "/backups/versions",
                    ],
                },
                "batch_size": {
                    "description": (
                        "Number of files to process per batch. Controls how many files "
                        "are processed in each repair cycle. Default is 10."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 10,
                    "examples": [5, 10, 20],
                },
                "poll_interval": {
                    "description": (
                        "Interval in seconds between repair cycles. Worker waits this "
                        "long between processing batches. Default is 30 seconds."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 30,
                    "examples": [15, 30, 60],
                },
            },
            "usage_examples": [
                {
                    "description": "Start repair worker with defaults",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Starts repair worker with default settings: "
                        "batch_size=10, poll_interval=30, version_dir=data/versions."
                    ),
                },
                {
                    "description": "Start with custom configuration",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "batch_size": 20,
                        "poll_interval": 60,
                        "version_dir": "/backups/versions",
                    },
                    "explanation": (
                        "Starts repair worker with custom batch size, poll interval, "
                        "and version directory location."
                    ),
                },
                {
                    "description": "Start with explicit project ID",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                    },
                    "explanation": (
                        "Starts repair worker for specific project ID. "
                        "Useful when multiple projects share same root_dir."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "message": "Project not found: {project_id}",
                    "solution": (
                        "Verify project_id is correct or ensure project is registered. "
                        "Run update_indexes to register project if needed."
                    ),
                },
                "START_REPAIR_WORKER_ERROR": {
                    "description": "Error starting repair worker",
                    "examples": [
                        {
                            "case": "Worker already running",
                            "message": "Repair worker already running (PID: {pid})",
                            "solution": (
                                "Stop existing worker first using stop_repair_worker, "
                                "or use the existing worker."
                            ),
                        },
                        {
                            "case": "Process start failure",
                            "message": "Repair worker process failed to start",
                            "solution": (
                                "Check system resources, permissions, and logs. "
                                "Verify database is accessible."
                            ),
                        },
                        {
                            "case": "Database error",
                            "message": "Error connecting to database",
                            "solution": (
                                "Verify database exists and is accessible. "
                                "Check database integrity with get_database_corruption_status."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "Worker started successfully",
                    "data": {
                        "success": "True if worker started, False if already running or failed",
                        "message": "Human-readable status message",
                        "pid": "Process ID of started worker (if successful)",
                        "exit_code": "Exit code if process failed to start (if applicable)",
                        "error": "Error message if start failed (if applicable)",
                    },
                    "example_success": {
                        "success": True,
                        "message": "Repair worker started (PID: 12345)",
                        "pid": 12345,
                    },
                    "example_already_running": {
                        "success": False,
                        "message": "Repair worker already running (PID: 12345)",
                        "pid": 12345,
                    },
                    "example_failed": {
                        "success": False,
                        "message": "Repair worker process failed to start",
                        "exit_code": 1,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, START_REPAIR_WORKER_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Check repair_worker_status before starting to avoid duplicates",
                "Use appropriate batch_size based on system resources",
                "Set poll_interval based on repair urgency (lower = more frequent)",
                "Monitor worker logs (logs/repair_worker.log) for activity",
                "Use stop_repair_worker to stop worker when no longer needed",
                "Verify version_dir exists and contains file versions",
                "Start worker after database operations that may create deleted files",
                "Monitor worker with repair_worker_status regularly",
            ],
        }


class StopRepairWorkerMCPCommand(BaseMCPCommand):
    """Stop repair worker process."""

    name = "stop_repair_worker"
    version = "1.0.0"
    descr = "Stop repair worker process gracefully"
    category = "repair_worker"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds before force kill (default: 10)",
                    "default": 10,
                },
                "force": {
                    "type": "boolean",
                    "description": "If True, immediately kill with SIGKILL (default: False)",
                    "default": False,
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        timeout: int = 10,
        force: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute stop repair worker command.

        Args:
            timeout: Timeout in seconds before force kill
            force: If True, immediately kill with SIGKILL

        Returns:
            SuccessResult with stop result or ErrorResult on failure
        """
        try:
            from .repair_worker_management import RepairWorkerManager

            # Create manager with minimal config (only for finding processes)
            manager = RepairWorkerManager(
                db_path=Path("/tmp/dummy.db"),  # Not used for stop
                project_id="dummy",
                root_dir=Path("/tmp"),
                version_dir="/tmp",
            )
            result = manager.stop(timeout=timeout, force=force)
            return SuccessResult(data=result)

        except Exception as e:
            return self._handle_error(
                e, "STOP_REPAIR_WORKER_ERROR", "stop_repair_worker"
            )

    @classmethod
    def metadata(cls: type["StopRepairWorkerMCPCommand"]) -> Dict[str, Any]:
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
                "The stop_repair_worker command stops running repair worker processes "
                "gracefully or forcefully. It finds all repair worker processes and "
                "terminates them using SIGTERM (graceful) or SIGKILL (force).\n\n"
                "Operation flow:\n"
                "1. Searches for all repair worker processes\n"
                "2. If no processes found, returns success immediately\n"
                "3. For each process:\n"
                "   - If force=True: Immediately sends SIGKILL\n"
                "   - If force=False: Sends SIGTERM and waits for graceful shutdown\n"
                "   - If timeout exceeded: Sends SIGKILL\n"
                "4. Verifies processes are terminated\n"
                "5. Returns summary of stopped processes\n\n"
                "Stop Methods:\n"
                "- Graceful (force=False): Sends SIGTERM, waits for process to exit\n"
                "  - Allows worker to finish current batch\n"
                "  - Clean shutdown with proper cleanup\n"
                "  - Uses timeout to prevent hanging\n"
                "- Force (force=True): Immediately sends SIGKILL\n"
                "  - Immediate termination\n"
                "  - No cleanup, may leave incomplete operations\n"
                "  - Use only when graceful stop fails\n\n"
                "Timeout Behavior:\n"
                "- If force=False, waits up to timeout seconds for graceful shutdown\n"
                "- If process doesn't exit within timeout, sends SIGKILL\n"
                "- Default timeout is 10 seconds\n"
                "- Timeout prevents hanging if process is unresponsive\n\n"
                "Process Discovery:\n"
                "- Searches for processes with 'repair_worker' or 'run_repair_worker' in cmdline\n"
                "- Uses psutil to find and manage processes\n"
                "- Handles multiple worker processes if present\n\n"
                "Use cases:\n"
                "- Stop repair worker when no longer needed\n"
                "- Stop worker before maintenance operations\n"
                "- Force stop unresponsive worker\n"
                "- Clean shutdown before system restart\n"
                "- Stop worker to change configuration\n\n"
                "Important notes:\n"
                "- Graceful stop is preferred (allows cleanup)\n"
                "- Force stop should be used only when necessary\n"
                "- Multiple processes may be stopped if found\n"
                "- Process discovery requires psutil library\n"
                "- Worker is automatically unregistered from WorkerManager"
            ),
            "parameters": {
                "timeout": {
                    "description": (
                        "Timeout in seconds before force kill. Used when force=False. "
                        "If process doesn't exit within timeout, SIGKILL is sent. "
                        "Default is 10 seconds."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 10,
                    "examples": [5, 10, 30],
                },
                "force": {
                    "description": (
                        "If True, immediately kill with SIGKILL without waiting. "
                        "If False, send SIGTERM and wait for graceful shutdown. "
                        "Default is False."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [False, True],
                },
            },
            "usage_examples": [
                {
                    "description": "Stop worker gracefully",
                    "command": {
                        "timeout": 10,
                        "force": False,
                    },
                    "explanation": (
                        "Stops repair worker gracefully with 10 second timeout. "
                        "Allows worker to finish current batch."
                    ),
                },
                {
                    "description": "Force stop worker immediately",
                    "command": {
                        "force": True,
                    },
                    "explanation": (
                        "Immediately kills repair worker with SIGKILL. "
                        "Use only when graceful stop fails."
                    ),
                },
                {
                    "description": "Stop with longer timeout",
                    "command": {
                        "timeout": 30,
                        "force": False,
                    },
                    "explanation": (
                        "Stops worker gracefully with 30 second timeout. "
                        "Gives worker more time to finish current operations."
                    ),
                },
            ],
            "error_cases": {
                "STOP_REPAIR_WORKER_ERROR": {
                    "description": "Error stopping repair worker",
                    "examples": [
                        {
                            "case": "Process not found",
                            "message": "No repair worker processes found",
                            "solution": (
                                "Worker may already be stopped. "
                                "Check repair_worker_status to verify."
                            ),
                        },
                        {
                            "case": "Permission denied",
                            "message": "Access denied to process",
                            "solution": (
                                "Check process permissions. May need elevated privileges "
                                "to stop processes owned by other users."
                            ),
                        },
                        {
                            "case": "Process still running after kill",
                            "message": "Still running",
                            "solution": (
                                "Process may be in uninterruptible state. "
                                "Wait and retry, or use force=True."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "Stop operation completed",
                    "data": {
                        "success": "True if all processes stopped, False if any failed",
                        "message": "Human-readable status message",
                        "killed": (
                            "List of successfully stopped processes. "
                            "Each contains: pid"
                        ),
                        "failed": (
                            "List of processes that failed to stop. "
                            "Each contains: pid, error"
                        ),
                    },
                    "example_success": {
                        "success": True,
                        "message": "Stopped 1 process(es), 0 failed",
                        "killed": [{"pid": 12345}],
                        "failed": [],
                    },
                    "example_no_processes": {
                        "success": True,
                        "message": "No repair worker processes found",
                        "killed": [],
                    },
                    "example_partial": {
                        "success": False,
                        "message": "Stopped 1 process(es), 1 failed",
                        "killed": [{"pid": 12345}],
                        "failed": [{"pid": 12346, "error": "Access denied"}],
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., STOP_REPAIR_WORKER_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use graceful stop (force=False) when possible",
                "Set appropriate timeout based on batch processing time",
                "Use force=True only when graceful stop fails",
                "Check repair_worker_status after stop to verify",
                "Monitor killed and failed lists in response",
                "Retry stop if process is still running",
                "Stop worker before database maintenance operations",
                "Stop worker before system restart or shutdown",
            ],
        }


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
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (for log path, optional)",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute repair worker status command.

        Args:
            root_dir: Root directory of the project (for log path, optional)

        Returns:
            SuccessResult with worker status or ErrorResult on failure
        """
        try:
            from .repair_worker_management import RepairWorkerManager

            # Create manager with minimal config
            worker_log_path = None
            if root_dir:
                root_path = self._validate_root_dir(root_dir)
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
