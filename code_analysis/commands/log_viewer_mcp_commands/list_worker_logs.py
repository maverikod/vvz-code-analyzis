"""
List worker log files MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..log_viewer import ListLogFilesCommand


class ListWorkerLogsMCPCommand(BaseMCPCommand):
    """List available worker log files."""

    name = "list_worker_logs"
    version = "1.0.0"
    descr = "List available worker log files"
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
                "log_dirs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of directories to scan for log files (optional, defaults to ['logs'])",
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
                    "description": "Filter by worker type (optional)",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        log_dirs: Optional[List[str]] = None,
        worker_type: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute list worker logs command."""
        try:
            resolved_dirs = log_dirs
            if not resolved_dirs:
                try:
                    storage = BaseMCPCommand._get_shared_storage()
                    config_logs = str(storage.config_dir / "logs")
                    resolved_dirs = [config_logs, "logs"]
                except Exception:
                    resolved_dirs = ["logs"]
            command = ListLogFilesCommand(
                log_dirs=resolved_dirs, worker_type=worker_type
            )
            result = await command.execute()
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "LOG_LIST_ERROR", "list_worker_logs")

    @classmethod
    def metadata(cls: type["ListWorkerLogsMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "parameters_summary": (
                "Optional: worker_type, log_dirs. No limit parameter."
            ),
            "detailed_description": (
                "The list_worker_logs command lists available worker log files in specified directories. "
                "It scans configured log directories and returns available log files for workers "
                "(file_watcher, vectorization, analysis) and server logs.\n\n"
                "Operation flow:\n"
                "1. If log_dirs provided, uses those directories\n"
                "2. If log_dirs not provided, defaults to ['logs'] directory\n"
                "3. Scans directories for log files\n"
                "4. If worker_type specified, filters by worker type\n"
                "5. If worker_type not specified, returns all log files\n"
                "6. Returns list of log files with metadata (path, size, modified time)"
            ),
            "parameters": {
                "log_dirs": {
                    "description": "List of directories to scan. Optional. Defaults to ['logs'].",
                    "type": "array",
                    "required": False,
                    "items": {"type": "string"},
                },
                "worker_type": {
                    "description": "Filter by worker type. Optional.",
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
            },
            "usage_examples": [
                {
                    "description": "List all log files",
                    "command": {},
                    "explanation": "Lists all in 'logs'.",
                },
                {
                    "description": "List file_watcher logs",
                    "command": {"worker_type": "file_watcher"},
                    "explanation": "Only file_watcher logs.",
                },
            ],
            "error_cases": {
                "LOG_LIST_ERROR": {
                    "description": "General error during log listing",
                    "solution": "Verify log directories exist and are accessible.",
                },
            },
            "return_value": {
                "success": {
                    "data": {
                        "log_files": "List of log files with path, size, modified_time.",
                        "total_files": "Count.",
                        "scanned_dirs": "Dirs scanned.",
                    }
                },
                "error": {
                    "code": "LOG_LIST_ERROR",
                    "message": "Human-readable message.",
                },
            },
            "best_practices": [
                "Use this command first to discover available log files",
                "Use returned paths with view_worker_logs",
            ],
        }
