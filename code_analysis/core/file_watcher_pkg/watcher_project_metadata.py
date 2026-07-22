"""
Watcher helpers: sync projectid → DB flags and accumulate ``projects.updated_at`` from scan.

``deleted`` and ``processing_paused`` are read from ``projectid`` and written to
``projects``. ``projects.updated_at`` is advanced only from the latest file mtime
seen while walking a project tree (not from metadata edits).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ..database_driver_pkg.domain.projects import sync_project_metadata_from_projectid
from ..sql_portable import unix_timestamp_to_julian_day
from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY

logger = logging.getLogger(__name__)


def max_unix_mtime_from_project_files(
    project_files: Dict[str, Dict[str, Any]],
) -> Optional[float]:
    """Return the latest disk ``mtime`` among scanned project files, if any."""
    max_m: Optional[float] = None
    for info in project_files.values():
        raw = info.get("mtime")
        if raw is None:
            continue
        try:
            mtime = float(raw)
        except (TypeError, ValueError):
            continue
        if max_m is None or mtime > max_m:
            max_m = mtime
    return max_m


def refresh_project_metadata_from_projectid(
    database: Any,
    project_root: str | Path,
    *,
    priority: int = BACKGROUND_WORKER_DB_RPC_PRIORITY,
) -> Optional[str]:
    """
    Sync ``projects.deleted``, ``processing_paused``, ``comment`` from ``projectid``.

    Does not modify ``projects.updated_at`` (that field is filled during file scan).
    """
    if hasattr(database, "sync_project_metadata_from_projectid"):
        return sync_project_metadata_from_projectid(
            database,
            project_root,
            priority=priority,
        )
    from ..project_resolution import load_project_info

    try:
        info = load_project_info(project_root)
    except Exception as exc:
        logger.warning(
            "refresh_project_metadata_from_projectid: cannot read %s/projectid: %s",
            project_root,
            exc,
        )
        return None
    database.execute(
        """
        UPDATE projects
        SET deleted = ?,
            processing_paused = ?,
            comment = ?
        WHERE id = ?
        """,
        (
            bool(info.deleted),
            bool(info.processing_paused),
            info.description or None,
            info.project_id,
        ),
    )
    return info.project_id


def apply_project_updated_at_from_scan(
    database: Any,
    project_id: str,
    project_files: Dict[str, Dict[str, Any]],
    *,
    priority: int = BACKGROUND_WORKER_DB_RPC_PRIORITY,
) -> bool:
    """
    Advance ``projects.updated_at`` to the Julian day of the latest scanned file mtime.

    Updates only when the accumulated mtime is newer than the stored value.
    """
    max_m = max_unix_mtime_from_project_files(project_files)
    if max_m is None:
        return False
    jd = unix_timestamp_to_julian_day(max_m)
    database.execute(
        """
        UPDATE projects
        SET updated_at = ?
        WHERE id = ?
          AND (updated_at IS NULL OR updated_at < ?)
        """,
        (jd, project_id, jd),
    )
    return True


def load_projectid_flags_for_insert(
    project_root: str | Path,
) -> tuple[bool, bool]:
    """Read ``deleted`` and ``processing_paused`` from ``projectid`` (default false)."""
    from ..project_resolution import load_project_info

    try:
        info = load_project_info(project_root)
        return bool(info.deleted), bool(info.processing_paused)
    except Exception:
        return False, False
