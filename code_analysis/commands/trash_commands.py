"""
Internal commands for project trash (list, permanently delete, clear).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

# Regex for trash folder name: {original_name}_{YYYY-MM-DDThh-mm-ss}Z
_TRASH_FOLDER_PATTERN = re.compile(r"^(.+)_(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)$")


def _parse_trash_folder_name(folder_name: str) -> tuple[str, Optional[str]]:
    """
    Parse trash folder name into original_name and deleted_at (ISO string or None).

    Returns:
        (original_name, deleted_at_iso_or_none)
    """
    m = _TRASH_FOLDER_PATTERN.match(folder_name)
    if m:
        original = m.group(1)
        ts = m.group(2)
        # Normalize back to ISO with colons for display: 2025-01-29T14-30-00Z
        return (original, ts)
    return (folder_name, None)


class ListTrashedProjectsCommand:
    """
    List projects that have been moved to trash (recycle bin).

    Lists direct children of trash_dir that are directories; parses folder
    names to extract original_name and deleted_at when they match the standard
    format.
    """

    def __init__(self, trash_dir: str):
        """
        Initialize list trashed projects command.

        Args:
            trash_dir: Path to trash directory (e.g. from StoragePaths).
        """
        self.trash_dir = Path(trash_dir).resolve()

    def execute(self) -> Dict[str, Any]:
        """
        List trashed project folders.

        Returns:
            Dict with success, items: [{ folder_name, original_name, deleted_at, path }].
        """
        if not self.trash_dir.exists():
            return {"success": True, "items": [], "trash_dir": str(self.trash_dir)}

        items: List[Dict[str, Any]] = []
        try:
            for child in sorted(self.trash_dir.iterdir()):
                if not child.is_dir():
                    continue
                folder_name = child.name
                original_name, deleted_at = _parse_trash_folder_name(folder_name)
                items.append(
                    {
                        "folder_name": folder_name,
                        "original_name": original_name,
                        "deleted_at": deleted_at,
                        "path": str(child),
                    }
                )
        except OSError as e:
            return {
                "success": False,
                "error": "LIST_TRASH_ERROR",
                "message": str(e),
                "trash_dir": str(self.trash_dir),
            }

        return {
            "success": True,
            "items": items,
            "trash_dir": str(self.trash_dir),
            "count": len(items),
        }


class PermanentlyDeleteFromTrashCommand:
    """
    Permanently delete one trashed project folder from trash.

    Validates that the target path is under trash_dir (no path escape).
    """

    def __init__(self, trash_dir: str, trash_folder_name: str):
        """
        Initialize permanently delete from trash command.

        Args:
            trash_dir: Path to trash directory.
            trash_folder_name: Name of the folder to delete (direct child of trash_dir).
        """
        self.trash_dir = Path(trash_dir).resolve()
        self.trash_folder_name = trash_folder_name

    def execute(self) -> Dict[str, Any]:
        """
        Permanently remove the trashed folder.

        Returns:
            Dict with success or error.
        """
        if (
            "/" in self.trash_folder_name
            or "\\" in self.trash_folder_name
            or ".." in self.trash_folder_name
        ):
            return {
                "success": False,
                "error": "INVALID_PATH",
                "message": "Folder name must not contain path separators or '..'.",
                "trash_folder_name": self.trash_folder_name,
            }
        target = (self.trash_dir / self.trash_folder_name).resolve()
        if target.parent != self.trash_dir.resolve():
            return {
                "success": False,
                "error": "INVALID_PATH",
                "message": "Folder name must be a direct child of trash_dir (path escape not allowed).",
                "trash_folder_name": self.trash_folder_name,
            }
        if not target.exists():
            return {
                "success": False,
                "error": "NOT_FOUND",
                "message": f"Trashed folder not found: {target}",
                "trash_folder_name": self.trash_folder_name,
            }
        if not target.is_dir():
            return {
                "success": False,
                "error": "NOT_DIRECTORY",
                "message": f"Path is not a directory: {target}",
                "trash_folder_name": self.trash_folder_name,
            }
        try:
            shutil.rmtree(target)
            return {
                "success": True,
                "message": f"Permanently deleted from trash: {self.trash_folder_name}",
                "trash_folder_name": self.trash_folder_name,
            }
        except OSError as e:
            return {
                "success": False,
                "error": "DELETE_ERROR",
                "message": str(e),
                "trash_folder_name": self.trash_folder_name,
            }


class ClearTrashCommand:
    """
    Permanently delete all contents of the trash directory.

    Optionally dry_run to only report what would be removed.
    """

    def __init__(self, trash_dir: str, dry_run: bool = False):
        """
        Initialize clear trash command.

        Args:
            trash_dir: Path to trash directory.
            dry_run: If True, only list what would be removed; do not delete.
        """
        self.trash_dir = Path(trash_dir).resolve()
        self.dry_run = dry_run

    def execute(self) -> Dict[str, Any]:
        """
        Remove all direct child directories of trash_dir.

        Returns:
            Dict with success, removed_count, removed (list of folder names).
        """
        if not self.trash_dir.exists():
            return {
                "success": True,
                "removed_count": 0,
                "removed": [],
                "dry_run": self.dry_run,
                "trash_dir": str(self.trash_dir),
            }

        removed: List[str] = []
        errors: List[str] = []
        try:
            for child in list(self.trash_dir.iterdir()):
                if not child.is_dir():
                    continue
                name = child.name
                removed.append(name)
                if not self.dry_run:
                    try:
                        shutil.rmtree(child)
                    except OSError as e:
                        errors.append(f"{name}: {e}")
        except OSError as e:
            return {
                "success": False,
                "error": "CLEAR_TRASH_ERROR",
                "message": str(e),
                "trash_dir": str(self.trash_dir),
            }

        return {
            "success": len(errors) == 0,
            "removed_count": len(removed),
            "removed": removed,
            "dry_run": self.dry_run,
            "trash_dir": str(self.trash_dir),
            "errors": errors if errors else None,
        }
