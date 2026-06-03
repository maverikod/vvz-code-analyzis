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

from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY
from code_analysis.core.project_root_path import (
    resolve_projects_root_path_row_to_absolute_str,
)

from ..path_normalization import normalize_path_simple
from ..file_identity import absolute_path_for_indexed_file, project_relative_file_posix

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
    """File change delta computed during scan phase.

    Path strings in ``new_files``, ``changed_files``, and ``deleted_files`` are
    **project-relative POSIX** paths (absolute scan keys are trimmed to the root suffix).
    """

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
        project_root = file_info.get("project_root")
        if not project_root:
            logger.warning(f"File {file_path_str} has no project_root, skipping")
            continue
        try:
            rel_key = project_relative_file_posix(file_path_str, Path(project_root))
        except ValueError:
            logger.warning(
                "File %s is not under declared project_root %s; skipping",
                file_path_str,
                project_root,
            )
            continue
        if not rel_key:
            continue
        files_by_project[project_id][rel_key] = file_info
        if project_id not in project_roots:
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
                    fid = f.get("id")
                    path = f.get("path")
                    rel = f.get("relative_path")
                    lm = f.get("last_modified")
                else:
                    fid, path = f.id, f.path
                    rel = getattr(f, "relative_path", None)
                    lm = getattr(f, "last_modified", None)
                row_for_abs = {"path": path, "relative_path": rel}
                abs_key = normalize_path_simple(
                    absolute_path_for_indexed_file(project_root, row_for_abs)
                )
                try:
                    rel_key = project_relative_file_posix(abs_key, project_root)
                except ValueError:
                    logger.warning(
                        "DB file row id=%s resolves outside project root %s; skipping delta",
                        fid,
                        project_root,
                    )
                    continue
                db_files.append(
                    {
                        "id": fid,
                        "path": rel_key,
                        "last_modified": last_modified_to_unix(lm),
                    }
                )

            db_files_map = {f["path"]: f for f in db_files}

            for rel_path_str, file_info in project_files.items():
                try:
                    mtime = file_info["mtime"]
                    size = file_info.get("size", 0)
                    db_file = db_files_map.get(rel_path_str)
                    if not db_file:
                        new_files.append((rel_path_str, mtime, size))
                    else:
                        db_mtime = db_file.get("last_modified")
                        if db_mtime is None or abs(mtime - float(db_mtime)) > 0.1:
                            changed_files.append((rel_path_str, mtime, size))
                except Exception as e:
                    logger.error(f"Error computing delta for file {rel_path_str}: {e}")

            deleted_files = list(
                find_missing_files(project_files, db_files_list, project_root)
            )

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
        from code_analysis.core.database.watch_dirs_partition import (
            current_server_instance_id,
        )

        sid = current_server_instance_id()
        if hasattr(database, "select"):
            all_projects = (
                database.select(
                    "projects",
                    where={"server_instance_id": sid},
                    columns=["id", "root_path", "watch_dir_id"],
                    priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                )
                or []
            )
        else:
            all_projects = (
                database.execute(
                    "SELECT id, root_path, watch_dir_id FROM projects "
                    "WHERE server_instance_id = ?",
                    (sid,),
                    priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                ).get("data")
                or []
            )
        if not isinstance(all_projects, list):
            all_projects = []

        for project_row in all_projects:
            db_project_id = project_row["id"]
            db_root_path_str = resolve_projects_root_path_row_to_absolute_str(
                root_path_stored=str(project_row.get("root_path") or ""),
                watch_dir_id=(
                    str(project_row["watch_dir_id"])
                    if project_row.get("watch_dir_id") is not None
                    else None
                ),
                database=database,
            )
            if not (db_root_path_str or "").strip():
                continue
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
                    # Project root directory is gone from disk.
                    # Mark ALL its DB files as deleted so the queue phase
                    # can cascade-purge all related records.
                    logger.warning(
                        "Project %s root_path %s does not exist on disk; "
                        "marking all %d DB files as deleted.",
                        db_project_id,
                        db_root_path,
                        0,  # count filled below
                    )
                    try:
                        get_raw = getattr(database, "get_project_file_rows", None)
                        if get_raw is not None:
                            gone_db_list = get_raw(db_project_id, include_deleted=False)
                        else:
                            gone_db_list = database.get_project_files(
                                db_project_id, include_deleted=False
                            )
                        if gone_db_list:
                            all_deleted = list(
                                find_missing_files({}, gone_db_list, db_root_path)
                            )
                            if all_deleted:
                                logger.warning(
                                    "Project %s: scheduling %d files for cascade purge",
                                    db_project_id,
                                    len(all_deleted),
                                )
                                deltas[db_project_id] = FileDelta(
                                    new_files=[],
                                    changed_files=[],
                                    deleted_files=all_deleted,
                                )
                    except Exception as gone_e:
                        logger.error(
                            "Failed to build delete delta for gone project %s: %s",
                            db_project_id,
                            gone_e,
                            exc_info=True,
                        )
                    continue
                # No scan entries for this project this cycle (e.g. last indexed file removed),
                # but DB rows must still be reconciled against disk.
                try:
                    get_raw = getattr(database, "get_project_file_rows", None)
                    if get_raw is not None:
                        sup_db_list = get_raw(db_project_id, include_deleted=False)
                    else:
                        sup_db_list = database.get_project_files(
                            db_project_id, include_deleted=False
                        )
                    if not sup_db_list:
                        continue
                    extra_deleted = list(
                        find_missing_files({}, sup_db_list, db_root_path)
                    )
                    if not extra_deleted:
                        continue
                    deltas[db_project_id] = FileDelta(
                        new_files=[],
                        changed_files=[],
                        deleted_files=extra_deleted,
                    )
                except Exception as sup_e:
                    logger.error(
                        "Supplemental watcher delta (no scan hits) failed for project %s: %s",
                        db_project_id,
                        sup_e,
                        exc_info=True,
                    )
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
