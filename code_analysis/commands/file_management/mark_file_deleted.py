"""
Command to mark a file as deleted (soft delete) and move to file trash.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


class MarkFileDeletedCommand:
    """
    Command to mark a file as deleted (soft delete) and move to file trash.

    Process:
    1. Resolves file path against project root (normalization).
    2. Marks file as deleted in DB and moves it to trash_dir/project_id/...
    3. Sets deleted=1, stores original_path; file is no longer in project tree.

    Options:
    - file_path: File path (relative to project root or absolute).
    - project_id: Project ID.
    - trash_dir: Preferred file trash root (from config); when set, files go under trash_dir/project_id/...
    - version_dir: Legacy directory for deleted files (used when trash_dir is None).
    """

    def __init__(
        self,
        database: "DatabaseClient",
        project_id: str,
        file_path: str,
        trash_dir: Optional[str] = None,
        version_dir: Optional[str] = None,
    ):
        """
        Initialize mark file deleted command.

        Args:
            database: DatabaseClient instance.
            project_id: Project UUID.
            file_path: File path (relative to project root or absolute).
            trash_dir: Optional file trash root; when set, files go under trash_dir/project_id/...
            version_dir: Optional legacy version directory (used when trash_dir is None).
        """
        self.database = database
        self.project_id = project_id
        self.file_path = file_path
        self.trash_dir = trash_dir
        self.version_dir = version_dir

    async def execute(self) -> Dict[str, Any]:
        """
        Execute mark file deleted command.

        Returns:
            Dictionary with success, file_path, message; or error key on failure.
        """
        result: Dict[str, Any] = {
            "success": False,
            "file_path": self.file_path,
            "message": "",
        }
        try:
            ok = self.database.mark_file_deleted(
                file_path=self.file_path,
                project_id=self.project_id,
                trash_dir=self.trash_dir,
                version_dir=self.version_dir,
            )
            result["success"] = ok
            result["message"] = (
                f"File marked as deleted and moved to trash: {self.file_path}"
                if ok
                else f"File not found in project: {self.file_path}"
            )
            if not ok:
                result["error"] = "FILE_NOT_FOUND"
        except Exception as e:
            logger.error("MarkFileDeletedCommand failed: %s", e, exc_info=True)
            result["error"] = str(e)
            result["message"] = str(e)
        return result
