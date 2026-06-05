"""
Initialize watch directories from config for multi-project file watcher.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List

from code_analysis.core.project_root_path import (
    find_project_id_by_resolved_absolute_root,
    persist_projects_root_path_stored_value,
)
from code_analysis.core.server_instance import get_server_instance_id

from ..sql_portable import sql_julian_timestamp_now_expr
from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY
from .multi_project_worker_specs import WatchDirSpec

logger = logging.getLogger(__name__)


def _watch_dir_id_str(watch_dir_id: Any) -> str:
    """Canonical str for watch dir UUIDs.

    Config JSON uses strings; PostgreSQL may return ``uuid.UUID`` from
    ``SELECT id``. Set membership and SQL parameters must use the same
    representation so the post-loop cleanup does not treat configured dirs
    as orphan rows and overwrite ``watch_dir_paths.absolute_path`` with NULL.
    """
    if watch_dir_id is None:
        return ""
    return str(watch_dir_id)


def _is_path_under(path: Path, parent: Path) -> bool:
    """Check whether ``path`` is equal to or under ``parent``.

    Args:
        path: Resolved absolute path to test.
        parent: Resolved candidate parent directory.

    Returns:
        True if ``path`` starts with ``parent``.
    """
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _verify_and_relocate_orphaned_projects(
    database: Any,
    config_watch_dir_paths: dict[str, Path],
    now_sql: str,
) -> None:
    """Verify root_path for projects outside all config watch_dirs.

    Config is authoritative over DB. For each active project whose root_path
    does not reside under any config watch_dir, searches all config watch_dirs
    for a ``projectid`` file whose content matches the project UUID. When found,
    calls ``relocate_project_root_after_disk_move`` to correct root_path and
    all absolute file paths atomically. Also updates watch_dir_id to match
    the config watch_dir where the project was found.

    Args:
        database: Legacy SQL facade instance.
        config_watch_dir_paths: Mapping of watch_dir_id -> resolved Path from config.
        now_sql: SQL expression for current timestamp (driver-specific).
    """
    from ..project_discovery import discover_projects_in_directory

    if not config_watch_dir_paths:
        return

    config_roots: list[Path] = list(config_watch_dir_paths.values())

    all_projects = database.get_all_projects()
    for proj in all_projects:
        project_id = (
            proj.get("id") if isinstance(proj, dict) else getattr(proj, "id", None)
        )
        raw_root = (
            proj.get("root_path")
            if isinstance(proj, dict)
            else getattr(proj, "root_path", None)
        )
        if not project_id or not raw_root:
            continue

        try:
            current_root = Path(str(raw_root)).resolve()
        except OSError:
            current_root = Path(str(raw_root))

        is_under_config = any(_is_path_under(current_root, wd) for wd in config_roots)
        if is_under_config:
            continue

        logger.info(
            "[WATCHER_INIT] project_id=%s root_path=%s is outside all config "
            "watch_dirs; searching for projectid file",
            project_id,
            current_root,
        )

        found = False
        for wid, wd_path in config_watch_dir_paths.items():
            if not wd_path.exists():
                continue
            try:
                discovered = discover_projects_in_directory(wd_path)
            except Exception as exc:
                logger.warning(
                    "[WATCHER_INIT] error scanning %s for orphan project %s: %s",
                    wd_path,
                    project_id,
                    exc,
                )
                continue
            for candidate in discovered:
                if str(candidate.project_id) != str(project_id):
                    continue
                new_root = candidate.root_path.resolve()
                if database.relocate_project_root_after_disk_move(
                    project_id,
                    str(current_root),
                    str(new_root),
                    new_watch_dir_id=wid,
                ):
                    logger.info(
                        "[WATCHER_INIT] project_id=%s relocated %s -> %s, watch_dir_id=%s",
                        project_id,
                        current_root,
                        new_root,
                        wid,
                    )
                else:
                    logger.error(
                        "[WATCHER_INIT] failed to relocate project_id=%s to %s",
                        project_id,
                        new_root,
                    )
                found = True
                break
            if found:
                break

        if not found:
            logger.warning(
                "[WATCHER_INIT] project_id=%s root_path=%s not found in any config "
                "watch_dir; leaving as-is",
                project_id,
                current_root,
            )


def initialize_watch_dirs(database: Any, watch_dirs: List[WatchDirSpec]) -> None:
    """Initialize watch directories from config.

    Creates/updates watch_dirs and watch_dir_paths, discovers projects
    and creates/updates them with watch_dir_id. Sets NULL paths for
    watch_dirs not found in config or on disk.

    Phase 3 (startup config priority): for every project in DB whose
    root_path does not lie under any config watch_dir, searches all
    config watch_dirs for a projectid file matching the project UUID.
    When found, calls relocate_project_root_after_disk_move so that
    root_path and all file paths are corrected without data loss.

    Args:
        database: Legacy SQL facade instance.
        watch_dirs: List of watch directory specs.
    """
    from ..database.watch_dirs_partition import (
        watch_dir_paths_upsert_conflict_target,
        watch_dirs_upsert_conflict_target,
    )
    from ..path_normalization import normalize_path_simple
    from ..project_discovery import discover_projects_in_directory
    from .watcher_soft_deleted_projects import (
        partition_discovered_projects_by_db_soft_delete,
    )

    logger.info("Initializing watch directories...")

    server_instance_id = get_server_instance_id()

    if not watch_dirs:
        logger.warning(
            "initialize_watch_dirs: empty watch_dirs list; "
            "skipping (avoids clearing watch_dir_paths for all DB dirs)"
        )
        return

    now_sql = sql_julian_timestamp_now_expr(database)
    watch_dirs_conflict = watch_dirs_upsert_conflict_target(database)
    watch_dir_paths_conflict = watch_dir_paths_upsert_conflict_target(database)
    config_watch_dir_ids: set[str] = set()
    # Map watch_dir_id -> resolved Path for use in phase 3
    config_watch_dir_paths: dict[str, Path] = {}
    for spec in watch_dirs:
        wid = _watch_dir_id_str(spec.watch_dir_id)
        watch_dir_path = spec.watch_dir.resolve()
        config_watch_dir_ids.add(wid)
        config_watch_dir_paths[wid] = watch_dir_path

        database.execute(
            f"""
            INSERT INTO watch_dirs (server_instance_id, id, name, updated_at)
            VALUES (?, ?, ?, {now_sql})
            ON CONFLICT {watch_dirs_conflict} DO UPDATE SET
                server_instance_id = EXCLUDED.server_instance_id,
                name = EXCLUDED.name,
                updated_at = EXCLUDED.updated_at
            """,
            (server_instance_id, wid, watch_dir_path.name),
            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
        )

        if watch_dir_path.exists():
            normalized_path = normalize_path_simple(str(watch_dir_path))
            database.execute(
                f"""
                INSERT INTO watch_dir_paths (
                    server_instance_id, watch_dir_id, absolute_path, updated_at
                )
                VALUES (?, ?, ?, {now_sql})
                ON CONFLICT {watch_dir_paths_conflict} DO UPDATE SET
                    server_instance_id = EXCLUDED.server_instance_id,
                    absolute_path = EXCLUDED.absolute_path,
                    updated_at = EXCLUDED.updated_at
                """,
                (server_instance_id, wid, normalized_path),
                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
            )
            logger.debug(f"Updated watch_dir_path: {wid} -> {normalized_path}")

            try:
                discovered_projects = discover_projects_in_directory(watch_dir_path)
                discovered_projects, _ = (
                    partition_discovered_projects_by_db_soft_delete(
                        database, discovered_projects
                    )
                )
                for project_root_obj in discovered_projects:
                    project_obj = database.get_project(project_root_obj.project_id)
                    if project_obj:
                        stored_root = (
                            project_obj.get("root_path")
                            if isinstance(project_obj, dict)
                            else getattr(project_obj, "root_path", None)
                        )
                        if stored_root:
                            try:
                                old_rr = Path(str(stored_root)).resolve()
                                new_rr = project_root_obj.root_path.resolve()
                            except OSError:
                                old_rr = Path(str(stored_root))
                                new_rr = project_root_obj.root_path.resolve()
                            if old_rr != new_rr:
                                if database.relocate_project_root_after_disk_move(
                                    project_root_obj.project_id,
                                    str(old_rr),
                                    str(new_rr),
                                    new_watch_dir_id=wid,
                                ):
                                    logger.info(
                                        "[WATCHER_INIT] project_id=%s root_path %s -> %s",
                                        project_root_obj.project_id,
                                        old_rr,
                                        new_rr,
                                    )
                                else:
                                    logger.error(
                                        "[WATCHER_INIT] failed to relocate project_id=%s "
                                        "to %s (collision or DB error)",
                                        project_root_obj.project_id,
                                        new_rr,
                                    )
                        wd_id = (
                            project_obj.get("watch_dir_id")
                            if isinstance(project_obj, dict)
                            else getattr(project_obj, "watch_dir_id", None)
                        )
                        if _watch_dir_id_str(wd_id) != wid:
                            database.execute(
                                f"""
                                UPDATE projects
                                SET watch_dir_id = ?, server_instance_id = ?, updated_at = {now_sql}
                                WHERE id = ?
                                  AND (server_instance_id IS NULL
                                       OR server_instance_id = ?)
                                """,
                                (
                                    wid,
                                    server_instance_id,
                                    project_root_obj.project_id,
                                    server_instance_id,
                                ),
                                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                            )
                            logger.debug(
                                f"Updated project {project_root_obj.project_id} "
                                f"watch_dir_id to {wid}"
                            )
                    else:
                        existing_by_root = find_project_id_by_resolved_absolute_root(
                            database,
                            str(project_root_obj.root_path.resolve()),
                        )
                        if existing_by_root:
                            if existing_by_root != project_root_obj.project_id:
                                logger.warning(
                                    "[WATCHER_INIT] project at %s already registered as %s; "
                                    "projectid file has %s (same server instance). Skipping insert.",
                                    project_root_obj.root_path,
                                    existing_by_root,
                                    project_root_obj.project_id,
                                )
                            continue
                        project_name = project_root_obj.root_path.name
                        root_stored = persist_projects_root_path_stored_value(
                            project_root_absolute=project_root_obj.root_path,
                            watch_dir_id=wid or None,
                            database=database,
                        )
                        if hasattr(database, "insert_project_row"):
                            database.insert_project_row(
                                project_root_obj.project_id,
                                root_stored,
                                project_name,
                                comment=project_root_obj.description,
                                watch_dir_id=wid,
                                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                            )
                        else:
                            database.execute(
                                f"""
                                INSERT INTO projects (
                                    id, server_instance_id, root_path, name, comment,
                                    watch_dir_id, updated_at
                                )
                                VALUES (?, ?, ?, ?, ?, ?, {now_sql})
                                """,
                                (
                                    project_root_obj.project_id,
                                    server_instance_id,
                                    root_stored,
                                    project_name,
                                    project_root_obj.description,
                                    wid,
                                ),
                                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                            )
                        logger.info(
                            f"Created project {project_root_obj.project_id} "
                            f"at {project_root_obj.root_path} "
                            f"with watch_dir_id: {wid}"
                        )
            except Exception as e:
                logger.error(
                    f"Error discovering projects in {watch_dir_path}: {e}",
                    exc_info=True,
                )
        else:
            database.execute(
                f"""
                INSERT INTO watch_dir_paths (
                    server_instance_id, watch_dir_id, absolute_path, updated_at
                )
                VALUES (?, ?, NULL, {now_sql})
                ON CONFLICT {watch_dir_paths_conflict} DO UPDATE SET
                    server_instance_id = EXCLUDED.server_instance_id,
                    absolute_path = EXCLUDED.absolute_path,
                    updated_at = EXCLUDED.updated_at
                """,
                (server_instance_id, wid),
                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
            )
            logger.warning(
                f"Watch dir path does not exist: {watch_dir_path}, "
                f"setting NULL for watch_dir_id: {wid}"
            )

    if config_watch_dir_ids:
        placeholders = ",".join("?" * len(config_watch_dir_ids))
        database.execute(
            f"""
            UPDATE projects
            SET server_instance_id = ?, updated_at = {now_sql}
            WHERE server_instance_id IS NULL
              AND watch_dir_id IN ({placeholders})
            """,
            (server_instance_id, *sorted(config_watch_dir_ids)),
            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
        )

    all_watch_dirs_result = database.execute(
        "SELECT id FROM watch_dirs WHERE server_instance_id = ?",
        (server_instance_id,),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    all_watch_dirs_rows = (
        all_watch_dirs_result.get("data", [])
        if isinstance(all_watch_dirs_result, dict)
        else []
    )
    for db_watch_dir in all_watch_dirs_rows:
        db_wid = _watch_dir_id_str(db_watch_dir["id"])
        if db_wid not in config_watch_dir_ids:
            database.execute(
                f"""
                INSERT INTO watch_dir_paths (
                    server_instance_id, watch_dir_id, absolute_path, updated_at
                )
                VALUES (?, ?, NULL, {now_sql})
                ON CONFLICT {watch_dir_paths_conflict} DO UPDATE SET
                    server_instance_id = EXCLUDED.server_instance_id,
                    absolute_path = EXCLUDED.absolute_path,
                    updated_at = EXCLUDED.updated_at
                """,
                (server_instance_id, db_wid),
                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
            )
            logger.debug(f"Watch dir {db_wid} not in config, setting path to NULL")

    # Phase 3: config-priority root_path verification.
    # For projects whose root_path is outside every config watch_dir,
    # search config watch_dirs for a projectid file matching the project UUID.
    # Config is authoritative: when found, relocate root_path in DB.
    _verify_and_relocate_orphaned_projects(database, config_watch_dir_paths, now_sql)

    logger.info("Watch directories initialization completed")
