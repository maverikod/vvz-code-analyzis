"""
Scan one watch directory for multi-project file watcher.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

from ..project_ignore_policy import filter_ignore_exception_py_paths_for_watcher
from ..venv_path_policy import (
    build_allowlisted_site_packages_py_files,
    build_ignore_exception_files_for_projects,
    load_ignore_exceptions_from_config,
    load_ignore_exceptions_from_config_path,
    load_venv_site_packages_index_allowlist_from_config,
)
from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY
from ..docs_indexing_config_load import load_docs_indexing_from_config_path
from ..worker_project_activity import (
    get_project_activity,
    release_project_activity,
    try_acquire_project_activity,
)
from .lock_manager import LockManager
from .multi_project_worker_specs import WatchDirSpec
from .processor import FileChangeProcessor
from .scanner import scan_directory
from .watcher_soft_deleted_projects import (
    partition_discovered_projects_by_db_soft_delete,
)

logger = logging.getLogger(__name__)


def scan_watch_dir(
    spec: WatchDirSpec,
    processor: FileChangeProcessor,
    database: Any,
    _ignore_patterns: Tuple[str, ...],
    locks_dir: Path,
    pid: int,
    *,
    config_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Scan a watched directory and process all discovered projects.

    Projects are discovered automatically by finding projectid files
    within the watched directory.

    Args:
        spec: Watch directory specification.
        processor: FileChangeProcessor for multi-project mode.
        database: Legacy SQL facade instance.
        _ignore_patterns: Deprecated global ignore patterns (ignored; kept for API compatibility).
        locks_dir: Directory for lock files.
        pid: Process ID for lock acquisition.
        config_path: Optional server ``config.json`` for FAISS index invalidation.

    Returns:
        Per-watch-dir scan stats.
    """
    from datetime import datetime

    from ..project_discovery import (
        DuplicateProjectIdError,
        NestedProjectError,
        discover_projects_in_directory,
    )

    stats: Dict[str, Any] = {
        "scanned_dirs": 0,
        "new_files": 0,
        "changed_files": 0,
        "deleted_files": 0,
        "errors": 0,
    }

    watch_dir = spec.watch_dir
    if not watch_dir.exists():
        logger.warning(f"Watched directory does not exist: {watch_dir}")
        return stats

    lock_key = str(watch_dir.resolve())
    lock_manager = LockManager(locks_dir, lock_key)

    if not lock_manager.acquire_lock(watch_dir, pid):
        logger.warning(f"Could not acquire lock for {watch_dir}, skipping")
        stats["errors"] += 1
        return stats

    try:
        try:
            discovered_projects = discover_projects_in_directory(watch_dir)
        except NestedProjectError as e:
            logger.error(
                f"Nested project detected in {watch_dir}: {e}, skipping watch_dir"
            )
            stats["errors"] += 1
            return stats
        except DuplicateProjectIdError as e:
            logger.error(
                f"Duplicate project_id detected in {watch_dir}: {e}, skipping watch_dir"
            )
            stats["errors"] += 1
            return stats

        discovered_projects, soft_deleted_roots = (
            partition_discovered_projects_by_db_soft_delete(
                database, discovered_projects
            )
        )

        if not discovered_projects:
            logger.debug(f"No projects found in watched directory: {watch_dir}")
            return stats

        watcher_lease_ttl = 300.0
        watcher_owner_id = f"watcher:{pid}:{uuid.uuid4()}"
        skipped_projects: Set[str] = set()

        for project_root_obj in discovered_projects:
            pid_p = project_root_obj.project_id
            if not try_acquire_project_activity(
                database,
                pid_p,
                "watcher",
                watcher_owner_id,
                "watcher_staging",
                watcher_lease_ttl,
            ):
                row = get_project_activity(database, pid_p) or {}
                logger.info(
                    "[WORKER_COORD] watcher skip project_id=%s reason=watcher_staging owner_type=%s",
                    pid_p,
                    row.get("owner_type", "unknown"),
                )
                skipped_projects.add(pid_p)
                continue
            try:
                project_obj = database.get_project(project_root_obj.project_id)
                if not project_obj:
                    project = None
                elif isinstance(project_obj, dict):
                    project = {
                        "id": project_obj.get("id"),
                        "root_path": project_obj.get("root_path"),
                        "name": project_obj.get("name"),
                        "comment": project_obj.get("comment"),
                        "watch_dir_id": project_obj.get("watch_dir_id"),
                    }
                else:
                    project = {
                        "id": project_obj.id,
                        "root_path": project_obj.root_path,
                        "name": project_obj.name,
                        "comment": project_obj.comment,
                        "watch_dir_id": getattr(project_obj, "watch_dir_id", None),
                    }
                if project:
                    try:
                        old_root_res = Path(str(project["root_path"])).resolve()
                        new_root_res = Path(project_root_obj.root_path).resolve()
                    except OSError:
                        old_root_res = Path(str(project["root_path"]))
                        new_root_res = Path(project_root_obj.root_path)
                    if old_root_res != new_root_res:
                        ok = database.relocate_project_root_after_disk_move(
                            project_root_obj.project_id,
                            str(old_root_res),
                            str(new_root_res),
                            new_watch_dir_id=spec.watch_dir_id,
                        )
                        if not ok:
                            stats["errors"] += 1
                            continue
                        project["root_path"] = str(new_root_res)
                        logger.info(
                            "[WATCHER] project_id=%s root_path synced disk move: %s -> %s",
                            project_root_obj.project_id,
                            old_root_res,
                            new_root_res,
                        )
                    current_comment = project.get("comment")
                    current_watch_dir_id = project.get("watch_dir_id")
                    watch_dir_id = spec.watch_dir_id
                    needs_update = False
                    update_fields = []
                    update_values = []

                    if current_comment != project_root_obj.description:
                        needs_update = True
                        update_fields.append("comment = ?")
                        update_values.append(project_root_obj.description)

                    if current_watch_dir_id != watch_dir_id:
                        needs_update = True
                        update_fields.append("watch_dir_id = ?")
                        update_values.append(watch_dir_id)

                    if needs_update:
                        update_values.append(project_root_obj.project_id)
                        database.execute(
                            f"""
                            UPDATE projects 
                            SET {', '.join(update_fields)}, updated_at = julianday('now')
                            WHERE id = ?
                            """,
                            tuple(update_values),
                            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                        )
                        logger.debug(
                            f"Updated project {project_root_obj.project_id}: "
                            f"comment={current_comment} -> {project_root_obj.description}, "
                            f"watch_dir_id={current_watch_dir_id} -> {watch_dir_id}"
                        )
                else:
                    existing_result = database.execute(
                        "SELECT id FROM projects WHERE root_path = ? LIMIT 1",
                        (str(project_root_obj.root_path),),
                        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                    )
                    existing_rows = (
                        existing_result.get("data", [])
                        if isinstance(existing_result, dict)
                        else []
                    )
                    existing_project_id = (
                        existing_rows[0].get("id") if existing_rows else None
                    )
                    if existing_project_id:
                        if existing_project_id != project_root_obj.project_id:
                            logger.warning(
                                f"Project at {project_root_obj.root_path} exists with "
                                f"different ID ({existing_project_id}) than projectid file "
                                f"({project_root_obj.project_id}), updating"
                            )
                            database.execute(
                                """
                                UPDATE projects 
                                SET id = ?, comment = ?, updated_at = julianday('now')
                                WHERE id = ?
                                """,
                                (
                                    project_root_obj.project_id,
                                    project_root_obj.description,
                                    existing_project_id,
                                ),
                                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                            )
                    else:
                        existing_project_obj = database.get_project(
                            project_root_obj.project_id
                        )
                        if not existing_project_obj:
                            existing_project = None
                        elif isinstance(existing_project_obj, dict):
                            existing_project = {
                                "id": existing_project_obj.get("id"),
                                "root_path": existing_project_obj.get("root_path"),
                            }
                        else:
                            existing_project = {
                                "id": existing_project_obj.id,
                                "root_path": existing_project_obj.root_path,
                            }
                        if existing_project:
                            logger.error(
                                f"Project ID {project_root_obj.project_id} already exists "
                                f"with root_path: {existing_project['root_path']} "
                                f"(trying to use in {project_root_obj.root_path}). "
                                "One project_id cannot be used in different directories. Skipping."
                            )
                            stats["errors"] += 1
                            continue

                        project_name = project_root_obj.root_path.name
                        project_description = project_root_obj.description
                        watch_dir_id = spec.watch_dir_id
                        database.execute(
                            """
                            INSERT INTO projects (id, root_path, name, comment, watch_dir_id, updated_at)
                            VALUES (?, ?, ?, ?, ?, julianday('now'))
                            """,
                            (
                                project_root_obj.project_id,
                                str(project_root_obj.root_path),
                                project_name,
                                project_description,
                                watch_dir_id,
                            ),
                            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                        )
                        logger.info(
                            f"Auto-created project {project_root_obj.project_id} "
                            f"at {project_root_obj.root_path} "
                            f"with description: {project_description} "
                            f"and watch_dir_id: {watch_dir_id}"
                        )

                        # Auto-indexing runs via the normal indexer; queue maps files
                        # with needs_chunking=1. No daemon update_indexes from watcher.
                        logger.info(
                            "[WORKER_COORD] new project %s: use normal indexer path after queue "
                            "(no watcher auto_indexing thread).",
                            project_root_obj.project_id,
                        )
            except Exception as e:
                logger.error(
                    f"Failed to get/create project {project_root_obj.project_id} "
                    f"at {project_root_obj.root_path}: {e}",
                    exc_info=True,
                )
                stats["errors"] += 1
            finally:
                release_project_activity(database, pid_p, "watcher", watcher_owner_id)

        logger.info(
            f"[SCAN START] Watch directory: {watch_dir} | "
            f"discovered_projects: {len(discovered_projects)} | "
            f"time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Ignore policy for watcher comes only from worker.watch_dirs[].ignore_patterns.
        merged_ignore = list(spec.ignore_patterns)
        scan_start = datetime.now()
        docs_indexing_snap: Optional[Dict[str, Any]] = None
        if config_path is not None:
            docs_indexing_snap = load_docs_indexing_from_config_path(config_path)
        allowlist = load_venv_site_packages_index_allowlist_from_config()
        allowed_venv_py: Set[Path] = set()
        if allowlist:
            for project_root_obj in discovered_projects:
                allowed_venv_py.update(
                    build_allowlisted_site_packages_py_files(
                        project_root_obj.root_path, allowlist
                    )
                )
        if config_path is not None:
            exc_patterns = load_ignore_exceptions_from_config_path(config_path)
        else:
            exc_patterns = load_ignore_exceptions_from_config()

        exc_files_raw: Set[Path] = set()
        if exc_patterns:
            exc_files_raw = build_ignore_exception_files_for_projects(
                [Path(p.root_path) for p in discovered_projects],
                list(exc_patterns),
            )
        exc_files_filtered = filter_ignore_exception_py_paths_for_watcher(
            exc_files_raw,
            [Path(p.root_path) for p in discovered_projects],
            allowed_venv_py or None,
        )

        immediate_roots = {Path(p.root_path).resolve() for p in discovered_projects}
        scanned_files = scan_directory(
            root_dir=watch_dir,
            watch_dirs=[spec.watch_dir],
            ignore_patterns=merged_ignore,
            allowed_venv_py_files=allowed_venv_py or None,
            ignore_exception_files=exc_files_filtered or None,
            ignore_exception_patterns=exc_patterns or None,
            immediate_project_roots=immediate_roots,
            soft_deleted_project_roots=soft_deleted_roots or None,
            docs_indexing=docs_indexing_snap,
        )

        delta = processor.compute_delta(watch_dir, scanned_files)
        if skipped_projects:
            delta = {k: v for k, v in delta.items() if k not in skipped_projects}

        from .ignore_pre_scan_purge import apply_ignore_purge_split_to_deltas

        project_id_to_root: Dict[str, Path] = {
            p.project_id: Path(p.root_path) for p in discovered_projects
        }
        apply_ignore_purge_split_to_deltas(
            delta,
            project_id_to_root,
            merged_ignore,
            allowed_venv_py_files=allowed_venv_py or None,
            ignore_exception_files=exc_files_filtered or None,
            ignore_exception_patterns=exc_patterns or None,
            docs_indexing=docs_indexing_snap,
        )

        scan_end = datetime.now()
        scan_duration = (scan_end - scan_start).total_seconds()

        total_new = sum(len(d.new_files) for d in delta.values())
        total_changed = sum(len(d.changed_files) for d in delta.values())
        total_deleted = sum(len(d.deleted_files) for d in delta.values())
        per_project = " | ".join(
            f"{proj_id} new={len(d.new_files)} changed={len(d.changed_files)} deleted={len(d.deleted_files)}"
            for proj_id, d in sorted(delta.items())
        )
        logger.info(
            f"[SCAN END] Watch directory: {watch_dir} | "
            f"time: {scan_end.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"duration: {scan_duration:.2f}s | "
            f"files_scanned: {len(scanned_files)} | "
            f"projects: {len(delta)} | "
            f"delta: new={total_new}, changed={total_changed}, deleted={total_deleted} | "
            f"per_project: {per_project}"
        )

        queue_start = datetime.now()
        dir_stats = processor.queue_changes(
            watch_dir,
            delta,
            watcher_coord={
                "database": database,
                "owner_id": watcher_owner_id,
                "lease_ttl": watcher_lease_ttl,
                "config_path": config_path,
            },
        )
        queue_end = datetime.now()
        queue_duration = (queue_end - queue_start).total_seconds()
        logger.info(
            f"[QUEUE END] Watch directory: {watch_dir} | "
            f"duration: {queue_duration:.2f}s | "
            f"new: {dir_stats.get('new_files', 0)} | "
            f"changed: {dir_stats.get('changed_files', 0)} | "
            f"deleted: {dir_stats.get('deleted_files', 0)}"
        )

        if delta:
            current_project_id = list(delta.keys())[-1] if delta else None
            if current_project_id:
                try:
                    cycle_result = database.execute(
                        """
                        SELECT cycle_id FROM file_watcher_stats
                        WHERE cycle_end_time IS NULL
                        ORDER BY cycle_start_time DESC
                        LIMIT 1
                        """,
                        None,
                        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                    )
                    cycle_rows = (
                        cycle_result.get("data", [])
                        if isinstance(cycle_result, dict)
                        else []
                    )
                    if cycle_rows:
                        cycle_id = cycle_rows[0].get("cycle_id")
                        database.execute(
                            """
                            UPDATE file_watcher_stats
                            SET current_project_id = ?, last_updated = julianday('now')
                            WHERE cycle_id = ?
                            """,
                            (current_project_id, cycle_id),
                            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                        )
                except Exception as e:
                    logger.debug(f"Could not update current_project_id: {e}")

        stats["scanned_dirs"] += 1
        stats["files_scanned"] = len(scanned_files)
        stats["new_files"] += int(dir_stats.get("new_files", 0))
        stats["changed_files"] += int(dir_stats.get("changed_files", 0))
        stats["deleted_files"] += int(dir_stats.get("deleted_files", 0))
        stats["errors"] += int(dir_stats.get("errors", 0))

    except Exception as e:
        logger.error(
            f"Error scanning watch directory {watch_dir}: {e}",
            exc_info=True,
        )
        stats["errors"] += 1
    finally:
        lock_manager.release_lock(watch_dir)

    return stats
