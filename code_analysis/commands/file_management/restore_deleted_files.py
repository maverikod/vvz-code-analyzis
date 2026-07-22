"""
Batch restore of multiple deleted files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, TYPE_CHECKING

from ...core.database_driver_pkg.domain.projects import get_project
from ...core.sql_portable import WHERE_FILES_TRASHED

if TYPE_CHECKING:
    from ...core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


class RestoreDeletedFilesCommand:
    """
    Restore multiple deleted files in one operation (batch restore).

    Pre-check: if any target path (original_path) already exists in the project
    folder, the whole operation is cancelled and an error is returned with the
    list of conflicting paths (FILE_TRASH_SPEC Req. 6). No partial restore.

    Options:
    - project_id: Project ID
    - file_paths: List of file paths (current path in trash or original_path)
    - dry_run: If True, only run pre-check and return what would be restored
    """

    def __init__(
        self,
        database: "DatabaseClient",
        project_id: str,
        file_paths: List[str],
        dry_run: bool = False,
    ):
        """
        Initialize batch restore command.

        Args:
            database: DatabaseClient instance
            project_id: Project ID
            file_paths: List of paths (trash path or original_path) to restore
            dry_run: If True, only pre-check and report
        """
        self.database = database
        self.project_id = project_id
        self.file_paths = file_paths
        self.dry_run = dry_run

    async def execute(self) -> Dict[str, Any]:
        """
        Execute batch restore.

        Returns:
            Dict with restored paths, or error with TARGET_FILE_EXISTS and conflicting_paths
        """
        result: Dict[str, Any] = {
            "restored_paths": [],
            "success": False,
            "dry_run": self.dry_run,
        }

        try:
            project = get_project(self.database, self.project_id)
            root_path = None
            if project:
                root_path = (
                    project.get("root_path")
                    if isinstance(project, dict)
                    else getattr(project, "root_path", None)
                )
            project_root = Path(root_path).resolve() if root_path else None

            # Step 1: resolve each file_path to file record (id, original_path)
            resolved: List[Dict[str, Any]] = []
            for file_path in self.file_paths:
                candidate = Path(file_path)
                abs_file_path = (
                    str((project_root / candidate).resolve())
                    if project_root and not candidate.is_absolute()
                    else str(candidate.resolve()) if candidate.is_absolute() else file_path
                )
                row_result = self.database.execute(
                    f"""
                    SELECT id, path, original_path
                    FROM files
                    WHERE project_id = ? AND (path = ? OR original_path = ?) AND {WHERE_FILES_TRASHED}
                    ORDER BY last_modified DESC
                    LIMIT 1
                    """,
                    (self.project_id, file_path, file_path),
                )
                data = row_result.get("data", [])
                row = data[0] if data else None
                if not row and abs_file_path != file_path:
                    row_result = self.database.execute(
                        f"""
                        SELECT id, path, original_path
                        FROM files
                        WHERE project_id = ? AND (path = ? OR original_path = ?) AND {WHERE_FILES_TRASHED}
                        ORDER BY last_modified DESC
                        LIMIT 1
                        """,
                        (self.project_id, abs_file_path, abs_file_path),
                    )
                data = row_result.get("data", [])
                row = data[0] if data else None
                if not row or not row.get("original_path"):
                    result["error"] = f"File not found or not deleted: {file_path}"
                    return result
                resolved.append(
                    {
                        "file_path": file_path,
                        "file_id": row["id"],
                        "original_path": row["original_path"],
                    }
                )

            # Step 2: pre-check all original_paths; if any exists, abort
            conflicting: List[str] = []
            for item in resolved:
                if Path(item["original_path"]).exists():
                    conflicting.append(item["original_path"])
            if conflicting:
                result["success"] = False
                result["error"] = "TARGET_FILE_EXISTS"
                result["conflicting_paths"] = conflicting
                result["message"] = (
                    "One or more target paths already exist in the project. "
                    "Delete or rename them before restoring."
                )
                return result

            if self.dry_run:
                result["would_restore"] = [r["original_path"] for r in resolved]
                result["success"] = True
                result["message"] = (
                    f"Dry run: {len(resolved)} file(s) would be restored"
                )
                return result

            # Step 3: restore each file; all-or-nothing (abort on first failure)
            for item in resolved:
                success = self.database.unmark_file_deleted(
                    item["file_path"], self.project_id
                )
                if not success:
                    result["error"] = "RESTORE_FAILED"
                    result["message"] = f"Failed to restore {item['original_path']}"
                    result["restored_paths"] = []  # rollback not implemented
                    return result
                result["restored_paths"].append(item["original_path"])

            result["success"] = True
            result["message"] = f"Restored {len(result['restored_paths'])} file(s)"

        except Exception as e:
            logger.error(f"Error in RestoreDeletedFilesCommand: {e}", exc_info=True)
            result["error"] = str(e)

        return result
