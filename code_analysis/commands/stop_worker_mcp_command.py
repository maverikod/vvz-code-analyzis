"""
MCP command: stop_worker — stop background workers by type.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.worker_manager import get_worker_manager
from .worker_management_mcp_commands_schema import get_stop_worker_metadata


class StopWorkerMCPCommand(BaseMCPCommand):
    """
    Stop background workers by type using WorkerManager.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "stop_worker"
    version = "1.0.0"
    descr = "Stop background worker(s) by type (file_watcher or vectorization)"
    category = "worker_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["StopWorkerMCPCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "description": "Stop background worker(s) by type.",
            "properties": {
                "worker_type": {
                    "type": "string",
                    "enum": ["file_watcher", "vectorization", "indexing"],
                    "description": "Type of worker to stop.",
                    "examples": ["file_watcher"],
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds before force kill.",
                    "default": 10,
                    "examples": [10],
                },
            },
            "required": ["worker_type"],
            "additionalProperties": False,
            "examples": [
                {"worker_type": "file_watcher", "timeout": 10},
                {"worker_type": "vectorization", "timeout": 10},
            ],
        }

    async def execute(
        self: "StopWorkerMCPCommand",
        worker_type: str,
        timeout: int = 10,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute stop worker command."""
        try:
            worker_manager = get_worker_manager()
            result = worker_manager.stop_worker_type(
                worker_type, timeout=float(timeout)
            )
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "WORKER_STOP_ERROR", "stop_worker")

    @classmethod
    def metadata(cls: type["StopWorkerMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_stop_worker_metadata(
            cls.name,
            cls.version,
            cls.descr,
            cls.category,
            cls.author,
            cls.email,
        )
