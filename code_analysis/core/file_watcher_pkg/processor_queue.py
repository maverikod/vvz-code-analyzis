"""
Queue phase: batch DB operations for file changes (new/changed/deleted).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import uuid

from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from code_analysis.core.worker_project_activity import (
    get_project_activity,
    heartbeat_project_activity,
    release_project_activity,
    try_acquire_project_activity,
)

from .ignore_pre_scan_purge import (
    collect_file_ids_for_active_paths,
    try_unlink_faiss_index_for_project,
)
from .processor_delta import FileDelta

from code_analysis.core.database.file_edit_lock import file_row_has_live_edit_lock
from code_analysis.core.sql_portable import sql_julian_timestamp_now_expr
from code_analysis.core.file_disk_registration import (
    collect_file_disk_metadata,
    ensure_file_row_for_disk_path,
)
from code_analysis.core.file_identity import (
    FILE_ROW_PATH_MATCH_SQL,
    file_row_path_match_values,
    relative_path_for_project,
)
from code_analysis.core.tree_lifecycle.checksum import validate_or_recreate_tree_file

logger = logging.getLogger(__name__)

_WATCHER_PHASE_HB = 50


def _watcher_path_input_to_absolute(file_path_str: str, project_root: Path) -> str:
    """Resolve queue/delta path (project-relative or absolute) to a normalized absolute path."""
    from code_analysis.core.path_normalization import normalize_path_simple

    raw = (file_path_str or "").strip()
    if not raw:
        return ""
    p = Path(raw.replace("\\", "/"))
    if p.is_absolute():
        return normalize_path_simple(p)
    try:
        root = project_root.resolve()
    except OSError:
        root = project_root
    return normalize_path_simple(root / p)


def _watch_dir_id_for_project(database: Any, project_id: str) -> Optional[str]:
    """Return watch dir id for project."""
    gp = getattr(database, "get_project", None)
    if not callable(gp):
        return None
    po = gp(project_id)
    if isinstance(po, dict):
        wd = po.get("watch_dir_id")
        return str(wd) if wd is not None else None
    if po is not None:
        wd = getattr(po, "watch_dir_id", None)
        return str(wd) if wd is not None else None
    return None


def _watcher_heartbeat_n(
    database: Any,
    project_id: str,
    owner_id: str,
    activity: str,
    ttl: float,
    n_ops: int,
) -> None:
    """Return watcher heartbeat n."""
    if n_ops > 0 and n_ops % _WATCHER_PHASE_HB == 0:
        heartbeat_project_activity(
            database, project_id, "watcher", owner_id, activity, ttl
        )


class ProcessorQueueOps:
    """Queue file changes for multiple projects (batch DB operations)."""

    def __init__(
        self,
        database: Any,
        watch_dirs_resolved: List[Path],
    ) -> None:
        """Initialize the instance."""
        self.database = database
        self.watch_dirs_resolved = watch_dirs_resolved

    def _db_execute(self, sql: str, params: Optional[tuple] = None) -> Any:
        """Execute SQL; support both execute() (client) and _execute() (legacy SQL facade)."""
        if hasattr(self.database, "execute"):
            return self.database.execute(
                sql,
                params or (),
                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
            )
        self.database._execute(sql, params)
        result = getattr(self.database, "_last_execute_result", None)
        if result is not None:
            return result
        # Legacy SQL facade: _execute returns None; use _fetchone for SELECT
        if hasattr(self.database, "_fetchone") and sql.strip().upper().startswith(
            "SELECT"
        ):
            row = self.database._fetchone(sql, params)
            return {"data": [row]} if row else {"data": []}
        return {"data": []}

    def _db_execute_batch(
        self,
        operations: List[Tuple[str, Optional[tuple]]],
    ) -> List[Dict[str, Any]]:
        """Run multiple SQL operations in one batch if database supports it."""
        if not operations:
            return []
        if hasattr(self.database, "execute_batch"):
            return self.database.execute_batch(
                operations,
                priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
            )
        results: List[Dict[str, Any]] = []
        for sql, params in operations:
            self._db_execute(sql, params or ())
            results.append({"data": []})
        return results

    def queue_changes(
        self,
        root_dir: Path,
        deltas: Dict[str, FileDelta],
        *,
        watcher_coord: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Queue file changes for multiple projects. Returns aggregated statistics."""
        total_stats = {
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }

        for project_id, delta in deltas.items():
            err_extra = len(delta.ignore_purge_paths)
            try:
                project_obj = self.database.get_project(project_id)
                # get_project may return a dict (local DB) or a Project object (RPC client)
                if not project_obj:
                    project = None
                else:
                    # Use attribute access for Project, subscript for dict (avoid TypeError)
                    id_ = (
                        project_obj["id"]
                        if isinstance(project_obj, dict)
                        else getattr(project_obj, "id", None)
                    )
                    root_path = (
                        project_obj["root_path"]
                        if isinstance(project_obj, dict)
                        else getattr(project_obj, "root_path", None)
                    )
                    name = (
                        project_obj.get("name")
                        if isinstance(project_obj, dict)
                        else getattr(project_obj, "name", None)
                    )
                    project = {"id": id_, "root_path": root_path, "name": name}
                root_path_val = project.get("root_path") if project else None
                if not project or not root_path_val:
                    logger.error(
                        f"[QUEUE] Project {project_id} not found in database. Skipping."
                    )
                    total_stats["errors"] += (
                        len(delta.new_files)
                        + len(delta.changed_files)
                        + len(delta.deleted_files)
                        + err_extra
                    )
                    continue

                project_root = Path(root_path_val)
                project_stats = self._queue_project_delta(
                    project_id, delta, project_root, watcher_coord=watcher_coord
                )
                total_stats["new_files"] += project_stats["new_files"]
                total_stats["changed_files"] += project_stats["changed_files"]
                total_stats["deleted_files"] += project_stats["deleted_files"]
                total_stats["errors"] += project_stats["errors"]

            except Exception as e:
                logger.error(
                    f"Error queueing changes for project {project_id} in {root_dir}: {e}",
                    exc_info=True,
                )
                total_stats["errors"] += (
                    len(delta.new_files)
                    + len(delta.changed_files)
                    + len(delta.deleted_files)
                    + err_extra
                )

        return total_stats

    @staticmethod
    def _log_watcher_skip_activity(
        database: Any, project_id: str, reason_activity: str
    ) -> None:
        """Return log watcher skip activity."""
        row = get_project_activity(database, project_id) or {}
        owner_t = row.get("owner_type", "unknown")
        logger.info(
            "[WORKER_COORD] watcher skip project_id=%s reason=%s owner_type=%s",
            project_id,
            reason_activity,
            owner_t,
        )

    def _queue_project_delta(
        self,
        project_id: str,
        delta: FileDelta,
        project_root: Path,
        *,
        watcher_coord: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Queue file changes for a single project (new rows first, then updates, then deletes)."""
        from ..path_normalization import normalize_file_path
        from ..exceptions import ProjectIdMismatchError

        stats: Dict[str, int] = {
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }
        wdb: Optional[Any] = None
        owner_id: Optional[str] = None
        ttl: float = 120.0
        config_path: Optional[Path] = None
        if watcher_coord:
            wdb = watcher_coord.get("database")
            oi = watcher_coord.get("owner_id")
            if isinstance(oi, str) and oi.strip():
                owner_id = oi
            t_raw = watcher_coord.get("lease_ttl", 120.0)
            try:
                ttl = float(t_raw) if t_raw is not None else 120.0
            except (TypeError, ValueError):
                ttl = 120.0
            cp = watcher_coord.get("config_path")
            if cp is not None and isinstance(cp, (str, Path)):
                config_path = Path(cp) if not isinstance(cp, Path) else cp

        has_work = bool(
            delta.new_files
            or delta.changed_files
            or delta.deleted_files
            or delta.ignore_purge_paths
        )
        acquired_lease: bool = False
        if wdb is not None and owner_id and has_work:
            if not try_acquire_project_activity(
                wdb, project_id, "watcher", owner_id, "watcher_staging", ttl
            ):
                self._log_watcher_skip_activity(wdb, project_id, "watcher_staging")
                stats["errors"] += (
                    len(delta.new_files)
                    + len(delta.changed_files)
                    + len(delta.deleted_files)
                    + len(delta.ignore_purge_paths)
                )
                return stats
            acquired_lease = True
        use_lease: bool = bool(acquired_lease)

        def _phase(activity: str) -> bool:
            """Return phase."""
            if not wdb or not owner_id or not use_lease:
                return True
            return try_acquire_project_activity(
                wdb, project_id, "watcher", str(owner_id), activity, float(ttl)
            )

        try:
            _now = sql_julian_timestamp_now_expr(self.database)
            watch_dir_id_queue = _watch_dir_id_for_project(self.database, project_id)

            watch_dirs: List[Path] = list(self.watch_dirs_resolved)
            Row = Tuple[str, str, int, float, bool, str]
            new_rows: List[Row] = []
            changed_rows: List[Row] = []

            def _collect_one(
                file_path_str: str,
                mtime: float,
                _size: int,
                out: List[Row],
            ) -> bool:
                """Return collect one."""
                try:
                    abs_for_norm = _watcher_path_input_to_absolute(
                        file_path_str, project_root
                    )
                    normalized = normalize_file_path(
                        abs_for_norm,
                        watch_dirs=watch_dirs,
                        project_root=project_root,
                    )
                    if normalized.project_id != project_id:
                        raise ProjectIdMismatchError(
                            message=(
                                f"Project ID mismatch: file {normalized.absolute_path}"
                            ),
                            file_project_id=normalized.project_id,
                            db_project_id=project_id,
                        )
                    try:
                        pr = project_root.resolve()
                    except OSError:
                        pr = project_root
                    nabs = Path(normalized.absolute_path).resolve()
                    try:
                        nabs.relative_to(pr)
                    except ValueError:
                        logger.warning(
                            "watcher: reject path outside project root "
                            "project_id=%s path=%s",
                            project_id,
                            normalized.absolute_path,
                        )
                        return False
                    abs_path = normalized.absolute_path
                    rel_posix = relative_path_for_project(abs_path, pr)
                    path_obj = Path(abs_path)
                    lines, has_docstring = collect_file_disk_metadata(path_obj)
                    try:
                        tree_ref, _tree_state = validate_or_recreate_tree_file(
                            project_root=pr,
                            file_path=rel_posix,
                        )
                    except (FileNotFoundError, ValueError, OSError) as e:
                        logger.error(
                            "[QUEUE] TreeLifecycle could not ensure a valid tree "
                            "for batch path %s: %s",
                            abs_path,
                            e,
                            exc_info=True,
                        )
                        return False
                    out.append(
                        (
                            rel_posix,
                            abs_path,
                            lines,
                            mtime,
                            has_docstring,
                            tree_ref.content_checksum,
                        )
                    )
                    return True
                except Exception as e:
                    logger.debug(
                        "Skip batch for %s: %s",
                        file_path_str,
                        e,
                    )
                    return False

            for file_path_str, mtime, size in delta.new_files:
                mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                logger.info(
                    f"[project={project_id}] [NEW FILE] {file_path_str} | "
                    f"mtime: {mtime_str} ({mtime}) | size: {size} bytes"
                )
                if not _collect_one(file_path_str, mtime, size, new_rows):
                    if self._queue_file_for_processing(
                        file_path_str, mtime, project_id, project_root
                    ):
                        stats["new_files"] += 1
                    else:
                        stats["errors"] += 1

            for file_path_str, mtime, size in delta.changed_files:
                mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                logger.info(
                    f"[project={project_id}] [CHANGED FILE] {file_path_str} | "
                    f"mtime: {mtime_str} ({mtime}) | size: {size} bytes"
                )
                if not _collect_one(file_path_str, mtime, size, changed_rows):
                    if self._queue_file_for_processing(
                        file_path_str, mtime, project_id, project_root
                    ):
                        stats["changed_files"] += 1
                    else:
                        stats["errors"] += 1

            if use_lease and wdb and owner_id and has_work:
                if not _phase("watcher_inserting_new_files"):
                    raise RuntimeError("watcher phase inserting_new_files not acquired")
            insert_new_sql = (
                "INSERT INTO files "
                "(id, project_id, watch_dir_id, path, relative_path, lines, last_modified, "
                "has_docstring, tree_checksum, created_at, updated_at) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, {_now}, {_now}) "
                "ON CONFLICT (project_id, path) DO NOTHING"
            )
            update_chunk_sql = f"UPDATE files SET needs_chunking = 1 WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL}"
            n_ins = 0
            for rel_path, abs_path, lines, mtime, has_doc, tree_checksum in new_rows:
                n_ins += 1
                if use_lease and wdb and owner_id and has_work:
                    _watcher_heartbeat_n(
                        wdb,
                        project_id,
                        str(owner_id),
                        "watcher_inserting_new_files",
                        ttl,
                        n_ins,
                    )
                self._db_execute(
                    insert_new_sql,
                    (
                        str(uuid.uuid4()),
                        project_id,
                        watch_dir_id_queue,
                        rel_path,
                        rel_path,
                        lines,
                        mtime,
                        has_doc,
                        tree_checksum,
                    ),
                )
                r1, r2, r3 = file_row_path_match_values(
                    project_root=project_root, absolute_path=abs_path
                )
                rsel = self._db_execute(
                    f"SELECT 1 AS ok FROM files WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL}",
                    (project_id, r1, r2, r3),
                )
                if rsel and (rsel.get("data") or ()):
                    if not file_row_has_live_edit_lock(
                        self.database, project_id=project_id, path=str(abs_path)
                    ):
                        self._db_execute(update_chunk_sql, (project_id, r1, r2, r3))
                stats["new_files"] += 1
            if use_lease and wdb and owner_id and has_work:
                if not _phase("watcher_updating_changed_files"):
                    raise RuntimeError("watcher phase updating_changed not acquired")
            update_changed_sql = (
                "UPDATE files SET lines = ?, last_modified = ?, has_docstring = ?, "
                "tree_checksum = ?, "
                f"deleted = FALSE, updated_at = {_now} "
                f"WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL}"
            )
            n_ch = 0
            for (
                _rel_path,
                abs_path,
                lines,
                mtime,
                has_doc,
                tree_checksum,
            ) in changed_rows:
                n_ch += 1
                if use_lease and wdb and owner_id and has_work:
                    _watcher_heartbeat_n(
                        wdb,
                        project_id,
                        str(owner_id),
                        "watcher_updating_changed_files",
                        ttl,
                        n_ch,
                    )
                if file_row_has_live_edit_lock(
                    self.database, project_id=project_id, path=str(abs_path)
                ):
                    logger.debug(
                        "[QUEUE] skip changed file DB touch (live edit lock): %s",
                        abs_path,
                    )
                    continue
                r1, r2, r3 = file_row_path_match_values(
                    project_root=project_root, absolute_path=abs_path
                )
                self._db_execute(
                    update_changed_sql,
                    (lines, mtime, has_doc, tree_checksum, project_id, r1, r2, r3),
                )
                self._db_execute(update_chunk_sql, (project_id, r1, r2, r3))
                stats["changed_files"] += 1

            if use_lease and wdb and owner_id and has_work:
                if not _phase("watcher_marking_deleted_files"):
                    raise RuntimeError("watcher phase marking_deleted not acquired")

            if delta.ignore_purge_paths:
                abs_ignore_purge = [
                    _watcher_path_input_to_absolute(p, project_root)
                    for p in delta.ignore_purge_paths
                ]
                ids_purge = collect_file_ids_for_active_paths(
                    self.database, project_id, abs_ignore_purge
                )
                if ids_purge:
                    purge = getattr(self.database, "purge_file_ids_cascade", None)
                    if not callable(purge):
                        logger.error(
                            "[QUEUE] ignore purge: database has no purge_file_ids_cascade"
                        )
                        stats["errors"] += len(delta.ignore_purge_paths)
                    else:
                        try:
                            purge(
                                project_id,
                                ids_purge,
                                operation_name="watcher_ignore_purge",
                            )
                        except Exception as e:  # noqa: BLE001
                            logger.error(
                                "ignore purge failed for %s: %s",
                                project_id,
                                e,
                                exc_info=True,
                            )
                            stats["errors"] += len(ids_purge)
                        else:
                            stats["deleted_files"] += len(ids_purge)
                            try_unlink_faiss_index_for_project(project_id, config_path)

            if delta.deleted_files:
                abs_deleted = [
                    _watcher_path_input_to_absolute(p, project_root)
                    for p in delta.deleted_files
                ]
                fids = collect_file_ids_for_active_paths(
                    self.database, project_id, abs_deleted
                )
                for path in delta.deleted_files:
                    logger.info(
                        f"[project={project_id}] [DELETED FILE] {path} | "
                        "action: cascade_purge"
                    )
                if fids:
                    purge = getattr(self.database, "purge_file_ids_cascade", None)
                    if not callable(purge):
                        logger.error(
                            "[QUEUE] deleted_files: database has no purge_file_ids_cascade "
                            "for project=%s",
                            project_id,
                        )
                        stats["errors"] += len(fids)
                    else:
                        try:
                            purge(
                                project_id,
                                fids,
                                operation_name="watcher_deleted_files_purge",
                            )
                            stats["deleted_files"] += len(fids)
                            try_unlink_faiss_index_for_project(project_id, config_path)
                        except Exception as e:  # noqa: BLE001
                            logger.error(
                                "Cascade purge failed for project %s: %s",
                                project_id,
                                e,
                                exc_info=True,
                            )
                            stats["errors"] += len(fids)

            if use_lease and wdb and owner_id and has_work:
                if not _phase("watcher_queueing"):
                    raise RuntimeError("watcher queueing phase not acquired")
        except RuntimeError as coord_err:
            logger.error("watcher queue coordination failed: %s", coord_err)
            stats["errors"] += (
                len(delta.new_files)
                + len(delta.changed_files)
                + len(delta.deleted_files)
                + len(delta.ignore_purge_paths)
            )
        except Exception as e:  # noqa: BLE001
            logger.error(
                "queue failed for project %s: %s",
                project_id,
                e,
                exc_info=True,
            )
            stats["errors"] += (
                len(delta.new_files)
                + len(delta.changed_files)
                + len(delta.deleted_files)
                + len(delta.ignore_purge_paths)
            )
        finally:
            if acquired_lease and wdb and owner_id:
                release_project_activity(wdb, project_id, "watcher", str(owner_id))

        return stats

    def queue_project_bulk_sync(
        self,
        project_id: str,
        _project_root: Path,
        disk_rows: List[Any],
        *,
        watch_dir_id: Optional[str] = None,
        watcher_coord: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        PostgreSQL bulk sync: disk manifest → FULL JOIN → INSERT/UPDATE/purge.

        Falls back to legacy queue with a warning when bulk is unsupported.
        """
        from .watcher_bulk_sync import bulk_sync_supported, submit_watcher_bulk_sync

        stats: Dict[str, Any] = {
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }
        if not bulk_sync_supported(self.database):
            logger.warning(
                "watcher bulk sync not implemented for sqlite; "
                "queue_project_bulk_sync skipped project_id=%s",
                project_id,
            )
            stats["errors"] = 1
            return stats

        wdb: Optional[Any] = None
        owner_id: Optional[str] = None
        ttl: float = 120.0
        if watcher_coord:
            wdb = watcher_coord.get("database")
            oi = watcher_coord.get("owner_id")
            if isinstance(oi, str) and oi.strip():
                owner_id = oi
            t_raw = watcher_coord.get("lease_ttl", 120.0)
            try:
                ttl = float(t_raw) if t_raw is not None else 120.0
            except (TypeError, ValueError):
                ttl = 120.0

        has_work = bool(disk_rows)
        acquired_lease = False
        if wdb is not None and owner_id and has_work:
            if not try_acquire_project_activity(
                wdb, project_id, "watcher", owner_id, "watcher_staging", ttl
            ):
                self._log_watcher_skip_activity(wdb, project_id, "watcher_staging")
                stats["errors"] = 1
                return stats
            acquired_lease = True

        try:
            if wdb and owner_id and acquired_lease:
                if not try_acquire_project_activity(
                    wdb, project_id, "watcher", owner_id, "watcher_queueing", ttl
                ):
                    raise RuntimeError("watcher queueing phase not acquired")
            wd_id = watch_dir_id or _watch_dir_id_for_project(self.database, project_id)
            bulk_stats = submit_watcher_bulk_sync(
                self.database,
                project_id,
                wd_id,
                disk_rows,
            )
            stats.update(bulk_stats)
        except Exception as exc:
            logger.error(
                "bulk sync failed for project %s: %s",
                project_id,
                exc,
                exc_info=True,
            )
            stats["errors"] = 1
        finally:
            if acquired_lease and wdb and owner_id:
                release_project_activity(wdb, project_id, "watcher", str(owner_id))

        return stats

    def _queue_file_for_processing(
        self,
        file_path: str,
        mtime: float,
        project_id: str,
        project_root: Optional[Path] = None,
    ) -> bool:
        """Queue file for processing (add/update in DB, mark needs_chunking)."""
        from ..path_normalization import normalize_file_path
        from ..exceptions import ProjectIdMismatchError
        from code_analysis.core.tree_lifecycle.checksum import (
            validate_or_recreate_tree_file,
        )

        try:
            watch_dirs: List[str | Path] = list(self.watch_dirs_resolved)
            path_for_norm = file_path
            if project_root is not None:
                path_for_norm = _watcher_path_input_to_absolute(file_path, project_root)
            normalized = normalize_file_path(
                path_for_norm,
                watch_dirs=watch_dirs,
                project_root=project_root,
            )
            abs_file_path = normalized.absolute_path

            if normalized.project_id != project_id:
                raise ProjectIdMismatchError(
                    message=(
                        f"Project ID mismatch: file {abs_file_path} belongs to project "
                        f"{normalized.project_id} but was provided with project_id {project_id}"
                    ),
                    file_project_id=normalized.project_id,
                    db_project_id=project_id,
                )

            if file_row_has_live_edit_lock(
                self.database, project_id=project_id, path=str(abs_file_path)
            ):
                logger.debug(
                    "[QUEUE] skip queue (live edit lock): %s",
                    abs_file_path,
                )
                return True

            if project_root is None:
                project_root = normalized.project_root

            if not project_root:
                root_dir = self._get_project_root_dir(project_id, abs_file_path)
                if root_dir:
                    project_root = root_dir

            if not project_root:
                logger.warning(
                    "Could not determine project root for %s; chunking update only",
                    abs_file_path,
                )
                gf = getattr(self.database, "get_file_by_path", None)
                if callable(gf):
                    row = gf(abs_file_path, project_id, include_deleted=False)
                    if row and row.get("id"):
                        self._db_execute(
                            "UPDATE files SET needs_chunking = 1 WHERE id = ?",
                            (row["id"],),
                        )
                return True

            logger.debug(
                "[QUEUE] File normalized: file=%s, project_root=%s, project_id=%s",
                abs_file_path,
                project_root,
                project_id,
            )

            try:
                rel_for_tree = str(
                    Path(abs_file_path)
                    .resolve()
                    .relative_to(Path(project_root).resolve())
                )
            except ValueError:
                rel_for_tree = str(abs_file_path)
            try:
                tree_ref, _tree_state = validate_or_recreate_tree_file(
                    project_root=Path(project_root),
                    file_path=rel_for_tree,
                )
            except (FileNotFoundError, ValueError, OSError) as e:
                logger.error(
                    "[QUEUE] TreeLifecycle could not ensure a valid tree for %s: %s",
                    abs_file_path,
                    e,
                    exc_info=True,
                )
                return False

            try:
                file_record = ensure_file_row_for_disk_path(
                    self.database,
                    project_id,
                    abs_file_path,
                    last_modified=mtime,
                    mark_needs_chunking=True,
                    tree_checksum=tree_ref.content_checksum,
                )
                if not file_record or file_record.get("id") is None:
                    logger.error(
                        "[QUEUE] File not registered after add: %s",
                        abs_file_path,
                    )
                    return False
                file_id = file_record.get("id")
                logger.debug(
                    "[QUEUE] File added/updated: %s | file_id=%s | project_id=%s",
                    abs_file_path,
                    file_id,
                    project_id,
                )
                logger.debug(
                    "[QUEUE] File verified: file_id=%s, path=%s",
                    file_id,
                    file_record.get("path"),
                )
                logger.debug("[QUEUE] File marked for vectorization: %s", abs_file_path)
            except Exception as e:
                logger.error(
                    "[QUEUE] Failed to add/update file: %s (%s)",
                    abs_file_path,
                    e,
                    exc_info=True,
                )
                return False

            return True

        except Exception as e:
            logger.error(
                f"[QUEUE] ✗ Error queueing file {file_path}: {e}",
                exc_info=True,
            )
            return False

    def _get_project_root_dir(self, project_id: str, file_path: str) -> Optional[Path]:
        """Get project root directory for a file."""
        try:
            project_obj = self.database.get_project(project_id)
            root = (
                project_obj.get("root_path")
                if isinstance(project_obj, dict)
                else getattr(project_obj, "root_path", None)
            )
            if root:
                return Path(root)
            abs_path = Path(file_path).resolve()
            for watch_dir in self.watch_dirs_resolved:
                try:
                    abs_path.relative_to(watch_dir)
                    return watch_dir
                except ValueError:
                    continue
            return None
        except Exception as e:
            logger.error(f"Error getting project root dir: {e}", exc_info=True)
            return None
