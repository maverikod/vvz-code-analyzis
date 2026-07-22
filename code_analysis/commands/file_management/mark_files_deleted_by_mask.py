"""
Soft-delete all project files matching a path mask (recursive tree or glob).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from ...core.database.files.trash_standalone import mark_file_deleted_via_driver
from ...core.database_driver_pkg.domain.files import get_project_file_rows
from ...core.database_driver_pkg.domain.projects import get_project
from .path_mask_match import filter_rows_by_mask, relative_path_posix

# Driver-direct (stage 2): DatabaseClient class removed; "database" params
# below are duck-typed driver-shaped objects (PostgreSQLDriver in production).
# Kept as an Any alias so existing type annotations do not need per-site rewrites.
DatabaseClient = Any

logger = logging.getLogger(__name__)


class MarkFilesDeletedByMaskCommand:
    """
    For each indexed file in ``project_id`` whose path matches ``path_mask``,
    call :meth:`DatabaseClient.mark_file_deleted` (move to trash + DB soft-delete).

    Masks and file paths are interpreted relative to the project root (logical ``cwd`` =
    ``projects.root_path``), never the server process current directory; see
    :func:`~code_analysis.commands.file_management.path_mask_match.path_matches_mask`.
    """

    def __init__(
        self,
        database: "DatabaseClient",
        project_id: str,
        path_mask: str,
        trash_dir: Optional[str] = None,
        version_dir: Optional[str] = None,
    ) -> None:
        """Store database, project, mask, and optional trash/version directories."""
        self.database = database
        self.project_id = project_id
        self.path_mask = path_mask
        self.trash_dir = trash_dir
        self.version_dir = version_dir

    async def execute(self) -> Dict[str, Any]:
        """Mark all active project files matching the mask as deleted."""
        paths_list: List[str] = []
        errors_list: List[Dict[str, str]] = []
        result: Dict[str, Any] = {
            "success": True,
            "project_id": self.project_id,
            "path_mask": self.path_mask,
            "matched": 0,
            "moved_to_trash": 0,
            "failed": 0,
            "paths": paths_list,
            "errors": errors_list,
        }

        proj = get_project(self.database, self.project_id)
        if not proj:
            result["success"] = False
            errors_list.append(
                {
                    "code": "PROJECT_NOT_FOUND",
                    "message": f"Unknown project {self.project_id}",
                }
            )
            return result

        root_path = proj.root_path
        project_root = Path(str(root_path))
        rows = get_project_file_rows(
            self.database, self.project_id, include_deleted=False
        )
        matched = filter_rows_by_mask(rows, project_root, self.path_mask)
        result["matched"] = len(matched)

        matched_sorted = sorted(
            matched,
            key=lambda r: len(str(r.get("path", ""))),
            reverse=True,
        )

        for row in matched_sorted:
            abs_path = str(row.get("path", ""))
            try:
                rel = relative_path_posix(project_root, abs_path)
            except OSError:
                rel = Path(abs_path).name
            try:
                ok = mark_file_deleted_via_driver(
                    # cast: see TrashSqlDriver docstring (pre-flip DatabaseClient bridge).
                    cast(Any, self.database),
                    file_path=rel,
                    project_id=self.project_id,
                    trash_dir=self.trash_dir,
                    version_dir=self.version_dir,
                )
                if ok:
                    result["moved_to_trash"] += 1
                    paths_list.append(rel)
                else:
                    result["failed"] += 1
                    errors_list.append(
                        {
                            "path": rel,
                            "code": "NOT_FOUND",
                            "message": (
                                "mark_file_deleted returned false "
                                "(path not in DB or move failed)"
                            ),
                        }
                    )
            except Exception as e:
                result["failed"] += 1
                logger.error(
                    "mark_files_deleted_by_mask: %s: %s", rel, e, exc_info=True
                )
                errors_list.append({"path": rel, "code": "ERROR", "message": str(e)})

        if result["matched"] == 0:
            result["success"] = True
        else:
            result["success"] = result["failed"] == 0

        return result
