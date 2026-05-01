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

from ..project_discovery import ProjectRoot
from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY

logger = logging.getLogger(__name__)


def _execute_data_rows(result: Any) -> List[dict[str, Any]]:
    if isinstance(result, dict):
        return list(result.get("data") or [])
    if isinstance(result, list):
        return result
    return []


def _truthy_deleted(value: Any) -> bool:
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
    - ``database.get_project(project_id)`` exists and ``projects.deleted`` is set, or
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

        proj_by_id = database.get_project(pr.project_id)
        if is_project_record_soft_deleted(proj_by_id):
            logger.info(
                "[WATCHER] skip discovered project root=%s project_id=%s "
                "reason=projects.deleted_by_id",
                root_s,
                pr.project_id,
            )
            excluded_resolved.add(root_resolved)
            continue

        res = database.execute(
            "SELECT id, deleted FROM projects WHERE root_path = ? LIMIT 1",
            (root_s,),
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
