"""
Scan phase: compute file change delta (new/changed/deleted) without DB writes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .scanner import find_missing_files

logger = logging.getLogger(__name__)

_JD_UNIX_EPOCH = 2440587.5


def last_modified_to_unix(value: Any) -> Optional[float]:
    """Normalize last_modified from DB to Unix timestamp for comparison with os.stat().st_mtime."""
    if value is None:
        return None
    timestamp_getter = getattr(value, "timestamp", None)
    if callable(timestamp_getter):
        try:
            return float(timestamp_getter())
        except (TypeError, ValueError):
            return None
    try:
        v = float(value)
        if v >= 1e9:
            return v
        return (v - _JD_UNIX_EPOCH) * 86400.0
    except (TypeError, ValueError):
        return None


@dataclass
class FileDelta:
    """File change delta computed during scan phase."""

    new_files: List[tuple[str, float, int]]
    changed_files: List[tuple[str, float, int]]
    deleted_files: List[str]
    # DB rows that match the ignore policy (on disk but excluded from the scan) —
    # full purge with dependencies, not soft-delete.
    ignore_purge_paths: List[str] = field(default_factory=list)


def compute_delta(
    database: Any,
    watch_dirs_resolved: List[Path],
    root_dir: Path,
    scanned_files: Dict[str, Dict],
) -> Dict[str, FileDelta]:
    """
    Compute file change delta for multiple projects (SCAN PHASE - no DB operations).
    Groups files by project_id and computes delta for each project separately.
    """
    files_by_project: Dict[str, Dict[str, Dict]] = defaultdict(dict)
    project_roots: Dict[str, Path] = {}

    for file_path_str, file_info in scanned_files.items():
        project_id = file_info.get("project_id")
        if not project_id:
            logger.warning(f"File {file_path_str} has no project_id, skipping")
            continue
        files_by_project[project_id][file_path_str] = file_info
        if project_id not in project_roots:
            project_root = file_info.get("project_root")
            if project_root:
                project_roots[project_id] = Path(project_root)

    deltas: Dict[str, FileDelta] = {}

    for project_id, project_files in files_by_project.items():
        project_root = project_roots.get(project_id)
        if not project_root:
            logger.warning(f"Project {project_id} has no project_root, skipping")
            continue

        new_files: List[tuple[str, float, int]] = []
        changed_files: List[tuple[str, float, int]] = []

        try:
            get_raw = getattr(database, "get_project_file_rows", None)
            if get_raw is not None:
                db_files_list = get_raw(project_id, include_deleted=False)
            else:
                db_files_list = database.get_project_files(
                    project_id, include_deleted=False
                )
            db_files = []
            for f in db_files_list:
                if isinstance(f, dict):
                    fid, path, lm = f.get("id"), f.get("path"), f.get("last_modified")
                else:
                    fid, path = f.id, f.path
                    lm = getattr(f, "last_modified", None)
                db_files.append(
                    {
                        "id": fid,
                        "path": path,
                        "last_modified": last_modified_to_unix(lm),
                    }
                )

            db_files_map = {f["path"]: f for f in db_files}

            for file_path_str, file_info in project_files.items():
                try:
                    mtime = file_info["mtime"]
                    size = file_info.get("size", 0)
                    db_file = db_files_map.get(file_path_str)
                    if not db_file:
                        new_files.append((file_path_str, mtime, size))
                    else:
                        db_mtime = db_file.get("last_modified")
                        if db_mtime is None or abs(mtime - float(db_mtime)) > 0.1:
                            changed_files.append((file_path_str, mtime, size))
                except Exception as e:
                    logger.error(f"Error computing delta for file {file_path_str}: {e}")

            deleted_files = list(find_missing_files(project_files, db_files))

            if changed_files and logger.isEnabledFor(logging.DEBUG):
                fp, disk_mt, _ = changed_files[0]
                db_rec = db_files_map.get(fp)
                db_mt = db_rec.get("last_modified") if db_rec else None
                logger.debug(
                    "[compute_delta] sample changed: path=%s db_mtime=%s disk_mtime=%s",
                    fp[-80:] if len(fp) > 80 else fp,
                    db_mt,
                    disk_mt,
                )

            deltas[project_id] = FileDelta(
                new_files=new_files,
                changed_files=changed_files,
                deleted_files=deleted_files,
            )

        except Exception as e:
            logger.error(
                f"Error computing delta for project {project_id} in {root_dir}: {e}"
            )
            deltas[project_id] = FileDelta(
                new_files=[], changed_files=[], deleted_files=[], ignore_purge_paths=[]
            )

    try:
        if hasattr(database, "select"):
            all_projects = (
                database.select("projects", columns=["id", "root_path"]) or []
            )
        else:
            all_projects = (
                database.execute("SELECT id, root_path FROM projects").get("data") or []
            )
        if not isinstance(all_projects, list):
            all_projects = []

        for project_row in all_projects:
            db_project_id = project_row["id"]
            db_root_path_str = project_row["root_path"]
            if db_project_id in deltas:
                continue
            try:
                db_root_path = Path(db_root_path_str).resolve()
                is_in_watch_dir = False
                for watch_dir in watch_dirs_resolved:
                    try:
                        db_root_path.relative_to(watch_dir)
                        is_in_watch_dir = True
                        break
                    except ValueError:
                        continue
                if not is_in_watch_dir:
                    continue
                if not db_root_path.exists():
                    logger.warning(
                        f"Project {db_project_id} root_path {db_root_path} does not exist. "
                        "Skipping automatic deletion. Files will be checked again in next scan."
                    )
                    continue
            except Exception as e:
                logger.debug(
                    f"Error checking project {db_project_id} root_path {db_root_path_str}: {e}"
                )
                continue
    except Exception as e:
        logger.warning(
            f"Error checking database projects for deleted directories in {root_dir}: {e}"
        )

    return deltas
