"""
MCP command wrappers for file management operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, cast

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ...core.database.files.trash_standalone import get_deleted_files_via_driver
from ..base_mcp_command import BaseMCPCommand
from ..file_management.relative_path_list_pattern import (
    canonical_relative_path,
    effective_listing_pattern,
    relative_path_matches_listing_pattern,
)

logger = logging.getLogger(__name__)


def _deleted_entry_rel_posix(project_root: Path, item: Dict[str, Any]) -> str | None:
    """Project-relative posix path for pattern matching (prefer ``original_path``)."""
    op = item.get("original_path")
    if op:
        p = Path(str(op))
        if p.is_absolute():
            return canonical_relative_path(project_root, p)
        return Path(str(op)).as_posix()
    raw = item.get("path")
    if not raw:
        return None
    return canonical_relative_path(project_root, Path(str(raw)))


class ListDeletedFilesMCPCommand(BaseMCPCommand):
    """List deleted files for a project (path in trash, original_path, in_trash)."""

    name = "list_deleted_files"
    version = "1.0.0"
    descr = (
        "List deleted files for a project (trash path, original_path). Optional "
        "``file_pattern`` / ``glob`` filter on project-relative paths (fnmatch / prefix, "
        "same as list_project_files)."
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
                "file_pattern": {
                    "type": "string",
                    "description": (
                        "Optional fnmatch on resolved project-relative path (prefers "
                        "``original_path``; falls back to ``path``). ``glob`` is an alias."
                    ),
                },
                "glob": {
                    "type": "string",
                    "description": (
                        "Alias of ``file_pattern``; non-empty ``file_pattern`` wins when both set."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_pattern: Optional[str] = None,
        glob: Optional[str] = None,
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
            root = self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)
            try:
                # cast: see TrashSqlDriver docstring (pre-flip DatabaseClient bridge).
                rows = get_deleted_files_via_driver(cast(Any, database), project_id)
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
                eff = effective_listing_pattern(file_pattern, glob)
                if eff:
                    filtered = []
                    for it in items:
                        rel = _deleted_entry_rel_posix(root, it)
                        if rel is None:
                            continue
                        if relative_path_matches_listing_pattern(rel, eff):
                            filtered.append(it)
                    items = filtered
                return SuccessResult(data={"deleted_files": items, "total": len(items)})
            finally:
                database.disconnect()
        except Exception as e:
            return self._handle_error(
                e, "LIST_DELETED_FILES_ERROR", "list_deleted_files"
            )
