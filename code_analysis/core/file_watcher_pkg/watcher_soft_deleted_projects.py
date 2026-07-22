"""
Exclude disk-discovered project roots that are soft-deleted in the database.

When ``project_set_mark_del`` runs, ``projects.deleted`` is set before the row
is cleared or the tree is moved to trash. The file watcher must not treat those
directories as active projects (no auto re-registration, no traversal into the
tree for indexing).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Set, Tuple

from ..database_driver_pkg.domain.projects import (
    get_project, sync_project_metadata_from_projectid)
from ..project_discovery import ProjectRoot
from ..project_resolution import load_project_info
from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY

logger = logging.getLogger(__name__)


def _execute_data_rows(result: Any) -> List[dict[str, Any]]:
    """Return execute data rows."""
    if isinstance(result, dict):
        return list(result.get("data") or [])
    if isinstance(result, list):
        return result
    return []


def _truthy_deleted(value: Any) -> bool:
    """Return truthy deleted."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return bool(value)


def is_project_record_soft_deleted(project_obj: Any) -> bool:
    """True if a ``get_project`` / row dict / ORM-like object is soft-deleted."""
    if project_obj is None:
        return False
    if isinstance(project_obj, dict):
        return _truthy_deleted(project_obj.get("deleted"))
    return _truthy_deleted(getattr(project_obj, "deleted", None))


def partition_discovered_projects_by_db_soft_delete(
    database: Any,
    discovered: List[ProjectRoot],
) -> Tuple[List[ProjectRoot], Set[Path]]:
    """
    Split ``discovered`` into active projects vs roots that must not be scanned.

    A discovered root is excluded when:
    - ``projectid`` has ``deleted: true`` (source of truth on disk), or
    - after syncing from ``projectid``, ``database.get_project(project_id)`` has
      ``projects.deleted`` set, or
    - a row for the same ``root_path`` exists with ``projects.deleted`` set (covers
      id/file mismatch while trash lifecycle is in flight).

    Returns:
        (active_project_roots, resolved_paths_to_prune_from_traversal)
    """
    active: List[ProjectRoot] = []
    excluded_resolved: Set[Path] = set()

    for pr in discovered:
        try:
            root_resolved = Path(pr.root_path).resolve()
        except OSError:
            root_resolved = Path(pr.root_path)
        root_s = str(root_resolved)

        try:
            pid_info = load_project_info(pr.root_path)
        except Exception as exc:
            logger.warning(
                "[WATCHER] skip unreadable projectid root=%s project_id=%s: %s",
                root_s,
                pr.project_id,
                exc,
            )
            excluded_resolved.add(root_resolved)
            continue

        if pid_info.deleted:
            if hasattr(database, "sync_project_metadata_from_projectid"):
                sync_project_metadata_from_projectid(
                    database,
                    pr.root_path,
                    priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                )
            logger.info(
                "[WATCHER] skip discovered project root=%s project_id=%s "
                "reason=projectid.deleted",
                root_s,
                pr.project_id,
            )
            excluded_resolved.add(root_resolved)
            continue

        if hasattr(database, "sync_project_metadata_from_projectid"):
            sync_project_metadata_from_projectid(
                database,
                pr.root_path,
                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
            )

        proj_by_id = get_project(database, pr.project_id)
        if is_project_record_soft_deleted(proj_by_id):
            logger.info(
                "[WATCHER] skip discovered project root=%s project_id=%s "
                "reason=projects.deleted_by_id",
                root_s,
                pr.project_id,
            )
            excluded_resolved.add(root_resolved)
            continue

        from code_analysis.core.database.watch_dirs_partition import (
            current_server_instance_id,
        )

        sid = current_server_instance_id()
        res = database.execute(
            "SELECT id, deleted FROM projects "
            "WHERE server_instance_id = ? AND root_path = ? LIMIT 1",
            (sid, root_s),
            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
        )
        rows = _execute_data_rows(res)
        if rows and _truthy_deleted(rows[0].get("deleted")):
            logger.info(
                "[WATCHER] skip discovered project root=%s project_id=%s "
                "reason=projects.deleted_by_root_path",
                root_s,
                pr.project_id,
            )
            excluded_resolved.add(root_resolved)
            continue

        active.append(pr)

    return active, excluded_resolved
