"""
Register on-disk project files in the ``files`` table (shared by file watcher and transfer).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from code_analysis.core.database_driver_pkg.domain.files import add_file, get_file_by_path
from code_analysis.core.database_driver_pkg.domain.projects import get_project
from code_analysis.core.file_identity import (
    FILE_ROW_PATH_MATCH_SQL,
    file_row_path_match_values,
)
from code_analysis.core.fs_permissions import log_fs_access_error

logger = logging.getLogger(__name__)


def collect_content_metadata(content: str) -> Tuple[int, bool]:
    """Derive line count and docstring flag from in-memory file content."""
    lines = content.count("\n") + (1 if content else 0)
    stripped = content.lstrip()
    has_docstring = stripped.startswith('"""') or stripped.startswith("'''")
    return lines, has_docstring


def collect_file_disk_metadata(path: Path) -> Tuple[int, bool]:
    """Read line count and docstring flag from a regular file on disk."""
    if not path.exists() or not path.is_file():
        return 0, False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        log_fs_access_error(path, "collect_file_disk_metadata")
        logger.debug("Failed to read file for metadata: %s", path, exc_info=True)
        return 0, False
    return collect_content_metadata(text)


def register_file_row_for_new_content(
    database: Any,
    project_id: str,
    absolute_path: Path | str,
    content: str,
    *,
    last_modified: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Register a ``files`` row for a not-yet-written project file from its content.

    Unlike :func:`ensure_file_row_for_disk_path`, this does not require the path
    to exist on disk: it allocates ``files.id`` from in-memory ``content`` so the
    row can be created before the bytes are persisted (atomic
    lock-then-register-then-write). Returns the active row dict (with ``id``), or
    an existing row when the path is already registered, or ``None`` when the
    database client cannot register the row.

    Args:
        database: Database client with ``get_file_by_path`` and ``add_file``.
        project_id: Registered project UUID.
        absolute_path: Absolute filesystem path the file will be written to.
        content: The text content the file will hold (used for line/docstring
            metadata only).
        last_modified: Optional provisional mtime; defaults to the current time.
            The file watcher reconciles the real mtime on its next pass after the
            file is unlocked.
    """
    path = Path(absolute_path)
    try:
        path = path.resolve()
    except OSError:
        path = Path(absolute_path)

    pid = str(project_id).strip()
    abs_str = str(path)

    existing = get_file_by_path(database, abs_str, pid, include_deleted=False)
    if existing and existing.get("id") is not None:
        return dict(existing)

    mtime = last_modified if last_modified is not None else time.time()
    lines, has_docstring = collect_content_metadata(content)
    add_file(database, abs_str, lines, float(mtime), has_docstring, pid)
    fetched = get_file_by_path(database, abs_str, pid, include_deleted=False)
    return dict(fetched) if fetched else None


def ensure_file_row_for_disk_path(
    database: Any,
    project_id: str,
    absolute_path: Path | str,
    *,
    last_modified: Optional[float] = None,
    mark_needs_chunking: bool = False,
    tree_checksum: Optional[str] = None,
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
        tree_checksum: Optional source content checksum to persist on the row.
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

    existing = get_file_by_path(database, abs_str, pid, include_deleted=False)
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
        add_file(database, abs_str, lines, float(mtime), has_docstring, pid)
        fetched = get_file_by_path(database, abs_str, pid, include_deleted=False)
        row = dict(fetched) if fetched else None

    if not row or row.get("id") is None:
        return row

    if tree_checksum is not None:
        _persist_tree_checksum(database, row, tree_checksum)

    if mark_needs_chunking:
        _mark_file_needs_chunking(database, pid, path, row)

    return row


def _persist_tree_checksum(
    database: Any,
    row: Optional[Dict[str, Any]],
    tree_checksum: str,
) -> None:
    """Store the source checksum on one ``files`` row by id."""
    execute = getattr(database, "execute", None)
    if not callable(execute):
        return
    file_id = (row or {}).get("id")
    if file_id is not None:
        execute(
            "UPDATE files SET tree_checksum = ? WHERE id = ?", (tree_checksum, file_id)
        )


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
    project = get_project(database, project_id)
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
