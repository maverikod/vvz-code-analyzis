"""
Command to clean up deleted files from database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING, cast

from ...core.database.files.trash_standalone import (
    get_deleted_files_via_driver,
    hard_delete_file_via_driver,
)

if TYPE_CHECKING:
    from ...core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


class CleanupDeletedFilesCommand:
    """
    Command to clean up deleted files from database.

    Options:
    - project_id: Specific project (optional, all projects if not specified)
    - dry_run: Show what would be deleted without actually deleting
    - older_than_days: Only delete files deleted more than N days ago
    - hard_delete: Permanently delete (removes all data, chunks, FAISS vectors)

    Hard delete removes:
    - File record
    - Physical file from version directory
    - All chunks (and removes from FAISS index)
    - All classes, functions, methods
    - All AST trees
    - All vector indexes

    Use with caution - cannot be recovered.
    """

    def __init__(
        self,
        database: DatabaseClient,
        project_id: Optional[str] = None,
        dry_run: bool = False,
        older_than_days: Optional[int] = None,
        hard_delete: bool = False,
    ):
        """
        Initialize cleanup command.

        Args:
            database: DatabaseClient instance
            project_id: Optional project ID (all projects if None)
            dry_run: If True, only show what would be deleted
            older_than_days: Only delete files deleted more than N days ago
            hard_delete: If True, permanently delete (default: False, just list)
        """
        self.database = database
        self.project_id = project_id
        self.dry_run = dry_run
        self.older_than_days = older_than_days
        self.hard_delete = hard_delete

    async def execute(self) -> Dict[str, Any]:
        """
        Execute cleanup command.

        Returns:
            Dictionary with cleanup statistics
        """
        result: Dict[str, Any] = {
            "deleted_files": [],
            "total_files": 0,
            "total_size": 0,
            "dry_run": self.dry_run,
            "hard_delete": self.hard_delete,
        }

        try:
            # Get deleted files
            # cast: see TrashSqlDriver docstring (pre-flip DatabaseClient bridge).
            if self.project_id:
                deleted_files = get_deleted_files_via_driver(
                    cast(Any, self.database), self.project_id
                )
            else:
                # Get all projects and their deleted files
                projects_result = cast(
                    Dict[str, Any],
                    self.database.execute("SELECT id FROM projects"),
                )
                projects = projects_result.get("data", [])
                deleted_files = []
                for project_row in projects:
                    project_id = project_row["id"]
                    deleted_files.extend(
                        get_deleted_files_via_driver(cast(Any, self.database), project_id)
                    )

            # Filter by age if specified
            if self.older_than_days:
                cutoff_time = time.time() - (self.older_than_days * 24 * 3600)
                deleted_files = [
                    f for f in deleted_files if f.get("updated_at", 0) < cutoff_time
                ]

            result["total_files"] = len(deleted_files)

            if self.dry_run:
                # Just collect information
                for file_info in deleted_files:
                    file_id = file_info["id"]
                    file_path = file_info.get("path", "unknown")
                    version_dir = file_info.get("version_dir")
                    deleted_at = file_info.get("updated_at", 0)

                    file_size = 0
                    if version_dir and file_path:
                        try:
                            file_path_obj = Path(file_path)
                            if file_path_obj.exists():
                                file_size = file_path_obj.stat().st_size
                        except Exception:
                            pass

                    result["deleted_files"].append(
                        {
                            "id": file_id,
                            "path": file_path,
                            "version_dir": version_dir,
                            "deleted_at": deleted_at,
                            "size": file_size,
                        }
                    )
                    result["total_size"] += file_size

                result["message"] = (
                    f"Would delete {result['total_files']} files "
                    f"({result['total_size']} bytes)"
                )
            elif self.hard_delete:
                # Actually delete files
                for file_info in deleted_files:
                    file_id = file_info["id"]
                    file_path = file_info.get("path", "unknown")
                    version_dir = file_info.get("version_dir")

                    try:
                        # Hard delete removes physical file and all DB data
                        # (cast: see TrashSqlDriver docstring, pre-flip bridge).
                        hard_delete_file_via_driver(cast(Any, self.database), file_id)
                        result["deleted_files"].append(
                            {"id": file_id, "path": file_path, "deleted": True}
                        )
                        logger.info(f"Hard deleted file ID {file_id}: {file_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete file ID {file_id}: {e}")
                        result["deleted_files"].append(
                            {
                                "id": file_id,
                                "path": file_path,
                                "deleted": False,
                                "error": str(e),
                            }
                        )

                result["message"] = f"Deleted {result['total_files']} files"
            else:
                # Just list files
                for file_info in deleted_files:
                    result["deleted_files"].append(
                        {
                            "id": file_info["id"],
                            "path": file_info.get("path", "unknown"),
                            "version_dir": file_info.get("version_dir"),
                            "deleted_at": file_info.get("updated_at", 0),
                        }
                    )

                result["message"] = f"Found {result['total_files']} deleted files"

        except Exception as e:
            logger.error(f"Error in cleanup command: {e}", exc_info=True)
            result["error"] = str(e)

        return result
