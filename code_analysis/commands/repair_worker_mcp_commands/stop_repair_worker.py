"""Stop repair worker MCP command."""

import logging
from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand
from ..repair_worker_management import RepairWorkerManager

logger = logging.getLogger(__name__)


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
