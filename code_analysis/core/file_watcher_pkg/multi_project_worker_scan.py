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

from code_analysis.core.path_normalization import normalize_path_simple
from code_analysis.core.project_root_path import (
    find_project_id_by_resolved_absolute_root,
    persist_projects_root_path_stored_value, resolve_project_root_absolute_str)

from ..docs_indexing_config_load import load_docs_indexing_from_config_path
from ..project_ignore_policy import \
    filter_ignore_exception_py_paths_for_watcher
from ..sql_portable import sql_julian_timestamp_now_expr
from ..venv_path_policy import (
    build_allowlisted_site_packages_py_files,
    build_ignore_exception_files_for_projects,
    load_ignore_exceptions_from_config,
    load_ignore_exceptions_from_config_path,
    load_venv_site_packages_index_allowlist_from_config)
from ..watch_dir_access import describe_watch_dir_access
from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY
from ..worker_project_activity import (get_project_activity,
                                       release_project_activity,
                                       try_acquire_project_activity)
from .lock_manager import LockManager
from .multi_project_worker_specs import WatchDirSpec
from .processor import FileChangeProcessor
from .processor_delta import (compute_project_delta,
                              compute_supplemental_watch_dir_deltas)
from .scanner import iter_watch_dir_project_scans
from .watcher_project_metadata import (apply_project_updated_at_from_scan,
                                       load_projectid_flags_for_insert,
                                       refresh_project_metadata_from_projectid)
from .watcher_soft_deleted_projects import \
    partition_discovered_projects_by_db_soft_delete

logger = logging.getLogger(__name__)


def _merge_queue_stats(into: Dict[str, Any], part: Dict[str, Any]) -> None:
    """Add per-project queue counters into watch-dir totals."""
    for key in ("new_files", "changed_files", "deleted_files", "errors"):
        into[key] = int(into.get(key, 0)) + int(part.get(key, 0))


def _abspath_dedup_ts(value: Any) -> float:
    """Return abspath dedup ts."""
    if value is None:
        return float("inf")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("inf")


