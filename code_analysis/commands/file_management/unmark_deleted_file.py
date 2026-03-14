"""
Command to unmark file as deleted (recovery).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from ...core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


class UnmarkDeletedFileCommand:
    """
    Command to unmark file as deleted (recovery).

    Process:
    1. Finds file in version directory (by path or original_path)
    2. Moves file back to original_path
    3. Clears deleted flag, original_path, version_dir
    4. File will be processed again

    Options:
    - file_path: File path (current path in version_dir or original_path)
    - project_id: Project ID
    - dry_run: Show what would be restored without actually restoring
    """

    def __init__(
        self,
        database: "DatabaseClient",
        file_path: str,
        project_id: str,
        dry_run: bool = False,
    ):
        """
        Initialize unmark command.

        Args:
            database: DatabaseClient instance
            file_path: File path (current in version_dir or original_path)
            project_id: Project ID
            dry_run: If True, only show what would be restored
        """
        self.database = database
        self.file_path = file_path
        self.project_id = project_id
        self.dry_run = dry_run

    async def execute(self) -> Dict[str, Any]:
        """
        Execute unmark command.

        Returns:
            Dictionary with restoration information
        """
        result = {
            "restored": False,
            "file_path": self.file_path,
            "original_path": None,
            "version_dir": None,
            "dry_run": self.dry_run,
        }

        try:
            # Get file info
            response = cast(
                Dict[str, Any],
                self.database.execute(
                    """
                    SELECT id, path, original_path, version_dir 
                    FROM files 
                    WHERE project_id = ? AND (path = ? OR original_path = ?)
                    ORDER BY last_modified DESC
                    LIMIT 1
                    """,
                    (self.project_id, self.file_path, self.file_path),
                ),
            )
            data = response.get("data", [])
            row = data[0] if data else None

            if not row:
                result["error"] = f"File not found: {self.file_path}"
                return result

            current_path = row["path"]
            original_path = row["original_path"]
            version_dir = row["version_dir"]

            result["original_path"] = original_path
            result["version_dir"] = version_dir

            if not original_path:
                result["error"] = "File has no original_path, cannot restore"
                return result

            # Pre-check: do not overwrite existing file (FILE_TRASH_SPEC Req. 2)
            original_path_obj = Path(original_path)
            if original_path_obj.exists():
                result["error"] = "FILE_EXISTS_AT_TARGET"
                result["message"] = (
                    f"File already exists at {original_path}. "
                    "Delete or rename it before restoring."
                )
                return result

            if self.dry_run:
                result["message"] = (
                    f"Would restore file from {current_path} to {original_path}"
                )
                result["restored"] = True  # Would be restored
            else:
                success = self.database.unmark_file_deleted(
                    self.file_path, self.project_id
                )
                result["restored"] = success
                if success:
                    result["message"] = f"Restored file to {original_path}"
                else:
                    result["error"] = "RESTORE_FAILED"
                    result["message"] = "Failed to restore file"

        except Exception as e:
            logger.error(f"Error in unmark command: {e}", exc_info=True)
            result["error"] = str(e)

        return result
