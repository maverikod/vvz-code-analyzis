"""
MCP command wrappers for file management operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand

logger = logging.getLogger(__name__)


class ListDeletedFilesMCPCommand(BaseMCPCommand):
    """List deleted files for a project (path in trash, original_path, in_trash)."""

    name = "list_deleted_files"
    version = "1.0.0"
    descr = (
        "List deleted files for a project; path is trash path, original_path in project"
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
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        List deleted files for the project.

        Returns entries with path (trash path when moved, else original),
        original_path, and in_trash=True only when file was moved to trash
        (FILE_TRASH_SPEC step 11).

        Args:
            project_id: Project UUID.

        Returns:
            SuccessResult with list of deleted file entries.
        """
        try:
            self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)
            try:
                rows = database.get_deleted_files(project_id)
                # path = trash path when file was moved (version_dir set); else original path (watcher-only)
                items = [
                    {
                        "id": r.get("id"),
                        "path": r.get("path"),
                        "original_path": r.get("original_path"),
                        "in_trash": bool(r.get("version_dir")),
                        "updated_at": r.get("updated_at"),
                    }
                    for r in rows
                ]
                return SuccessResult(data={"deleted_files": items, "total": len(items)})
            finally:
                database.disconnect()
        except Exception as e:
            return self._handle_error(
                e, "LIST_DELETED_FILES_ERROR", "list_deleted_files"
            )