def _deduplicate_absolute_paths(database: Any, watch_dir: Path) -> int:
    """
    Finds files rows where path is absolute (starts with '/') within projects
    rooted under watch_dir. For each absolute-path row, checks if a sibling
    row with the relative counterpart exists. If a duplicate pair is found,
    the LATER-created (higher updated_at / created_at) row is deleted (all
    related data cleared), and the canonical (earlier) row's path/relative_path
    is normalised to the relative form. Returns count of pairs resolved.
    """
    wd = str(watch_dir.resolve())
    root_prefix = (wd, wd + "/%")
    list_sql = (
        "SELECT f.id AS file_id, f.project_id, f.path, f.relative_path, "
        "f.created_at, f.updated_at, p.root_path "
        "FROM files f "
        "JOIN projects p ON p.id = f.project_id "
        "WHERE (f.deleted IS NULL OR f.deleted = 0) "
        "AND SUBSTR(CAST(f.path AS TEXT), 1, 1) = '/' "
        "AND p.root_path IS NOT NULL "
        "AND (p.root_path = ? OR p.root_path LIKE ?)"
    )
    try:
        list_res = database.execute(
            list_sql,
            root_prefix,
            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
        )
    except Exception as exc:
        logger.warning("[ABSPATH_DEDUP] list absolute rows failed: %s", exc)
        return 0

    abs_rows = list(list_res.get("data", [])) if isinstance(list_res, dict) else []
    pairs_merged = 0
    lone_fixed = 0
    skipped = 0
    _now_sql = sql_julian_timestamp_now_expr(database)

    dup_sql = (
        "SELECT id, created_at, updated_at FROM files "
        "WHERE project_id = ? AND path = ? "
        "AND (deleted IS NULL OR deleted = 0) AND id != ?"
    )

    for abs_row in abs_rows:
        try:
            abs_path_str = str(abs_row.get("path") or "")
            project_id = abs_row.get("project_id")
            abs_row_id = abs_row.get("file_id")
            root_s = abs_row.get("root_path")
            if not abs_path_str or not project_id or abs_row_id is None or not root_s:
                skipped += 1
                continue

            try:
                abs_path = Path(abs_path_str)
                root = Path(str(root_s))
                rel = abs_path.relative_to(root)
            except ValueError:
                logger.warning(
                    "[ABSPATH_DEDUP] skip abs path outside project root: "
                    "project_id=%s path=%s root=%s",
                    project_id,
                    abs_path_str,
                    root_s,
                )
                skipped += 1
                continue

            rel_str = rel.as_posix()

            try:
                dup_res = database.execute(
                    dup_sql,
                    (project_id, rel_str, str(abs_row_id)),
                    priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                )
            except Exception as exc:
                logger.warning(
                    "[ABSPATH_DEDUP] duplicate lookup failed for %s: %s",
                    abs_path_str,
                    exc,
                )
                skipped += 1
                continue

            dup_rows = (
                list(dup_res.get("data", [])) if isinstance(dup_res, dict) else []
            )

            if dup_rows:
                rel_dup = dup_rows[0]
                rel_dup_id = rel_dup.get("id")
                t_abs = (
                    str(abs_row_id),
                    abs_row.get("created_at"),
                    abs_row.get("updated_at"),
                )
                t_rel = (
                    str(rel_dup_id),
                    rel_dup.get("created_at"),
                    rel_dup.get("updated_at"),
                )

                def _pair_sort_key(t: Tuple[str, Any, Any]) -> Tuple[float, float, str]:
                    """Return pair sort key."""
                    return (
                        _abspath_dedup_ts(t[2]),
                        _abspath_dedup_ts(t[1]),
                        str(t[0]),
                    )

                if _pair_sort_key(t_abs) <= _pair_sort_key(t_rel):
                    canonical_id, duplicate_id = t_abs[0], t_rel[0]
                else:
                    canonical_id, duplicate_id = t_rel[0], t_abs[0]

                try:
                    clear_fn = getattr(database, "clear_file_data", None)
                    if callable(clear_fn):
                        clear_fn(str(duplicate_id))
                    else:
                        # Legacy facades only: avoid SQLite-only tables (e.g.
                        # ``chunk_embeddings``) that are absent on PostgreSQL.
                        for tbl in ("code_chunks", "vector_index", "code_content"):
                            database.execute(
                                f"DELETE FROM {tbl} WHERE file_id = ?",
                                (str(duplicate_id),),
                                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                            )
                except Exception as exc:
                    logger.warning(
                        "[ABSPATH_DEDUP] duplicate cleanup failed duplicate_id=%s: %s",
                        duplicate_id,
                        exc,
                    )
                    skipped += 1
                    continue

                try:
                    database.execute(
                        "DELETE FROM files WHERE id = ?",
                        (str(duplicate_id),),
                        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                    )
                    database.execute(
                        f"UPDATE files SET path = ?, relative_path = ?, "
                        f"updated_at = {_now_sql} WHERE id = ?",
                        (rel_str, rel_str, str(canonical_id)),
                        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                    )
                    database.execute(
                        "DELETE FROM indexing_errors WHERE project_id = ? "
                        "AND (file_path = ? OR file_path = ?)",
                        (project_id, abs_path_str, rel_str),
                        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                    )
                except Exception as exc:
                    logger.warning(
                        "[ABSPATH_DEDUP] merge update failed canonical_id=%s: %s",
                        canonical_id,
                        exc,
                    )
                    skipped += 1
                    continue

                logger.info(
                    "[ABSPATH_DEDUP] merged abs=%s -> canonical_id=%s rel=%s",
                    abs_path_str,
                    canonical_id,
                    rel_str,
                )
                pairs_merged += 1
            else:
                try:
                    database.execute(
                        f"UPDATE files SET path = ?, relative_path = ?, "
                        f"updated_at = {_now_sql} WHERE id = ?",
                        (rel_str, rel_str, str(abs_row_id)),
                        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                    )
                except Exception as exc:
                    logger.warning(
                        "[ABSPATH_DEDUP] lone abs fix failed id=%s: %s",
                        abs_row_id,
                        exc,
                    )
                    skipped += 1
                    continue
                logger.info(
                    "[ABSPATH_DEDUP] fixed lone abs_row abs=%s -> rel=%s",
                    abs_path_str,
                    rel_str,
                )
                lone_fixed += 1
        except Exception as exc:
            logger.warning(
                "[ABSPATH_DEDUP] row handling failed: %s",
                exc,
                exc_info=True,
            )
            skipped += 1

    logger.info(
        "[ABSPATH_DEDUP] done: pairs_merged=%d, lone_fixed=%d, skipped=%d",
        pairs_merged,
        lone_fixed,
        skipped,
    )
    return pairs_merged + lone_fixed


