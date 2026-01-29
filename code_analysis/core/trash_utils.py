"""
Utilities for project trash (recycle bin): name sanitization and path building.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


# Characters illegal or problematic in filenames (Windows + Unix)
_ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|]+')


def sanitize_project_name(name: str, project_id: str) -> str:
    """
    Sanitize project name for use in filesystem folder names.

    Replaces illegal characters by underscore, collapses multiple underscores,
    strips leading/trailing underscores and dots. If result is empty, returns
    fallback using first 8 chars of project_id.

    Args:
        name: Raw project name (e.g. from DB or root_path basename).
        project_id: Project UUID (used for fallback if name becomes empty).

    Returns:
        Sanitized string safe for folder name.
    """
    if not name or not isinstance(name, str):
        name = ""
    s = _ILLEGAL_CHARS.sub("_", name.strip())
    s = re.sub(r"_+", "_", s).strip("_. ")
    if not s:
        s = f"project_{project_id[:8]}" if project_id else "project_unknown"
    return s


def build_trash_folder_name(
    project_name: str, project_id: str, deleted_at_utc: datetime
) -> str:
    """
    Build trash folder name: {sanitized_name}_{YYYY-MM-DDThh-mm-ss}Z.

    Args:
        project_name: Project name (will be sanitized).
        project_id: Project UUID (for fallback if name empty).
        deleted_at_utc: Deletion time in UTC.

    Returns:
        Folder name string, e.g. MyProject_2025-01-29T14-30-00Z.
    """
    sanitized = sanitize_project_name(project_name, project_id)
    # ISO-like with colons replaced by hyphen for FS compatibility
    ts = deleted_at_utc.strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{sanitized}_{ts}"


def ensure_unique_trash_path(trash_dir: Path, base_name: str) -> Path:
    """
    Return a path under trash_dir that does not exist yet.

    If trash_dir / base_name exists, appends _1, _2, ... until unique.

    Args:
        trash_dir: Base trash directory.
        base_name: Desired folder name (e.g. from build_trash_folder_name).

    Returns:
        Path to a unique directory under trash_dir.
    """
    dest = trash_dir / base_name
    if not dest.exists():
        return dest
    suffix = 1
    while True:
        candidate = trash_dir / f"{base_name}_{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1
