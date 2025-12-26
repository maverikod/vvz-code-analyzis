"""
MCP command wrappers for worker status and database monitoring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from .worker_status import WorkerStatusCommand, DatabaseStatusCommand

logger = logging.getLogger(__name__)


class GetWorkerStatusMCPCommand(BaseMCPCommand):
    """Get worker process status and activity."""

    name = "get_worker_status"
    version = "1.0.0"
    descr = "Get worker process status, resource usage, and recent activity"
    category = "monitoring"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "worker_type": {
                    "type": "string",
                    "enum": ["file_watcher", "vectorization"],
                    "description": "Type of worker to check",
                },
                "log_path": {
                    "type": "string",
                    "description": "Path to worker log file (optional, for activity check)",
                },
                "lock_file_path": {
                    "type": "string",
                    "description": "Path to lock file (optional, for file_watcher)",
                },
            },
            "required": ["worker_type"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        worker_type: str,
        log_path: Optional[str] = None,
        lock_file_path: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute get worker status command.

        Args:
            worker_type: Type of worker (file_watcher or vectorization)
            log_path: Path to worker log file
            lock_file_path: Path to lock file (for file_watcher)

        Returns:
            SuccessResult with worker status or ErrorResult on failure
        """
        try:
            command = WorkerStatusCommand(
                worker_type=worker_type,
                log_path=log_path,
                lock_file_path=lock_file_path,
            )
            result = await command.execute()
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "WORKER_STATUS_ERROR", "get_worker_status")


class GetDatabaseStatusMCPCommand(BaseMCPCommand):
    """Get database state and statistics."""

    name = "get_database_status"
    version = "1.0.0"
    descr = "Get database state, statistics, and pending work"
    category = "monitoring"
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
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute get database status command.

        Args:
            root_dir: Root directory of the project

        Returns:
            SuccessResult with database status or ErrorResult on failure
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            data_dir = root_path / "data"
            db_path = data_dir / "code_analysis.db"

            command = DatabaseStatusCommand(db_path=str(db_path))
            result = await command.execute()
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "DATABASE_STATUS_ERROR", "get_database_status")
