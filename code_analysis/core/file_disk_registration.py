"""
Register on-disk project files in the ``files`` table (shared by file watcher and transfer).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from code_analysis.core.file_identity import (
    FILE_ROW_PATH_MATCH_SQL,
    file_row_path_match_values,
)

logger = logging.getLogger(__name__)


def collect_file_disk_metadata(path: Path) -> Tuple[int, bool]:
    """Read line count and docstring flag from a regular file on disk."""
    lines = 0
    has_docstring = False
    if not path.exists() or not path.is_file():
        return lines, has_docstring
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.count("\n") + (1 if text else 0)
        stripped = text.lstrip()
        has_docstring = stripped.startswith('"""') or stripped.startswith("'''")
    except Exception:
        logger.debug("Failed to read file for metadata: %s", path, exc_info=True)
    return lines, has_docstring


def ensure_file_row_for_disk_path(
    database: Any,
    project_id: str,
    absolute_path: Path | str,
    *,
    last_modified: Optional[float] = None,
    mark_needs_chunking: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Ensure a ``files`` row exists for an on-disk project file.

    Uses ``database.add_file`` when the row is missing. Returns the active row
    dict (with ``id``) or ``None`` when the path is not a regular file.

    Args:
        database: Database client with ``get_file_by_path`` and ``add_file``.
        project_id: Registered project UUID.
        absolute_path: Absolute filesystem path to the file.
        last_modified: Optional mtime; when omitted, taken from ``stat``.
        mark_needs_chunking: When True, set ``needs_chunking = 1`` (file watcher).
    """
    path = Path(absolute_path)
    try:
        path = path.resolve()
    except OSError:
        path = Path(absolute_path)
    if not path.is_file():
        return None

    pid = str(project_id).strip()
    abs_str = str(path)
    get_by_path = getattr(database, "get_file_by_path", None)
    if not callable(get_by_path):
        logger.warning("database has no get_file_by_path; skip register %s", abs_str)
        return None

    existing = get_by_path(abs_str, pid, include_deleted=False)
    if existing and existing.get("id") is not None:
        row: Optional[Dict[str, Any]] = dict(existing)
    else:
        mtime = last_modified
        if mtime is None:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
        lines, has_docstring = collect_file_disk_metadata(path)
        add_file = getattr(database, "add_file", None)
        if not callable(add_file):
            logger.warning("database has no add_file; skip register %s", abs_str)
            return None
        add_file(abs_str, lines, float(mtime), has_docstring, pid)
        fetched = get_by_path(abs_str, pid, include_deleted=False)
        row = dict(fetched) if fetched else None

    if not row or row.get("id") is None:
        return row

    if mark_needs_chunking:
        _mark_file_needs_chunking(database, pid, path, row)

    return row


def _mark_file_needs_chunking(
    database: Any,
    project_id: str,
    absolute_path: Path,
    row: Optional[Dict[str, Any]] = None,
) -> None:
    """Set ``needs_chunking = 1`` for one file row (file watcher indexing queue)."""
    execute = getattr(database, "execute", None)
    if not callable(execute):
        return
    file_id = (row or {}).get("id")
    if file_id is not None:
        execute("UPDATE files SET needs_chunking = 1 WHERE id = ?", (file_id,))
        return
    project = None
    get_project = getattr(database, "get_project", None)
    if callable(get_project):
        project = get_project(project_id)
    root = getattr(project, "root_path", None) if project is not None else None
    if isinstance(project, dict):
        root = project.get("root_path")
    if not root:
        return
    try:
        r1, r2, r3 = file_row_path_match_values(
            project_root=Path(root).resolve(),
            absolute_path=str(absolute_path),
        )
    except ValueError:
        return
    execute(
        f"UPDATE files SET needs_chunking = 1 WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL}",
        (project_id, r1, r2, r3),
    )