def scan_watch_dir(
    spec: WatchDirSpec,
    processor: FileChangeProcessor,
    database: Any,
    global_ignore_patterns: Tuple[str, ...],
    locks_dir: Path,
    pid: int,
    *,
    config_path: Optional[Path] = None,
    manifest_signature_cache: Optional[Dict[str, Tuple[int, float, int]]] = None,
) -> Dict[str, Any]:
    """
    Scan a watched directory and process all discovered projects.

    Projects are discovered automatically by finding projectid files
    within the watched directory.

    Args:
        spec: Watch directory specification.
        processor: FileChangeProcessor for multi-project mode.
        database: Legacy SQL facade instance.
        global_ignore_patterns: Global ``file_watcher.ignore_patterns`` from config.
        locks_dir: Directory for lock files.
        pid: Process ID for lock acquisition.
        config_path: Optional server ``config.json`` for FAISS index invalidation.
        manifest_signature_cache: Mutable per-worker cache of last-seen per-project
            disk signatures; when a project's signature is unchanged, the heavy
            manifest rebuild and bulk queue are skipped for that project
            (bug 673ba07a). None disables the short-circuit.

    Returns:
        Per-watch-dir scan stats.
    """
    from datetime import datetime

    from ..project_discovery import (DuplicateProjectIdError,
                                     NestedProjectError,
                                     discover_projects_in_directory)

    stats: Dict[str, Any] = {
        "scanned_dirs": 0,
        "new_files": 0,
        "changed_files": 0,
        "deleted_files": 0,
        "errors": 0,
    }

    watch_dir = spec.watch_dir
    access_issue = describe_watch_dir_access(watch_dir)
    if access_issue:
        logger.warning(
            "Watch directory not accessible (id=%s, path=%s): %s — will retry next cycle",
            spec.watch_dir_id,
            watch_dir,
            access_issue,
        )
        return stats

    lock_key = str(watch_dir.resolve())
    lock_manager = LockManager(locks_dir, lock_key)

    if not lock_manager.acquire_lock(watch_dir, pid):
        logger.warning(f"Could not acquire lock for {watch_dir}, skipping")
        stats["errors"] += 1
        return stats

    try:
        _now_sql = sql_julian_timestamp_now_expr(database)
        try:
            _deduplicate_absolute_paths(database, watch_dir)
        except Exception as _dedup_exc:
            logger.warning(
                "[ABSPATH_DEDUP] deduplication failed (non-fatal): %s",
                _dedup_exc,
                exc_info=True,
            )

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
                logger.debug(
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
                    old_abs = resolve_project_root_absolute_str(
                        project_id=str(project_root_obj.project_id),
                        root_path_stored=str(project.get("root_path") or ""),
                        watch_dir_id=(
                            str(project.get("watch_dir_id"))
                            if project.get("watch_dir_id")
                            else None
                        ),
                        project_name=str(project.get("name") or "") or None,
                        database=database,
                        require_exists=False,
                    )
                    new_norm = normalize_path_simple(
                        str(project_root_obj.root_path.resolve())
                    )
                    old_norm = normalize_path_simple(old_abs) if old_abs else ""
                    if old_norm != new_norm:
                        old_for_relocate = old_abs or str(
                            project.get("root_path") or ""
                        )
                        ok = database.relocate_project_root_after_disk_move(
                            project_root_obj.project_id,
                            old_for_relocate,
                            str(project_root_obj.root_path.resolve()),
                            new_watch_dir_id=spec.watch_dir_id,
                        )
                        if not ok:
                            stats["errors"] += 1
                            continue
                        project["root_path"] = str(project_root_obj.root_path.resolve())
                        logger.info(
                            "[WATCHER] project_id=%s root_path synced disk move: %s -> %s",
                            project_root_obj.project_id,
                            old_for_relocate,
                            new_norm,
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
                            SET {', '.join(update_fields)}
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
                    refresh_project_metadata_from_projectid(
                        database,
                        project_root_obj.root_path,
                        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                    )
                else:
                    existing_project_id = find_project_id_by_resolved_absolute_root(
                        database,
                        str(project_root_obj.root_path.resolve()),
                    )
                    if existing_project_id:
                        if existing_project_id != project_root_obj.project_id:
                            logger.warning(
                                f"Project at {project_root_obj.root_path} exists with "
                                f"different ID ({existing_project_id}) than projectid file "
                                f"({project_root_obj.project_id}), updating"
                            )
                            database.execute(
                                f"""
                                UPDATE projects 
                                SET id = ?, comment = ?
                                WHERE id = ?
                                """,
                                (
                                    project_root_obj.project_id,
                                    project_root_obj.description,
                                    existing_project_id,
                                ),
                                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                            )
                        refresh_project_metadata_from_projectid(
                            database,
                            project_root_obj.root_path,
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
                        pid_deleted, pid_paused = load_projectid_flags_for_insert(
                            project_root_obj.root_path
                        )
                        root_stored = persist_projects_root_path_stored_value(
                            project_root_absolute=project_root_obj.root_path,
                            watch_dir_id=(
                                str(watch_dir_id) if watch_dir_id is not None else None
                            ),
                            database=database,
                        )
                        if hasattr(database, "insert_project_row"):
                            database.insert_project_row(
                                project_root_obj.project_id,
                                root_stored,
                                project_name,
                                comment=project_description,
                                watch_dir_id=(
                                    str(watch_dir_id)
                                    if watch_dir_id is not None
                                    else None
                                ),
                                deleted=pid_deleted,
                                processing_paused=pid_paused,
                                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                            )
                        else:
                            from code_analysis.core.server_instance import \
                                get_server_instance_id

                            sid = get_server_instance_id()
                            database.execute(
                                f"""
                                INSERT INTO projects (
                                    id, server_instance_id, root_path, name, comment,
                                    watch_dir_id, updated_at
                                )
                                VALUES (?, ?, ?, ?, ?, ?, {_now_sql})
                                """,
                                (
                                    project_root_obj.project_id,
                                    sid,
                                    root_stored,
                                    project_name,
                                    project_description,
                                    watch_dir_id,
                                ),
                                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                            )
                        refresh_project_metadata_from_projectid(
                            database,
                            project_root_obj.root_path,
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
                        logger.debug(
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

        from code_analysis.core.watch_dir_settings import \
            merge_watch_ignore_patterns

        merged_ignore = list(
            merge_watch_ignore_patterns(
                spec.ignore_patterns,
                global_ignore_patterns,
            )
        )
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
        all_scanned_files: Dict[str, Dict[str, Any]] = {}
        project_deltas: Dict[str, Any] = {}
        dir_stats: Dict[str, Any] = {
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }
        processed_project_ids: Set[str] = set()
        watcher_coord = {
            "database": database,
            "owner_id": watcher_owner_id,
            "lease_ttl": watcher_lease_ttl,
            "config_path": config_path,
        }

        from .ignore_pre_scan_purge import (
            apply_ignore_purge_split_to_deltas,
            run_pre_scan_ignore_purge_for_project)
        from .watcher_bulk_sync import bulk_sync_supported
        from .watcher_disk_manifest import (build_project_disk_manifest,
                                            compute_project_files_signature,
                                            manifest_rebuild_needed)

        project_id_to_root: Dict[str, Path] = {
            p.project_id: Path(p.root_path) for p in discovered_projects
        }

        for project_id, project_root, project_files in iter_watch_dir_project_scans(
            watch_dir,
            [spec.watch_dir],
            merged_ignore,
            allowed_venv_py_files=allowed_venv_py or None,
            ignore_exception_files=exc_files_filtered or None,
            ignore_exception_patterns=exc_patterns or None,
            immediate_project_roots=immediate_roots,
            soft_deleted_project_roots=soft_deleted_roots or None,
            docs_indexing=docs_indexing_snap,
        ):
            processed_project_ids.add(project_id)
            all_scanned_files.update(project_files)

            if project_id in skipped_projects:
                continue

            if bulk_sync_supported(database):
                run_pre_scan_ignore_purge_for_project(
                    database,
                    project_id,
                    merged_ignore,
                    allowed_venv_py_files=allowed_venv_py or None,
                    ignore_exception_files=exc_files_filtered or None,
                    ignore_exception_patterns=exc_patterns or None,
                    config_path=config_path,
                    docs_indexing=docs_indexing_snap,
                )
                signature = compute_project_files_signature(project_files, project_id)
                if not manifest_rebuild_needed(
                    project_id, signature, manifest_signature_cache
                ):
                    logger.debug(
                        "[MANIFEST SKIP] watch_dir=%s project_id=%s disk signature "
                        "unchanged (files=%s max_mtime=%s total_size=%s); skipping "
                        "manifest rebuild and bulk queue",
                        watch_dir,
                        project_id,
                        signature[0],
                        signature[1],
                        signature[2],
                    )
                    continue
                manifest = build_project_disk_manifest(
                    project_files, project_id, project_root
                )
                project_queue_stats = processor.queue_project_bulk_sync(
                    project_id,
                    project_root,
                    manifest,
                    watch_dir_id=(
                        str(spec.watch_dir_id)
                        if spec.watch_dir_id is not None
                        else None
                    ),
                    watcher_coord=watcher_coord,
                )
                project_deltas[project_id] = compute_project_delta(
                    database, project_root, project_id, project_files
                )
                if manifest_signature_cache is not None:
                    # Record only after a successful bulk queue so a failed cycle
                    # retries the rebuild next time.
                    manifest_signature_cache[project_id] = signature
            else:
                project_delta = compute_project_delta(
                    database, project_root, project_id, project_files
                )
                project_deltas[project_id] = project_delta
                apply_ignore_purge_split_to_deltas(
                    {project_id: project_delta},
                    {project_id: project_root},
                    merged_ignore,
                    allowed_venv_py_files=allowed_venv_py or None,
                    ignore_exception_files=exc_files_filtered or None,
                    ignore_exception_patterns=exc_patterns or None,
                    docs_indexing=docs_indexing_snap,
                )
                project_queue_stats = processor.queue_changes(
                    watch_dir,
                    {project_id: project_delta},
                    watcher_coord=watcher_coord,
                )
            _merge_queue_stats(dir_stats, project_queue_stats)
            apply_project_updated_at_from_scan(
                database,
                project_id,
                project_files,
                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
            )
            logger.info(
                "[QUEUE PROJECT] watch_dir=%s project_id=%s "
                "new=%s changed=%s deleted=%s errors=%s files_buffered=%s",
                watch_dir,
                project_id,
                project_queue_stats.get("new_files", 0),
                project_queue_stats.get("changed_files", 0),
                project_queue_stats.get("deleted_files", 0),
                project_queue_stats.get("errors", 0),
                len(project_files),
            )

        supplemental = compute_supplemental_watch_dir_deltas(
            database,
            [spec.watch_dir.resolve()],
            watch_dir,
            processed_project_ids,
        )
        if skipped_projects:
            supplemental = {
                k: v for k, v in supplemental.items() if k not in skipped_projects
            }
        if supplemental:
            if bulk_sync_supported(database):
                for supp_pid, _supp_delta in supplemental.items():
                    supp_root = project_id_to_root.get(supp_pid)
                    if supp_root is None:
                        continue
                    run_pre_scan_ignore_purge_for_project(
                        database,
                        supp_pid,
                        merged_ignore,
                        allowed_venv_py_files=allowed_venv_py or None,
                        ignore_exception_files=exc_files_filtered or None,
                        ignore_exception_patterns=exc_patterns or None,
                        config_path=config_path,
                        docs_indexing=docs_indexing_snap,
                    )
                    supp_stats = processor.queue_project_bulk_sync(
                        supp_pid,
                        supp_root,
                        [],
                        watch_dir_id=(
                            str(spec.watch_dir_id)
                            if spec.watch_dir_id is not None
                            else None
                        ),
                        watcher_coord=watcher_coord,
                    )
                    _merge_queue_stats(dir_stats, supp_stats)
                project_deltas.update(supplemental)
            else:
                apply_ignore_purge_split_to_deltas(
                    supplemental,
                    project_id_to_root,
                    merged_ignore,
                    allowed_venv_py_files=allowed_venv_py or None,
                    ignore_exception_files=exc_files_filtered or None,
                    ignore_exception_patterns=exc_patterns or None,
                    docs_indexing=docs_indexing_snap,
                )
                supp_stats = processor.queue_changes(
                    watch_dir,
                    supplemental,
                    watcher_coord=watcher_coord,
                )
                _merge_queue_stats(dir_stats, supp_stats)
                project_deltas.update(supplemental)
            logger.info(
                "[QUEUE SUPPLEMENTAL] watch_dir=%s projects=%s "
                "new=%s changed=%s deleted=%s errors=%s",
                watch_dir,
                len(supplemental),
                supp_stats.get("new_files", 0),
                supp_stats.get("changed_files", 0),
                supp_stats.get("deleted_files", 0),
                supp_stats.get("errors", 0),
            )

        delta = {k: v for k, v in project_deltas.items() if k not in skipped_projects}

        scan_end = datetime.now()
        scan_duration = (scan_end - scan_start).total_seconds()

        total_new = sum(len(d.new_files) for d in delta.values())
        total_changed = sum(len(d.changed_files) for d in delta.values())
        total_deleted = sum(len(d.deleted_files) for d in delta.values())
        per_project = " | ".join(
            f"{proj_id} new={len(d.new_files)} changed={len(d.changed_files)} deleted={len(d.deleted_files)}"
            for proj_id, d in sorted(delta.items(), key=lambda kv: str(kv[0]))
        )
        logger.info(
            f"[SCAN END] Watch directory: {watch_dir} | "
            f"time: {scan_end.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"duration: {scan_duration:.2f}s | "
            f"files_scanned: {len(all_scanned_files)} | "
            f"projects: {len(delta)} | "
            f"delta: new={total_new}, changed={total_changed}, deleted={total_deleted} | "
            f"per_project: {per_project}"
        )

        logger.info(
            f"[QUEUE END] Watch directory: {watch_dir} | "
            f"duration: {(datetime.now() - scan_start).total_seconds():.2f}s | "
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
                            f"""
                            UPDATE file_watcher_stats
                            SET current_project_id = ?, last_updated = {_now_sql}
                            WHERE cycle_id = ?
                            """,
                            (current_project_id, cycle_id),
                            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                        )
                except Exception as e:
                    logger.debug(f"Could not update current_project_id: {e}")

        stats["scanned_dirs"] += 1
        stats["files_scanned"] = len(all_scanned_files)
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
