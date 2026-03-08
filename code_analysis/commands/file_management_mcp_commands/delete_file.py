"""
MCP command wrappers for file management operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand
from ..file_management import MarkFileDeletedCommand

logger = logging.getLogger(__name__)


class DeleteFileMCPCommand(BaseMCPCommand):
    """Mark a file as deleted and move it to file trash (soft delete)."""

    name = "delete_file"
    version = "1.0.0"
    descr = "Mark file as deleted and move to file trash (soft delete)"
    category = "file_management"
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
                "file_path": {
                    "type": "string",
                    "description": "File path relative to project root (e.g. ai_admin/commands/foo.py).",
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute delete file command (mark as deleted, move to trash).

        Args:
            project_id: Project UUID (from create_project or list_projects).
            file_path: File path relative to project root.

        Returns:
            SuccessResult with success and message, or ErrorResult on failure.
        """
        try:
            self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)

            trash_dir: Optional[str] = None
            try:
                from ...core.storage_paths import load_raw_config, resolve_storage_paths

                config_path = self._resolve_config_path()
                config_data = load_raw_config(config_path)
                storage = resolve_storage_paths(
                    config_data=config_data, config_path=config_path
                )
                trash_dir = str(storage.trash_dir)
            except Exception:
                pass

            if not trash_dir:
                return ErrorResult(
                    code="DELETE_FILE_CONFIG_ERROR",
                    message=(
                        "trash_dir not configured. Set code_analysis.storage.trash_dir "
                        "in config.json to use delete_file."
                    ),
                )

            try:
                command = MarkFileDeletedCommand(
                    database=database,
                    project_id=project_id,
                    file_path=file_path,
                    trash_dir=trash_dir,
                )
                result = await command.execute()
                if result.get("error") == "FILE_NOT_FOUND":
                    return ErrorResult(
                        code="FILE_NOT_FOUND",
                        message=result.get(
                            "message", f"File not found in project: {file_path}"
                        ),
                    )
                if result.get("error"):
                    return ErrorResult(
                        code="DELETE_FILE_ERROR",
                        message=result.get("message", str(result.get("error"))),
                    )
                return SuccessResult(data=result)
            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "DELETE_FILE_ERROR", "delete_file")
