"""
Disk manifest rows for watcher bulk PostgreSQL sync.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from code_analysis.core.file_disk_registration import collect_file_disk_metadata
from code_analysis.core.file_identity import relative_path_for_project
from code_analysis.core.tree_lifecycle.checksum import validate_or_recreate_tree_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WatcherDiskFileRow:
    """One on-disk file row loaded before bulk DB sync."""

    relative_path: str
    last_modified: float
    lines: int
    has_docstring: bool
    tree_checksum: str


def build_project_disk_manifest(
    project_files: Dict[str, Dict[str, Any]],
    project_id: str,
    project_root: Path,
) -> List[WatcherDiskFileRow]:
    """
    Build insert-ready disk manifest for one project scan result.

    Reads metadata and tree checksum from disk (same work legacy queue did per file).
    """
    try:
        root = project_root.resolve()
    except OSError:
        root = project_root

    rows: List[WatcherDiskFileRow] = []
    for _abs_key, info in project_files.items():
        file_project_id = info.get("project_id")
        if file_project_id and str(file_project_id) != str(project_id):
            continue
        path_obj = info.get("path")
        if not isinstance(path_obj, Path):
            continue
        if not path_obj.is_file():
            continue
        mtime = float(info.get("mtime") or 0.0)
        try:
            rel_posix = relative_path_for_project(path_obj, root)
        except Exception:
            logger.debug("skip manifest path outside root: %s", path_obj, exc_info=True)
            continue
        lines, has_docstring = collect_file_disk_metadata(path_obj)
        try:
            tree_ref, _state = validate_or_recreate_tree_file(
                project_root=root,
                file_path=rel_posix,
            )
            tree_checksum = tree_ref.content_checksum
        except (FileNotFoundError, ValueError, OSError) as exc:
            logger.warning(
                "[MANIFEST] skip file without valid tree project_id=%s path=%s: %s",
                project_id,
                rel_posix,
                exc,
            )
            continue
        rows.append(
            WatcherDiskFileRow(
                relative_path=rel_posix,
                last_modified=mtime,
                lines=lines,
                has_docstring=has_docstring,
                tree_checksum=tree_checksum,
            )
        )
    rows.sort(key=lambda r: r.relative_path)
    return rows


def filter_manifest_paths(
    rows: Sequence[WatcherDiskFileRow],
    excluded_relative_paths: Optional[Sequence[str]] = None,
) -> List[WatcherDiskFileRow]:
    """Drop manifest rows whose relative_path is in ``excluded_relative_paths``."""
    if not excluded_relative_paths:
        return list(rows)
    excluded = {p.strip().replace("\\", "/") for p in excluded_relative_paths if p}
    if not excluded:
        return list(rows)
    return [r for r in rows if r.relative_path not in excluded]
