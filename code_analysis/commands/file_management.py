"""
Internal commands for file management (cleanup, unmark, collapse versions).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase
else:
    CodeDatabase = Any

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
        database: CodeDatabase,
        project_id: Optional[str] = None,
        dry_run: bool = False,
        older_than_days: Optional[int] = None,
        hard_delete: bool = False,
    ):
        """
        Initialize cleanup command.

        Args:
            database: CodeDatabase instance
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
        import time

        result = {
            "deleted_files": [],
            "total_files": 0,
            "total_size": 0,
            "dry_run": self.dry_run,
            "hard_delete": self.hard_delete,
        }

        try:
            # Get deleted files
            if self.project_id:
                deleted_files = self.database.get_deleted_files(self.project_id)
            else:
                # Get all projects and their deleted files
                cursor = self.database.conn.cursor()
                cursor.execute("SELECT id FROM projects")
                projects = cursor.fetchall()
                deleted_files = []
                for project_row in projects:
                    project_id = project_row[0]
                    deleted_files.extend(self.database.get_deleted_files(project_id))

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
                        self.database.hard_delete_file(file_id)
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
        database: "CodeDatabase",
        file_path: str,
        project_id: str,
        dry_run: bool = False,
    ):
        """
        Initialize unmark command.

        Args:
            database: CodeDatabase instance
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
            cursor = self.database.conn.cursor()
            cursor.execute(
                """
                SELECT id, path, original_path, version_dir 
                FROM files 
                WHERE project_id = ? AND (path = ? OR original_path = ?)
                ORDER BY last_modified DESC
                LIMIT 1
                """,
                (self.project_id, self.file_path, self.file_path),
            )
            row = cursor.fetchone()

            if not row:
                result["error"] = f"File not found: {self.file_path}"
                return result

            file_id, current_path, original_path, version_dir = (
                row[0],
                row[1],
                row[2],
                row[3],
            )

            result["original_path"] = original_path
            result["version_dir"] = version_dir

            if not original_path:
                result["error"] = "File has no original_path, cannot restore"
                return result

            if self.dry_run:
                result["message"] = (
                    f"Would restore file from {current_path} to {original_path}"
                )
                result["restored"] = True  # Would be restored
            else:
                # Actually restore
                success = self.database.unmark_file_deleted(
                    self.file_path, self.project_id
                )
                result["restored"] = success
                if success:
                    result["message"] = f"Restored file to {original_path}"
                else:
                    result["error"] = "Failed to restore file"

        except Exception as e:
            logger.error(f"Error in unmark command: {e}", exc_info=True)
            result["error"] = str(e)

        return result


class CollapseVersionsCommand:
    """
    Command to collapse file versions, keeping only latest by last_modified.

    Finds all records with same path but different last_modified.
    Keeps the one with latest last_modified, deletes others (hard delete).

    Options:
    - project_id: Project ID
    - keep_latest: If True, keep latest version (default: True)
    - dry_run: Show what would be collapsed without actually collapsing
    """

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        keep_latest: bool = True,
        dry_run: bool = False,
    ):
        """
        Initialize collapse command.

        Args:
            database: CodeDatabase instance
            project_id: Project ID
            keep_latest: If True, keep latest version (default: True)
            dry_run: If True, only show what would be collapsed
        """
        self.database = database
        self.project_id = project_id
        self.keep_latest = keep_latest
        self.dry_run = dry_run

    async def execute(self) -> Dict[str, Any]:
        """
        Execute collapse command.

        Returns:
            Dictionary with collapse statistics
        """
        result = {
            "kept_count": 0,
            "deleted_count": 0,
            "collapsed_files": [],
            "dry_run": self.dry_run,
        }

        try:
            if self.dry_run:
                # Just analyze, don't delete
                cursor = self.database.conn.cursor()
                cursor.execute(
                    """
                    SELECT path, COUNT(*) as version_count
                    FROM files
                    WHERE project_id = ?
                    GROUP BY path
                    HAVING COUNT(*) > 1
                    """,
                    (self.project_id,),
                )
                files_with_versions = cursor.fetchall()

                for path_row in files_with_versions:
                    file_path = path_row[0]
                    version_count = path_row[1]

                    # Get all versions
                    versions = self.database.get_file_versions(
                        file_path, self.project_id
                    )

                    if self.keep_latest:
                        keep_version = versions[0]  # Latest
                        delete_versions = versions[1:]
                    else:
                        keep_version = versions[-1]  # Oldest
                        delete_versions = versions[:-1]

                    result["collapsed_files"].append(
                        {
                            "path": file_path,
                            "version_count": version_count,
                            "keep": {
                                "id": keep_version["id"],
                                "last_modified": keep_version.get("last_modified"),
                            },
                            "delete": [
                                {"id": v["id"], "last_modified": v.get("last_modified")}
                                for v in delete_versions
                            ],
                        }
                    )
                    result["kept_count"] += 1
                    result["deleted_count"] += len(delete_versions)

                result["message"] = (
                    f"Would collapse {len(result['collapsed_files'])} files: "
                    f"keep {result['kept_count']}, delete {result['deleted_count']}"
                )
            else:
                # Actually collapse
                collapse_result = self.database.collapse_file_versions(
                    self.project_id, self.keep_latest
                )
                result.update(collapse_result)
                result["message"] = (
                    f"Collapsed {len(result['collapsed_files'])} files: "
                    f"kept {result['kept_count']}, deleted {result['deleted_count']}"
                )

        except Exception as e:
            logger.error(f"Error in collapse command: {e}", exc_info=True)
            result["error"] = str(e)

        return result
