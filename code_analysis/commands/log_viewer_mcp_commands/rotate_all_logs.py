"""
Rotate all logs (main + workers) MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand

from ...core.log_rotation_all import run_rotation_all_logs
from ...core.storage_paths import load_raw_config


class RotateAllLogsMCPCommand(BaseMCPCommand):
    """Rotate all logs (main + workers) or a subset by filter; rotated files are packed (gzip)."""

    name = "rotate_all_logs"
    version = "1.0.0"
    descr = (
        "Rotate main and worker logs (optionally filtered). "
        "If log_filter omitted, rotates all; otherwise only logs matching filter. Rotated files are gzipped."
    )
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
                "log_filter": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional. List of log labels or path substrings to rotate. "
                        "If omitted or empty, all logs are rotated. "
                        "Labels: mcp_server, code_analysis, vectorization, file_watcher, indexing_worker."
                    ),
                },
                "backup_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 99,
                    "description": "Number of backup files to keep per log (default 5)",
                    "default": 5,
                },
                "pack_rotated": {
                    "type": "boolean",
                    "description": "If true, gzip rotated files (default true)",
                    "default": True,
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        log_filter: Optional[List[str]] = None,
        backup_count: int = 5,
        pack_rotated: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute rotate all logs."""
        try:
            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            config_dir = Path(config_path).resolve().parent

            result = run_rotation_all_logs(
                config_data=config_data,
                config_dir=config_dir,
                backup_count=backup_count,
                pack_rotated=pack_rotated,
                log_filter=log_filter if log_filter else None,
                timeout_seconds=30.0,
            )
            if result.get("status") == "lock_timeout":
                return ErrorResult(
                    code="ROTATION_LOCK_TIMEOUT",
                    message=result.get(
                        "message", "Rotation already in progress or lock timed out"
                    ),
                )
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "ROTATE_ALL_LOGS_ERROR", "rotate_all_logs")

    @classmethod
    def metadata(cls: type["RotateAllLogsMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The rotate_all_logs command rotates main process and worker log files: "
                "current log is renamed to .1, .1 to .2, etc., then rotated files are gzipped. "
                "Uses a process-wide lock. Filter: if log_filter omitted or empty, all known logs are rotated. "
                "Labels: mcp_server, code_analysis, vectorization, file_watcher, indexing_worker."
            ),
            "parameters": {
                "log_filter": {
                    "description": "Optional. List of labels or path substrings. If omitted, rotate all.",
                    "type": "array",
                    "items": {"type": "string"},
                    "required": False,
                },
                "backup_count": {
                    "description": "Number of backup files per log (1-99). Default 5.",
                    "type": "integer",
                    "required": False,
                    "default": 5,
                },
                "pack_rotated": {
                    "description": "If true, gzip rotated files. Default true.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
            },
        }
