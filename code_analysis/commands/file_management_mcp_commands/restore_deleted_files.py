"""
MCP command wrappers for file management operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand
from ..file_management import RestoreDeletedFilesCommand

logger = logging.getLogger(__name__)


class RestoreDeletedFilesMCPCommand(BaseMCPCommand):
    """Batch restore deleted files with pre-check (no restore if any target exists)."""

    name = "restore_deleted_files"
    version = "1.0.0"
    descr = (
        "Restore multiple deleted files; cancelled if any target path already exists"
    )
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
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths (current in trash or original_path) to restore",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If True, only pre-check and return what would be restored",
                    "default": False,
                },
            },
            "required": ["project_id", "file_paths"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_paths: list,
        dry_run: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute batch restore.

        Args:
            project_id: Project UUID.
            file_paths: List of paths (trash path or original_path) to restore.
            dry_run: If True, only pre-check and report.

        Returns:
            SuccessResult with restored_paths, or ErrorResult with TARGET_FILE_EXISTS and conflicting_paths.
        """
        try:
            self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)
            try:
                command = RestoreDeletedFilesCommand(
                    database=database,
                    project_id=project_id,
                    file_paths=file_paths or [],
                    dry_run=dry_run,
                )
                result = await command.execute()
                if result.get("error") == "TARGET_FILE_EXISTS":
                    return ErrorResult(
                        code="TARGET_FILE_EXISTS",
                        message=result.get("message", ""),
                        data={"conflicting_paths": result.get("conflicting_paths", [])},
                    )
                return SuccessResult(data=result)
            finally:
                database.disconnect()
        except Exception as e:
            return self._handle_error(
                e, "RESTORE_DELETED_FILES_ERROR", "restore_deleted_files"
            )
