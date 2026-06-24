"""
Startup-time DB/disk reconciliation for the multi-project file watcher.

Runs ONCE, before the first scan cycle and before ``initialize_watch_dirs``, in
this strict order (see TZ "file watcher startup reconciliation"):

  1. Build a ``(watch_dir, project_root, project_id)`` table by discovering
     projects on disk across every configured watch directory.
  2. Detect duplicate ``project_id`` values (the same id under more than one path
     or in more than one watch directory). Any duplicate is a fatal data-integrity
     error: log the offending table and request a full server stop.
  3. When no duplicates exist, delete from the database every project that is not
     found on disk (no matching ``projectid`` file under any watch dir), together
     with all data tied to it (files, chunks, vectors, ...).
  4. For each surviving project, scan its database file rows and mark every file
     that no longer exists on disk as deleted.

Only after this completes does the watcher proceed to ``initialize_watch_dirs``
and normal scanning.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import signal
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ..file_identity import absolute_path_for_indexed_file
from ..path_normalization import normalize_path_simple
from ..project_discovery import (
    DuplicateProjectIdError,
    NestedProjectError,
    discover_projects_in_directory,
)
from ..server_instance import get_server_instance_id
from ..sql_portable import sql_julian_timestamp_now_expr
from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY
from .multi_project_worker_init import (
    _project_row_field,
    _resolve_project_row_absolute_path,
)
from .multi_project_worker_specs import WatchDirSpec

logger = logging.getLogger(__name__)


class StartupReconciliationFatal(RuntimeError):
    """Unrecoverable data corruption found at startup (duplicate project_id)."""


@dataclass(frozen=True)
class DiscoveredProjectRow:
    """One row of the watch_dir -> project -> project_id table built on disk."""

    watch_dir: str
    root_path: str
    project_id: str


def _build_discovery_table(
    watch_dirs: Sequence[WatchDirSpec],
) -> Tuple[List[DiscoveredProjectRow], List[str]]:
    """Discover projects on disk and build the reconciliation table.

    Returns:
        A tuple ``(rows, hard_errors)``. ``rows`` is the discovered
        ``(watch_dir, root_path, project_id)`` table. ``hard_errors`` collects
        per-watch-dir duplicate/nested discovery failures that, like cross-dir
        duplicates, must stop the server.
    """
    rows: List[DiscoveredProjectRow] = []
    hard_errors: List[str] = []

    for spec in watch_dirs:
        watch_dir = Path(spec.watch_dir).resolve()
        if not watch_dir.is_dir():
            logger.warning(
                "[RECONCILE] watch_dir not present on disk, skipping: %s", watch_dir
            )
            continue
        try:
            discovered = discover_projects_in_directory(watch_dir)
        except DuplicateProjectIdError as exc:
            hard_errors.append(f"duplicate project_id in {watch_dir}: {exc}")
            continue
        except NestedProjectError as exc:
            hard_errors.append(f"nested project in {watch_dir}: {exc}")
            continue
        except (OSError, ValueError) as exc:
            logger.error("[RECONCILE] error scanning %s: %s", watch_dir, exc)
            continue
        for proj in discovered:
            rows.append(
                DiscoveredProjectRow(
                    watch_dir=normalize_path_simple(str(watch_dir)),
                    root_path=normalize_path_simple(str(proj.root_path.resolve())),
                    project_id=str(proj.project_id),
                )
            )
    return rows, hard_errors


def _log_discovery_table(rows: List[DiscoveredProjectRow]) -> None:
    """Emit the discovered watch_dir -> project -> project_id table to the log."""
    logger.info("[RECONCILE] discovered %d project(s) on disk:", len(rows))
    for r in sorted(rows, key=lambda x: (x.watch_dir, x.root_path)):
        logger.info(
            "[RECONCILE]   watch_dir=%s project=%s id=%s",
            r.watch_dir,
            r.root_path,
            r.project_id,
        )


def _find_duplicate_ids(
    rows: List[DiscoveredProjectRow],
) -> Dict[str, Set[Tuple[str, str]]]:
    """Return project_ids mapped to >1 distinct ``(watch_dir, root_path)`` location."""
    by_id: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
    for r in rows:
        by_id[r.project_id].add((r.watch_dir, r.root_path))
    return {pid: locs for pid, locs in by_id.items() if len(locs) > 1}


def _request_server_stop(server_pid: Optional[int]) -> None:
    """Send SIGTERM to the main server process for a clean, no-restart shutdown.

    The watcher runs as a child process; the target is the spawning daemon
    (``server_pid`` when known, otherwise the parent PID). A graceful SIGTERM
    lets the server's signal handler exit cleanly so systemd's ``Restart=on-failure``
    does not bounce it — the corruption must be fixed by a human first.
    """
    pid = server_pid if server_pid and server_pid > 1 else os.getppid()
    if not pid or pid <= 1:
        logger.error(
            "[RECONCILE] cannot resolve server PID to stop; worker aborting only"
        )
        return
    logger.error("[RECONCILE] requesting server stop via SIGTERM to PID %s", pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError) as exc:
        logger.error("[RECONCILE] failed to signal server PID %s: %s", pid, exc)


def _abort_on_duplicates(
    duplicates: Dict[str, Set[Tuple[str, str]]],
    hard_errors: List[str],
    server_pid: Optional[int],
) -> None:
    """Log the duplicate-id table, stop the server, and raise a fatal error."""
    logger.error(
        "[RECONCILE] FATAL: duplicate project_id detected on disk; "
        "refusing to continue. Server will be stopped for manual repair."
    )
    for pid, locs in sorted(duplicates.items()):
        logger.error("[RECONCILE]   duplicate id=%s found at:", pid)
        for watch_dir, root_path in sorted(locs):
            logger.error(
                "[RECONCILE]     watch_dir=%s root_path=%s", watch_dir, root_path
            )
    for err in hard_errors:
        logger.error("[RECONCILE]   %s", err)

    _request_server_stop(server_pid)
    raise StartupReconciliationFatal(
        "duplicate project_id detected on disk: "
        + ", ".join(sorted(duplicates)) + (
            ("; " + "; ".join(hard_errors)) if hard_errors else ""
        )
    )


def _all_db_projects(database: Any) -> List[Any]:
    """Every project row for this server instance (independent of file state)."""
    sid = get_server_instance_id()
    result = database.execute(
        "SELECT id, root_path, name, watch_dir_id FROM projects "
        "WHERE server_instance_id = ? OR server_instance_id IS NULL",
        (sid,),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    if isinstance(result, dict):
        return list(result.get("data", []) or [])
    if isinstance(result, list):
        return result
    return []


async def _purge_orphan_projects(
    database: Any, disk_ids: Set[str]
) -> List[Dict[str, str]]:
    """Delete every DB project whose id was not discovered on disk (cascade)."""
    from ...commands.clear_project_data_impl import _clear_project_data_impl

    purged: List[Dict[str, str]] = []
    for proj in _all_db_projects(database):
        project_id = str(_project_row_field(proj, "id") or "").strip()
        if not project_id:
            continue
        if project_id in disk_ids:
            continue
        name = str(_project_row_field(proj, "name") or "")
        raw_root = str(_project_row_field(proj, "root_path") or "")
        try:
            await _clear_project_data_impl(database, project_id)
        except Exception as exc:  # noqa: BLE001 - log and continue purging others
            logger.error(
                "[RECONCILE] failed to purge orphan project %s (%s): %s",
                project_id,
                name,
                exc,
                exc_info=True,
            )
            continue
        purged.append(
            {"project_id": project_id, "name": name, "root_path": raw_root}
        )
        logger.info(
            "[RECONCILE] purged orphan project %s (%s) root_path=%s (not on disk)",
            project_id,
            name,
            raw_root,
        )
    return purged


def _mark_missing_files_for_project(
    database: Any, proj: Any, now_sql: str
) -> int:
    """Mark DB file rows whose path is absent on disk as deleted. Returns count."""
    project_id = str(_project_row_field(proj, "id") or "").strip()
    if not project_id:
        return 0
    root = _resolve_project_row_absolute_path(proj, database, require_exists=True)
    if root is None:
        logger.warning(
            "[RECONCILE] project %s root unresolved on disk; skipping file pass",
            project_id,
        )
        return 0

    result = database.execute(
        "SELECT id, path, relative_path FROM files "
        "WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
        (project_id,),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    file_rows = (
        result.get("data", []) if isinstance(result, dict) else (result or [])
    )

    marked = 0
    for row in file_rows:
        if not isinstance(row, dict):
            continue
        abs_path = absolute_path_for_indexed_file(str(root), row)
        if abs_path and Path(abs_path).exists():
            continue
        file_id = row.get("id")
        if file_id is None:
            continue
        database.execute(
            f"UPDATE files SET deleted = 1, updated_at = {now_sql} WHERE id = ?",
            (file_id,),
            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
        )
        marked += 1
        logger.debug(
            "[RECONCILE] marked missing file deleted: project=%s path=%s",
            project_id,
            abs_path,
        )
    if marked:
        logger.info(
            "[RECONCILE] project %s: marked %d missing file(s) deleted",
            project_id,
            marked,
        )
    return marked


async def run_startup_reconciliation(
    database: Any,
    watch_dirs: Sequence[WatchDirSpec],
    *,
    server_pid: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the one-time startup reconciliation described in the module docstring.

    Args:
        database: Worker database client (legacy SQL facade).
        watch_dirs: Configured watch directory specs.
        server_pid: PID of the main server process to stop on fatal corruption.
            Defaults to the parent process when omitted.

    Returns:
        Summary dict: ``discovered``, ``purged_projects``, ``files_marked_deleted``.

    Raises:
        StartupReconciliationFatal: When duplicate project_ids are found on disk.
            The server stop is requested before the exception propagates.
    """
    logger.info("[RECONCILE] starting file-watcher startup reconciliation")

    # Step 1: build the watch_dir -> project -> project_id table.
    rows, hard_errors = _build_discovery_table(watch_dirs)
    _log_discovery_table(rows)

    # Step 2: duplicate-id detection. Any duplicate (or hard discovery error)
    # stops the server.
    duplicates = _find_duplicate_ids(rows)
    if duplicates or hard_errors:
        _abort_on_duplicates(duplicates, hard_errors, server_pid)

    disk_ids = {r.project_id for r in rows}

    # Step 3: delete projects that are not on disk, cascade.
    purged = await _purge_orphan_projects(database, disk_ids)

    # Step 4: per-project pass — mark files missing on disk as deleted.
    now_sql = sql_julian_timestamp_now_expr(database)
    files_marked = 0
    for proj in _all_db_projects(database):
        project_id = str(_project_row_field(proj, "id") or "").strip()
        if not project_id or project_id not in disk_ids:
            continue
        files_marked += _mark_missing_files_for_project(database, proj, now_sql)

    logger.info(
        "[RECONCILE] completed: discovered=%d purged_projects=%d files_marked_deleted=%d",
        len(rows),
        len(purged),
        files_marked,
    )
    return {
        "discovered": len(rows),
        "purged_projects": purged,
        "files_marked_deleted": files_marked,
    }
