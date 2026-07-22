"""Start repair worker MCP command."""

import logging
from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand
from ..repair_worker_management import RepairWorkerManager

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
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
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
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        version_dir: str = "data/versions",
        batch_size: int = 10,
        poll_interval: int = 30,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute start repair worker command.

        Args:
            project_id: Project UUID (from create_project or list_projects).
            version_dir: Version directory for deleted files (relative to project root)
            batch_size: Number of files to process per batch
            poll_interval: Interval in seconds between repair cycles

        Returns:
            SuccessResult with start result or ErrorResult on failure
        """
        try:
            root_path = self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)

            if not Path(version_dir).is_absolute():
                version_dir = str(root_path / version_dir)

            storage = BaseMCPCommand._get_shared_storage()
            db_path = storage.db_path
            worker_log_path = root_path / "logs" / "repair_worker.log"

            try:
                manager = RepairWorkerManager(
                    db_path=db_path,
                    project_id=project_id,
                    root_dir=root_path,
                    version_dir=version_dir,
                    worker_log_path=worker_log_path,
                    batch_size=batch_size,
                    poll_interval=poll_interval,
                )
                result = manager.start()
                return SuccessResult(data=result)
            finally:
                database.disconnect()

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
                "6. Resolves shared database path from server config and worker log path\n"
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
                        "Used for version_dir and logs; database path comes from server config (shared DB)."
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
                                "Check PostgreSQL server logs and connectivity."
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
