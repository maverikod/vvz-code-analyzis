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
    build_ignore_purge_logical_write_program,
    collect_file_ids_for_active_paths,
    database_has_sqlite_code_content_fts,
    database_uses_postgres,
    try_unlink_faiss_index_for_project,
)
from .processor_delta import FileDelta

from code_analysis.core.database.file_edit_lock import file_row_has_live_edit_lock
from code_analysis.core.file_identity import (
    FILE_ROW_PATH_MATCH_SQL,
    file_row_path_match_values,
    relative_path_for_project,
)

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
            if not wdb or not owner_id or not use_lease:
                return True
            return try_acquire_project_activity(
                wdb, project_id, "watcher", str(owner_id), activity, float(ttl)
            )

        try:
            watch_dir_id_queue = _watch_dir_id_for_project(self.database, project_id)

            watch_dirs: List[Path] = list(self.watch_dirs_resolved)
            Row = Tuple[str, str, int, float, bool]
            new_rows: List[Row] = []
            changed_rows: List[Row] = []

            def _collect_one(
                file_path_str: str,
                mtime: float,
                _size: int,
                out: List[Row],
            ) -> bool:
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
                    lines = 0
                    has_docstring = False
                    if path_obj.exists() and path_obj.is_file():
                        try:
                            text = path_obj.read_text(encoding="utf-8", errors="ignore")
                            lines = text.count("\n") + (1 if text else 0)
                            stripped = text.lstrip()
                            has_docstring = stripped.startswith(
                                '"""'
                            ) or stripped.startswith("'''")
                        except Exception:
                            pass
                    out.append((rel_posix, abs_path, lines, mtime, has_docstring))
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
                "has_docstring, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, julianday('now'), julianday('now')) "
                "ON CONFLICT (project_id, path) DO NOTHING"
            )
            update_chunk_sql = f"UPDATE files SET needs_chunking = 1 WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL}"
            n_ins = 0
            for rel_path, abs_path, lines, mtime, has_doc in new_rows:
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
                "deleted = FALSE, updated_at = julianday('now') "
                f"WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL}"
            )
            n_ch = 0
            for _rel_path, abs_path, lines, mtime, has_doc in changed_rows:
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
                    (lines, mtime, has_doc, project_id, r1, r2, r3),
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
                    lw = getattr(self.database, "execute_logical_write_operation", None)
                    if lw is None:
                        logger.warning(
                            "[QUEUE] ignore purge: no execute_logical_write_operation"
                        )
                        stats["errors"] += len(delta.ignore_purge_paths)
                    else:
                        program = build_ignore_purge_logical_write_program(
                            project_id,
                            ids_purge,
                            include_code_content_fts=database_has_sqlite_code_content_fts(
                                self.database
                            ),
                            operation_name="watcher_ignore_purge",
                            use_uuid_temp_table=database_uses_postgres(self.database),
                        )
                        try:
                            lw(program)
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
                if fids:
                    ph = ",".join(["?"] * len(fids))
                    self._db_execute(
                        f"DELETE FROM code_chunks WHERE file_id IN ({ph})",
                        tuple(fids),
                    )
                for path in delta.deleted_files:
                    logger.info(
                        f"[project={project_id}] [DELETED FILE] {path} | "
                        f"action: soft_delete"
                    )
                del_sql = (
                    "UPDATE files SET deleted = TRUE, updated_at = julianday('now') "
                    f"WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL}"
                )
                del_ops: List[Tuple[str, Optional[tuple]]] = []
                for path in delta.deleted_files:
                    abs_p = _watcher_path_input_to_absolute(path, project_root)
                    r1, r2, r3 = file_row_path_match_values(
                        project_root=project_root, absolute_path=abs_p
                    )
                    del_ops.append((del_sql, (project_id, r1, r2, r3)))
                try:
                    self._db_execute_batch(del_ops)
                    stats["deleted_files"] += len(delta.deleted_files)
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "Batch delete failed for project %s: %s",
                        project_id,
                        e,
                        exc_info=True,
                    )
                    stats["errors"] += len(delta.deleted_files)

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

            try:
                root_res = project_root.resolve()
            except OSError:
                root_res = project_root

            logger.debug(
                "[QUEUE] File normalized: file=%s, project_root=%s, project_id=%s",
                abs_file_path,
                project_root,
                project_id,
            )

            path_obj = Path(abs_file_path)
            lines = 0
            has_docstring = False
            try:
                if path_obj.exists() and path_obj.is_file():
                    text = path_obj.read_text(encoding="utf-8", errors="ignore")
                    lines = text.count("\n") + (1 if text else 0)
                    stripped = text.lstrip()
                    has_docstring = stripped.startswith('"""') or stripped.startswith(
                        "'''"
                    )
            except Exception:
                logger.debug("Failed to read file for metadata: %s", abs_file_path)

            rel_key = relative_path_for_project(abs_file_path, root_res)
            wdid = _watch_dir_id_for_project(self.database, project_id)

            try:
                self._db_execute(
                    """
                    INSERT INTO files (id, project_id, watch_dir_id, path, relative_path,
                        lines, last_modified, has_docstring, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, julianday('now'), julianday('now'))
                    ON CONFLICT (project_id, path) DO UPDATE SET
                    lines = excluded.lines,
                    last_modified = excluded.last_modified,
                    has_docstring = excluded.has_docstring,
                    deleted = FALSE,
                    updated_at = julianday('now')
                    """,
                    (
                        str(uuid.uuid4()),
                        project_id,
                        wdid,
                        rel_key,
                        rel_key,
                        lines,
                        mtime,
                        has_docstring,
                    ),
                )
                r1, r2, r3 = file_row_path_match_values(
                    project_root=root_res, absolute_path=abs_file_path
                )
                res = self._db_execute(
                    f"SELECT id FROM files WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL} LIMIT 1",
                    (project_id, r1, r2, r3),
                )
                data = res.get("data", []) if isinstance(res, dict) else []
                file_row = data[0] if data else None
                file_id = file_row.get("id", 0) if file_row else 0
                logger.debug(
                    "[QUEUE] File added/updated: %s | file_id=%s | project_id=%s",
                    abs_file_path,
                    file_id,
                    project_id,
                )

                file_record = self.database.get_file_by_id(file_id) if file_id else None
                if not file_record:
                    logger.error(
                        "[QUEUE] File file_id=%s not found after add: %s",
                        file_id,
                        abs_file_path,
                    )
                    return False
                logger.debug(
                    "[QUEUE] File verified: file_id=%s, path=%s",
                    file_id,
                    file_record.get("path"),
                )
                logger.debug(
                    "[QUEUE] Marking for processing: file_id=%s, path=%s",
                    file_id,
                    abs_file_path,
                )
                self._db_execute(
                    f"UPDATE files SET needs_chunking = 1 WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL}",
                    (project_id, r1, r2, r3),
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
