"""
Command to mark a file as deleted (soft delete) and move to file trash.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from ...core.database_driver_pkg.domain.files import add_file, get_file_by_path
from ...core.database_driver_pkg.domain.projects import get_project

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

    @staticmethod
    def _project_root_from_record(project: Any) -> Optional[Path]:
        """Extract project root path from DB row/object."""
        if not project:
            return None
        root_path = (
            project.get("root_path")
            if isinstance(project, dict)
            else getattr(project, "root_path", None)
        )
        if not root_path:
            return None
        return Path(str(root_path)).resolve()

    @staticmethod
    def _line_count_for_file(path: Path) -> int:
        """Best-effort line count for DB row creation."""
        try:
            with path.open("rb") as f:
                data = f.read()
            if not data:
                return 0
            return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)
        except Exception:
            return 0

    def _normalize_relative_file_path(self, project_root: Path) -> Optional[str]:
        """Validate request path and return normalized project-relative POSIX path."""
        raw_path = (self.file_path or "").strip()
        if not raw_path:
            return None
        rel_path = Path(raw_path)
        if rel_path.is_absolute():
            return None
        if any(part == ".." for part in rel_path.parts):
            return None
        if rel_path.name in {"", ".", ".."}:
            return None

        abs_path = (project_root / rel_path).resolve()
        try:
            abs_path.relative_to(project_root)
        except ValueError:
            return None
        return abs_path.relative_to(project_root).as_posix()

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
            "db_lookup_found": False,
            "fs_fallback_used": False,
            "file_existed_on_disk": False,
            "db_row_created": False,
            "deleted": False,
            "moved_to_trash": False,
        }
        try:
            project = get_project(self.database, self.project_id)
            project_root = self._project_root_from_record(project)
            if project_root is None:
                result["error"] = "PROJECT_NOT_FOUND"
                result["message"] = f"Project not found: {self.project_id}"
                return result

            relative_file_path = self._normalize_relative_file_path(project_root)
            if relative_file_path is None:
                result["error"] = "INVALID_FILE_PATH"
                result["message"] = (
                    "file_path must be a non-empty project-relative file path "
                    "without absolute paths or traversal."
                )
                return result

            absolute_path = (project_root / relative_file_path).resolve()
            result["file_path"] = relative_file_path

            existing_row = get_file_by_path(
                self.database, str(absolute_path), self.project_id, include_deleted=True
            )
            result["db_lookup_found"] = bool(existing_row)

            if not existing_row:
                result["fs_fallback_used"] = True
                if absolute_path.exists() and absolute_path.is_file():
                    result["file_existed_on_disk"] = True
                    file_id = add_file(
                        self.database,
                        path=str(absolute_path),
                        lines=self._line_count_for_file(absolute_path),
                        last_modified=absolute_path.stat().st_mtime,
                        has_docstring=False,
                        project_id=self.project_id,
                    )
                    result["db_row_created"] = bool(file_id)
                elif absolute_path.exists():
                    result["error"] = "PATH_IS_DIRECTORY"
                    result["message"] = f"Path is not a file: {relative_file_path}"
                    return result
                else:
                    result["error"] = "FILE_NOT_FOUND"
                    result["message"] = (
                        f"File not found in project and on disk: {relative_file_path}"
                    )
                    return result
            else:
                result["file_existed_on_disk"] = bool(
                    absolute_path.exists() and absolute_path.is_file()
                )

            ok = self.database.mark_file_deleted(
                file_path=relative_file_path,
                project_id=self.project_id,
                trash_dir=self.trash_dir,
                version_dir=self.version_dir,
            )
            result["success"] = ok
            result["deleted"] = ok
            result["moved_to_trash"] = ok
            result["message"] = (
                f"File marked as deleted and moved to trash: {relative_file_path}"
                if ok
                else f"Failed to move file to trash: {relative_file_path}"
            )
            if not ok:
                result["error"] = "DELETE_FAILED"
        except Exception as e:
            logger.error("MarkFileDeletedCommand failed: %s", e, exc_info=True)
            result["error"] = str(e)
            result["message"] = str(e)
        return result
