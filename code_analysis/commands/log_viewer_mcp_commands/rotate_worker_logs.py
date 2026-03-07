"""
Rotate a single worker log file MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..log_viewer import RotateLogsCommand

from ._shared import WORKER_LOG_FILENAMES

logger = logging.getLogger(__name__)


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
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute manual log rotation."""
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
                "the current log is renamed to .1, .1 to .2, etc., then a new empty log file is created. "
                "Parameters: log_path (optional if worker_type set), worker_type, backup_count (default 5)."
            ),
            "parameters": {
                "log_path": {
                    "description": "Path to the log file to rotate. Optional if worker_type is set.",
                    "type": "string",
                    "required": False,
                },
                "worker_type": {
                    "description": "Worker type to resolve default log path.",
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
                    "explanation": "Rotates the default file_watcher log.",
                },
                {
                    "description": "Rotate by path with 3 backups",
                    "command": {
                        "log_path": "logs/vectorization_worker.log",
                        "backup_count": 3,
                    },
                    "explanation": "Rotates the given log and keeps 3 backups.",
                },
            ],
            "error_cases": {
                "MISSING_LOG_PATH": {
                    "description": "Neither log_path nor worker_type provided or path could not be resolved",
                    "solution": "Provide log_path or worker_type.",
                },
                "ROTATE_LOG_ERROR": {
                    "description": "OS error during rotation",
                    "solution": "Check file permissions and disk space.",
                },
            },
            "return_value": {
                "success": {
                    "data": {
                        "log_path": "Path rotated",
                        "backup_count": "Backups kept",
                        "rotated_paths": "List of paths after rotation",
                        "message": "Summary.",
                    }
                }
            },
        }
