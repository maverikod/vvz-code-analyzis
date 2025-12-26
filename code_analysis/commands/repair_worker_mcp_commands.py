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

            db_path = root_path / database.db_path if hasattr(database, "db_path") else root_path / "data" / "code_analysis.db"
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
            return self._handle_error(e, "START_REPAIR_WORKER_ERROR", "start_repair_worker")


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
            return self._handle_error(e, "STOP_REPAIR_WORKER_ERROR", "stop_repair_worker")


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

