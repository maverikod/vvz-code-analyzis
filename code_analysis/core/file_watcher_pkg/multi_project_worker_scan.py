"""
Scan one watch directory for multi-project file watcher.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

from ..venv_path_policy import (
    build_allowlisted_site_packages_py_files,
    expand_ignore_exception_py_files,
    load_ignore_exceptions_from_config,
    load_venv_site_packages_index_allowlist_from_config,
)
from .lock_manager import LockManager
from .multi_project_worker_specs import WatchDirSpec
from .processor import FileChangeProcessor
from .scanner import scan_directory

logger = logging.getLogger(__name__)


def scan_watch_dir(
    spec: WatchDirSpec,
    processor: FileChangeProcessor,
    database: Any,
    ignore_patterns: Tuple[str, ...],
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
        database: CodeDatabase instance.
        ignore_patterns: Global ignore patterns (merged with spec.ignore_patterns).
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

        if not discovered_projects:
            logger.debug(f"No projects found in watched directory: {watch_dir}")
            return stats

        for project_root_obj in discovered_projects:
            try:
                project_obj = database.get_project(project_root_obj.project_id)
                project = (
                    {
                        "id": project_obj.id,
                        "root_path": project_obj.root_path,
                        "name": project_obj.name,
                        "comment": project_obj.comment,
                        "watch_dir_id": getattr(project_obj, "watch_dir_id", None),
                    }
                    if project_obj
                    else None
                )
                if project:
                    if project["root_path"] != str(project_root_obj.root_path):
                        logger.error(
                            f"Project ID {project_root_obj.project_id} already exists "
                            f"with different root_path: {project['root_path']} "
                            f"(found in {project_root_obj.root_path}). "
                            "One project_id cannot be used in different directories. Skipping."
                        )
                        stats["errors"] += 1
                        continue
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
                            )
                    else:
                        existing_project_obj = database.get_project(
                            project_root_obj.project_id
                        )
                        existing_project = (
                            {
                                "id": existing_project_obj.id,
                                "root_path": existing_project_obj.root_path,
                            }
                            if existing_project_obj
                            else None
                        )
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
                        )
                        logger.info(
                            f"Auto-created project {project_root_obj.project_id} "
                            f"at {project_root_obj.root_path} "
                            f"with description: {project_description} "
                            f"and watch_dir_id: {watch_dir_id}"
                        )

                        logger.info(
                            "[AUTO_INDEXING] Starting update_indexes for newly created project "
                            "project_id=%s root_path=%s (each file will get needs_chunking=1, chunks deleted)",
                            project_root_obj.project_id,
                            str(project_root_obj.root_path),
                        )
                        try:
                            import asyncio
                            import threading

                            from code_analysis.commands.code_mapper_mcp_command import (
                                UpdateIndexesMCPCommand,
                            )
                            from code_analysis.core.constants import (
                                DEFAULT_MAX_FILE_LINES,
                            )

                            def run_indexing() -> None:
                                try:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    try:
                                        cmd = UpdateIndexesMCPCommand()
                                        result = loop.run_until_complete(
                                            cmd.execute(
                                                project_id=project_root_obj.project_id,
                                                max_lines=DEFAULT_MAX_FILE_LINES,
                                                trigger="auto_indexing",
                                            )
                                        )
                                        if not result.success:
                                            logger.warning(
                                                f"Auto-indexing for new project {project_root_obj.project_id} "
                                                f"completed with warnings: {result.message}"
                                            )
                                        else:
                                            logger.info(
                                                f"Auto-indexing for new project {project_root_obj.project_id} "
                                                f"completed: {result.data.get('files_processed', 0) if result.data else 0} files processed"
                                            )
                                    finally:
                                        loop.close()
                                except Exception as e:
                                    logger.error(
                                        f"Failed to run auto-indexing for new project "
                                        f"{project_root_obj.project_id}: {e}",
                                        exc_info=True,
                                    )

                            thread = threading.Thread(target=run_indexing, daemon=True)
                            thread.start()
                            logger.info(
                                "[AUTO_INDEXING] Started background thread for project_id=%s "
                                "(update_indexes running; check [update_indexes START] with trigger=auto_indexing)",
                                project_root_obj.project_id,
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to start auto-indexing for new project "
                                f"{project_root_obj.project_id}: {e}"
                            )
            except Exception as e:
                logger.error(
                    f"Failed to get/create project {project_root_obj.project_id} "
                    f"at {project_root_obj.root_path}: {e}",
                    exc_info=True,
                )
                stats["errors"] += 1

        logger.info(
            f"[SCAN START] Watch directory: {watch_dir} | "
            f"discovered_projects: {len(discovered_projects)} | "
            f"time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        merged_ignore = list(ignore_patterns) + list(spec.ignore_patterns)
        scan_start = datetime.now()
        allowlist = load_venv_site_packages_index_allowlist_from_config()
        allowed_venv_py: Set[Path] = set()
        if allowlist:
            for project_root_obj in discovered_projects:
                allowed_venv_py.update(
                    build_allowlisted_site_packages_py_files(
                        project_root_obj.root_path, allowlist
                    )
                )
        ign_ex: Set[Path] = set()
        exc_patterns = load_ignore_exceptions_from_config()
        if exc_patterns:
            for project_root_obj in discovered_projects:
                ign_ex.update(
                    expand_ignore_exception_py_files(
                        project_root_obj.root_path, exc_patterns
                    )
                )

        from .ignore_pre_scan_purge import run_pre_scan_ignore_purge_for_project

        for project_root_obj in discovered_projects:
            try:
                n = run_pre_scan_ignore_purge_for_project(
                    database,
                    project_root_obj.project_id,
                    merged_ignore,
                    allowed_venv_py_files=allowed_venv_py or None,
                    ignore_exception_files=ign_ex or None,
                    config_path=config_path,
                )
                if n:
                    logger.info(
                        "[IGNORE_PURGE] Removed %d DB file row(s) for project %s "
                        "before scan (ignore policy)",
                        n,
                        project_root_obj.project_id,
                    )
            except Exception as e:
                logger.error(
                    "[IGNORE_PURGE] Failed for project %s: %s",
                    project_root_obj.project_id,
                    e,
                    exc_info=True,
                )
                stats["errors"] += 1

        immediate_roots = {
            Path(p.root_path).resolve() for p in discovered_projects
        }
        scanned_files = scan_directory(
            root_dir=watch_dir,
            watch_dirs=[spec.watch_dir],
            ignore_patterns=merged_ignore,
            allowed_venv_py_files=allowed_venv_py or None,
            ignore_exception_files=ign_ex or None,
            immediate_project_roots=immediate_roots,
        )

        delta = processor.compute_delta(watch_dir, scanned_files)
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
        dir_stats = processor.queue_changes(watch_dir, delta)
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
                        )
                except Exception as e:
                    logger.debug(f"Could not update current_project_id: {e}")

        stats["scanned_dirs"] += 1
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
