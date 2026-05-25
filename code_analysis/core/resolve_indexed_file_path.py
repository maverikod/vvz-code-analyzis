"""
Resolve absolute filesystem paths for indexed files using DB fields only.

Layout (when watcher fills watch_dir_paths and project.name):
  watch_dir_paths.absolute_path / projects.name / files.relative_path

Fallbacks: projects.root_path / relative_path, then legacy files.path.

Public API
----------
resolve_indexed_file_path(file_row)
    Probe candidates in order; return first Path that exists as a regular file.

build_file_path_candidates(file_row)
    Return ordered list of Path candidates WITHOUT probing disk.
    Use when the file may not exist yet (trash, backup, write operations).

resolve_file_path_from_parts(...)
    Same logic but accepts explicit keyword arguments instead of a mapping.
    Use in driver/handler code that has individual fields, not a full row.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Mapping, Optional

logger = logging.getLogger(__name__)


def _normalize_relative_key(rel: str) -> str:
    s = (rel or "").strip().replace("\\", "/")
    while s.startswith("/"):
        s = s[1:]
    return s


def _first_existing_file(*candidates: Path) -> Optional[Path]:
    seen: set[str] = set()
    for raw in candidates:
        if raw is None:
            continue
        try:
            resolved = raw.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            return resolved
    return None


def resolve_indexed_file_path(file_row: Mapping[str, Any]) -> Optional[Path]:
    """
    Recompute absolute path from a file row (include joined project/watch columns).

    Tries, in order, the first path that exists and is a regular file:
    1. watch_absolute_path / project_name / relative_path
    2. project_root_path / relative_path
    3. files.path (stored absolute path at index time)

    Args:
        file_row: Dict-like row with id, path, optional relative_path, watch_absolute_path,
            project_name, project_root_path.

    Returns:
        Resolved Path, or None if no candidate exists on disk.
    """
    rel = _normalize_relative_key(str(file_row.get("relative_path") or ""))

    watch_abs = file_row.get("watch_absolute_path")
    proj_name = file_row.get("project_name")
    root_path = file_row.get("project_root_path")
    stored = file_row.get("path")

    candidates: list[Path] = []
    if watch_abs and proj_name and rel:
        candidates.append(Path(str(watch_abs)) / str(proj_name) / rel)
    if root_path and rel:
        candidates.append(Path(str(root_path)) / rel)
    if stored:
        candidates.append(Path(str(stored)))

    hit = _first_existing_file(*candidates)
    if hit is None:
        logger.debug(
            "resolve_indexed_file_path: no file on disk for file_id=%s "
            "(had watch+name+rel=%s root+rel=%s stored=%s)",
            file_row.get("id"),
            bool(watch_abs and proj_name and rel),
            bool(root_path and rel),
            bool(stored),
        )
    return hit


def build_file_path_candidates(file_row: Mapping[str, Any]) -> List[Path]:
    """Return ordered Path candidates for a file row WITHOUT probing disk.

    Candidates in priority order:
      1. watch_absolute_path / project_name / relative_path
      2. project_root_path / relative_path
      3. files.path (stored path, may be absolute or relative)

    Use this when the file may not exist yet (trash, backup, new write).
    For read/index operations prefer :func:`resolve_indexed_file_path`.

    Args:
        file_row: Dict-like row with optional fields: relative_path,
            watch_absolute_path, project_name, project_root_path, path.

    Returns:
        List of Path objects (may be empty if no fields are populated).
    """
    rel = _normalize_relative_key(str(file_row.get("relative_path") or ""))

    watch_abs = file_row.get("watch_absolute_path")
    proj_name = file_row.get("project_name")
    root_path = file_row.get("project_root_path")
    stored = file_row.get("path")

    candidates: List[Path] = []
    if watch_abs and proj_name and rel:
        candidates.append(Path(str(watch_abs)) / str(proj_name) / rel)
    if root_path and rel:
        candidates.append(Path(str(root_path)) / rel)
    if stored:
        candidates.append(Path(str(stored)))
    return candidates


def resolve_file_path_from_parts(
    *,
    watch_abs: Optional[str] = None,
    project_name: Optional[str] = None,
    root_path: Optional[str] = None,
    relative_path: Optional[str] = None,
    stored_path: Optional[str] = None,
    probe_disk: bool = True,
) -> Optional[Path]:
    """Resolve absolute path from individual fields without a full file row.

    Equivalent to :func:`resolve_indexed_file_path` but accepts explicit
    keyword arguments. Use in driver/handler code where only a subset of
    fields is available (e.g. ``handle_index_file`` has ``root_path`` and
    ``relative_path`` only).

    Candidate order (same as the row-based variant):
      1. watch_abs / project_name / relative_path
      2. root_path / relative_path
      3. stored_path

    Args:
        watch_abs: Absolute path of the watch directory (from watch_dir_paths).
        project_name: Project directory name (direct child of watch_abs).
        root_path: Absolute project root path (from projects.root_path).
        relative_path: Path relative to project root.
        stored_path: Raw stored path from files.path (legacy / fallback).
        probe_disk: If True (default), return only a path that exists on disk.
            If False, return the highest-priority candidate regardless.

    Returns:
        Resolved Path, or None if no candidate could be constructed or
        (when probe_disk=True) none of the candidates exists on disk.
    """
    rel = _normalize_relative_key(relative_path or "")

    candidates: List[Path] = []
    if watch_abs and project_name and rel:
        candidates.append(Path(str(watch_abs)) / str(project_name) / rel)
    if root_path and rel:
        candidates.append(Path(str(root_path)) / rel)
    if stored_path:
        candidates.append(Path(str(stored_path)))

    if not candidates:
        return None

    if not probe_disk:
        return candidates[0]

    hit = _first_existing_file(*candidates)
    if hit is None:
        logger.debug(
            "resolve_file_path_from_parts: no file on disk "
            "(watch+name+rel=%s root+rel=%s stored=%s)",
            bool(watch_abs and project_name and rel),
            bool(root_path and rel),
            bool(stored_path),
        )
    return hit
