"""
Project operations API methods for database client.

Provides object-oriented API methods for Project operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from code_analysis.core.database.watch_dirs_partition import (
    current_server_instance_id,
    current_server_instance_params,
    sql_projects_server_instance_filter,
)
from code_analysis.core.project_root_path import (
    enrich_project_dict_resolve_root_path,
    normalize_path_simple,
    persist_projects_root_path_stored_value,
    resolve_project_root_absolute_str,
)

from ..sql_portable import (
    WHERE_FILES_ACTIVE,
    WHERE_FILES_ACTIVE_F,
    WHERE_FILES_ACTIVE_P,
    WHERE_PROJECTS_ACTIVE_P,
    sql_julian_timestamp_now_expr,
)
from .client_base import _DatabaseClientBase
from .objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
    get_table_name_for_object,
    object_to_db_row,
)
from .objects.project import Project

logger = logging.getLogger(__name__)


def _execute_select_first_row(
    database: Any,
    sql: str,
    params: tuple[Any, ...],
    *,
    priority: int = 0,
    transaction_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Run SELECT via DatabaseClient.execute and return the first row dict."""
    result = database.execute(
        sql,
        params,
        transaction_id=transaction_id,
        priority=priority,
    )
    if not isinstance(result, dict):
        return None
    rows = result.get("data")
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    return dict(row) if isinstance(row, dict) else None


def _project_row_by_id_global(
    database: Any,
    project_id: str,
    *,
    priority: int = 0,
    transaction_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch a ``projects`` row by ``id`` without ``server_instance_id`` filter.

    Selects every column (not a fixed subset) so callers that need a fully
    hydrated row - e.g. ``get_project``'s scoped-miss fallback - can build a
    complete :class:`~code_analysis.core.database_client.objects.project.Project`
    from it, not just the columns ``insert_project_row``'s reclaim path reads.
    """
    return _execute_select_first_row(
        database,
        "SELECT * FROM projects WHERE id = ? LIMIT 1",
        (project_id,),
        priority=priority,
        transaction_id=transaction_id,
    )


def _reclaim_orphan_and_retry_scoped_projects_write(
    database: Any,
    *,
    sid: str,
    project_id: str,
    write_fn: "Callable[[], int]",
    priority: int = 0,
    transaction_id: Optional[str] = None,
) -> int:
    """Run a ``projects`` write scoped to ``(server_instance_id, id)``; reclaim orphans.

    ``write_fn`` performs one scoped UPDATE/DELETE against ``projects`` (filtered by
    ``server_instance_id = sid AND id = project_id``) and returns the affected row
    count. A ``projects`` row can exist under a different/rotated
    ``server_instance_id`` (orphan instance after a server reinstall/rebind) while
    still being the same on-disk project - ``get_project``'s global-by-id fallback
    (``_project_row_by_id_global``) already reads around this for lookups. Without
    an equivalent on the write side, a scoped write against such a row silently
    affects 0 rows with no error, while callers that resolved the project via
    ``get_project`` believe it exists and the write succeeded.

    If ``write_fn`` affects 0 rows AND a ``projects`` row for ``project_id`` exists
    globally under a different ``server_instance_id``, reclaim the row to ``sid``
    (same semantics as ``insert_project_row``'s orphan reclaim) and retry
    ``write_fn`` once. Returns the final affected-row count (0 when the row is
    genuinely absent, or when it already belonged to ``sid`` and legitimately
    matched nothing).
    """
    affected = write_fn()
    if affected:
        return affected
    global_row = _project_row_by_id_global(
        database, project_id, priority=priority, transaction_id=transaction_id
    )
    if global_row is None:
        return 0
    other_sid = global_row.get("server_instance_id")
    if other_sid == sid:
        return 0
    database.update(
        "projects",
        where={"id": project_id},
        data={"server_instance_id": sid},
    )
    return write_fn()


def _resolved_project_root_norm(
    database: Any,
    *,
    project_id: str,
    root_path_stored: Optional[str],
    watch_dir_id: Optional[str],
    project_name: Optional[str] = None,
) -> str:
    """Normalized absolute project root for same-disk comparisons (RPC-only reads)."""
    try:
        resolved = resolve_project_root_absolute_str(
            project_id=project_id or None,
            root_path_stored=root_path_stored,
            watch_dir_id=(
                str(watch_dir_id).strip()
                if watch_dir_id is not None and str(watch_dir_id).strip()
                else None
            ),
            project_name=project_name,
            database=database,
            require_exists=False,
        )
    except Exception:
        return ""
    if not resolved:
        return ""
    return normalize_path_simple(resolved)


def _project_row_root_path_for_write(
    database: Any, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Normalize ``root_path`` for DB insert/update (segment under watch when applicable)."""
    out = dict(data)
    rp = out.get("root_path")
    if rp is None or str(rp).strip() == "":
        return out
    wd = out.get("watch_dir_id")
    out["root_path"] = persist_projects_root_path_stored_value(
        project_root_absolute=Path(str(rp)),
        watch_dir_id=str(wd).strip() if wd is not None and str(wd).strip() else None,
        database=database,
    )
    if not out.get("server_instance_id"):
        out["server_instance_id"] = current_server_instance_id()
    return out


class _ClientAPIProjectsMixin(_DatabaseClientBase):
    """Mixin class with Project operation methods."""

    def insert_project_row(
        self,
        project_id: str,
        root_path_stored: str,
        name: str,
        *,
        comment: Optional[str] = None,
        watch_dir_id: Optional[str] = None,
        transaction_id: Optional[str] = None,
        priority: int = 0,
        deleted: bool = False,
        processing_paused: bool = False,
    ) -> None:
        """Insert or reclaim a ``projects`` row for the current server instance via RPC.

        Lookup and writes go only through ``DatabaseClient.execute`` (RPC → driver → DB).
        """
        sid = current_server_instance_id()
        _now = sql_julian_timestamp_now_expr(self)

        if self.get_project(project_id) is not None:
            return

        global_row = _project_row_by_id_global(
            self,
            project_id,
            priority=priority,
            transaction_id=transaction_id,
        )
        if global_row is not None:
            other_sid = global_row.get("server_instance_id")
            other_sid_str = str(other_sid).strip() if other_sid is not None else ""
            if not other_sid_str:
                self.execute(
                    f"""
                    UPDATE projects
                    SET server_instance_id = ?, root_path = ?, name = ?, comment = ?,
                        watch_dir_id = ?, updated_at = {_now}
                    WHERE id = ?
                      AND (server_instance_id IS NULL OR server_instance_id = '')
                    """,
                    (
                        sid,
                        root_path_stored,
                        name,
                        comment,
                        watch_dir_id,
                        project_id,
                    ),
                    transaction_id=transaction_id,
                    priority=priority,
                )
                logger.info(
                    "Reclaimed orphan projects row id=%s for server_instance_id=%s",
                    project_id,
                    sid,
                )
                return
            if other_sid_str != sid:
                incoming_root = _resolved_project_root_norm(
                    self,
                    project_id=project_id,
                    root_path_stored=root_path_stored,
                    watch_dir_id=watch_dir_id,
                    project_name=name,
                )
                existing_root = _resolved_project_root_norm(
                    self,
                    project_id=project_id,
                    root_path_stored=str(global_row.get("root_path") or ""),
                    watch_dir_id=(
                        str(global_row["watch_dir_id"])
                        if global_row.get("watch_dir_id") is not None
                        else None
                    ),
                    project_name=str(global_row.get("name") or "") or None,
                )
                if incoming_root and existing_root and incoming_root == existing_root:
                    self.execute(
                        f"""
                        UPDATE projects
                        SET server_instance_id = ?, root_path = ?, name = ?, comment = ?,
                            watch_dir_id = ?, updated_at = {_now}
                        WHERE id = ?
                          AND server_instance_id = ?
                        """,
                        (
                            sid,
                            root_path_stored,
                            name,
                            comment,
                            watch_dir_id,
                            project_id,
                            other_sid_str,
                        ),
                        transaction_id=transaction_id,
                        priority=priority,
                    )
                    logger.info(
                        "Reassigned projects row id=%s from server_instance_id=%s "
                        "to %s (same disk root %s)",
                        project_id,
                        other_sid_str,
                        sid,
                        incoming_root,
                    )
                    return
                raise ValueError(
                    f"Project id {project_id} is already registered under "
                    f"server_instance_id={other_sid_str} (current instance {sid}). "
                    "Cannot insert the same project UUID for another server instance "
                    "while projects.id remains a global primary key."
                )
            return

        self.execute(
            f"""
            INSERT INTO projects (
                id, server_instance_id, root_path, name, comment, watch_dir_id,
                deleted, processing_paused, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, {_now})
            """,
            (
                project_id,
                sid,
                root_path_stored,
                name,
                comment,
                watch_dir_id,
                bool(deleted),
                bool(processing_paused),
            ),
            transaction_id=transaction_id,
            priority=priority,
        )

    def sync_project_metadata_from_projectid(
        self,
        root_dir: str | Path,
        *,
        transaction_id: Optional[str] = None,
        priority: int = 0,
    ) -> Optional[str]:
        """Sync ``projects.deleted``, ``processing_paused``, ``comment`` from ``projectid``."""
        from code_analysis.core.project_resolution import load_project_info

        try:
            info = load_project_info(root_dir)
        except Exception as e:
            logger.warning(
                "sync_project_metadata_from_projectid: cannot load projectid at %s: %s",
                root_dir,
                e,
            )
            return None

        sid = current_server_instance_id()

        def _write() -> int:
            """Run the scoped UPDATE once; return affected row count."""
            result = self.execute(
                """
                UPDATE projects
                SET deleted = ?,
                    processing_paused = ?,
                    comment = ?
                WHERE server_instance_id = ? AND id = ?
                """,
                (
                    bool(info.deleted),
                    bool(info.processing_paused),
                    info.description or None,
                    sid,
                    info.project_id,
                ),
                transaction_id=transaction_id,
                priority=priority,
            )
            affected_rows = (
                result.get("affected_rows", 0) if isinstance(result, dict) else 0
            )
            return int(affected_rows) if isinstance(affected_rows, int) else 0

        _reclaim_orphan_and_retry_scoped_projects_write(
            self,
            sid=sid,
            project_id=info.project_id,
            write_fn=_write,
            priority=priority,
            transaction_id=transaction_id,
        )
        return info.project_id

    def create_project(self, project: Project) -> Project:
        """Create new project in database.

        Args:
            project: Project object to create

        Returns:
            Created Project object with updated timestamps

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If project data is invalid
        """
        table_name = get_table_name_for_object(project)
        if table_name is None:
            raise ValueError("Unknown table for Project object")

        data = _project_row_root_path_for_write(self, object_to_db_row(project))
        self.insert(table_name, data)

        # Fetch created project to get all fields including timestamps
        sid = current_server_instance_id()
        rows = self.select(
            table_name,
            where={"server_instance_id": sid, "id": project.id},
        )
        if not rows:
            raise ValueError(f"Failed to create project {project.id}")

        row = enrich_project_dict_resolve_root_path(dict(rows[0]), self)
        return db_row_to_object(row, Project)

    def get_project(self, project_id: str) -> Optional[Project]:
        """Get project by ID.

        Looks up ``project_id`` scoped to the current ``server_instance_id``
        first. When that scoped lookup misses, falls back to an unscoped
        global-by-id lookup (:func:`_project_row_by_id_global`): a
        ``projects`` row can exist under a different/rotated
        ``server_instance_id`` (orphan instance after a server
        reinstall/rebind) while still being the same on-disk project.
        Without this fallback, ``get_project`` could disagree with
        unscoped readers (e.g. ``BaseMCPCommand._resolve_project_root``)
        about whether the project exists.

        Args:
            project_id: Project identifier

        Returns:
            Project object or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        sid = current_server_instance_id()
        rows = self.select(
            "projects",
            where={"server_instance_id": sid, "id": project_id},
        )
        if rows:
            row = enrich_project_dict_resolve_root_path(dict(rows[0]), self)
            return db_row_to_object(row, Project)

        global_row = _project_row_by_id_global(self, project_id)
        if global_row is None:
            return None
        row = enrich_project_dict_resolve_root_path(dict(global_row), self)
        return db_row_to_object(row, Project)

    def update_project(self, project: Project) -> Project:
        """Update existing project in database.

        Args:
            project: Project object with updated data

        Returns:
            Updated Project object

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If project not found
        """
        # Check if project exists
        existing = self.get_project(project.id)
        if existing is None:
            raise ValueError(f"Project {project.id} not found")

        # Update project
        data = _project_row_root_path_for_write(self, object_to_db_row(project))
        # Remove id from update data (it's in where clause)
        update_data = {k: v for k, v in data.items() if k != "id"}
        sid = current_server_instance_id()
        _reclaim_orphan_and_retry_scoped_projects_write(
            self,
            sid=sid,
            project_id=project.id,
            write_fn=lambda: self.update(
                "projects",
                where={"server_instance_id": sid, "id": project.id},
                data=update_data,
            ),
        )

        # Fetch updated project
        return self.get_project(project.id) or project

    def delete_project(self, project_id: str) -> bool:
        """Delete project from database.

        Args:
            project_id: Project identifier

        Returns:
            True if project was deleted, False if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        affected_rows = self.delete("projects", where={"id": project_id})
        return affected_rows > 0

    def list_projects(self, *, include_deleted: bool = False) -> List[Project]:
        """List projects in database.

        By default excludes rows with ``projects.deleted`` set (soft-deleted / trash),
        matching MCP ``list_projects``. A project is also listed if it has no file rows
        or has at least one non-deleted file (``WHERE_FILES_ACTIVE`` on ``files``).

        When ``include_deleted`` is true, returns **all** rows from ``projects`` (active
        and soft-deleted), including projects whose files are all trashed — required for
        trash lifecycle after ``project_set_mark_del(delete_from_disk=True)``.

        Args:
            include_deleted: When true, include soft-deleted project rows.

        Returns:
            List of Project objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        sid_params = current_server_instance_params()
        if include_deleted:
            sql = (
                "SELECT p.* FROM projects p "
                "WHERE p.server_instance_id = ? ORDER BY p.created_at"
            )
            list_params: tuple[Any, ...] = sid_params
        else:
            _proj_del = f" AND {WHERE_PROJECTS_ACTIVE_P}"
            sql = (
                "SELECT p.* FROM projects p "
                "WHERE p.server_instance_id = ? "
                "AND p.id IN ("
                "  SELECT project_id FROM files "
                f"  WHERE {WHERE_FILES_ACTIVE} "
                "  GROUP BY project_id"
                ")" + _proj_del + " UNION "
                "SELECT p.* FROM projects p "
                "WHERE p.server_instance_id = ? "
                "AND p.id NOT IN (SELECT project_id FROM files)"
                + _proj_del
                + " ORDER BY created_at"
            )
            list_params = sid_params + sid_params
        result = self.execute(sql, list_params)
        rows = (
            result.get("data", [])
            if isinstance(result, dict)
            else (result if isinstance(result, list) else [])
        )
        enriched = [enrich_project_dict_resolve_root_path(dict(r), self) for r in rows]
        return db_rows_to_objects(enriched, Project)

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """Get all active (non-soft-deleted) projects as row dicts.

        Matches legacy ``CodeDatabase.get_all_projects`` (used by file watcher init
        and :class:`~code_analysis.core.project_manager.ProjectManager`).

        Returns:
            List of dicts with id, root_path, name, comment, watch_dir_id, updated_at.
        """
        proj_where, proj_params = sql_projects_server_instance_filter("p")
        sql = (
            "SELECT p.id, p.root_path, p.name, p.comment, p.watch_dir_id, p.updated_at "
            "FROM projects p "
            f"WHERE {proj_where} AND " + WHERE_FILES_ACTIVE_P + " "
            "AND (NOT EXISTS (SELECT 1 FROM files f WHERE f.project_id = p.id) "
            "   OR EXISTS (SELECT 1 FROM files f WHERE f.project_id = p.id "
            "              AND " + WHERE_FILES_ACTIVE_F + ")) "
            "ORDER BY p.name, p.root_path"
        )
        result = self.execute(sql, proj_params)
        rows = (
            result.get("data", [])
            if isinstance(result, dict)
            else (result if isinstance(result, list) else [])
        )
        return rows if rows else []

    def relocate_project_root_after_disk_move(
        self,
        project_id: str,
        old_root_path: str,
        new_root_path: str,
        new_watch_dir_id: Optional[str] = None,
    ) -> bool:
        """
        Same project UUID, new directory under a watch root: update only ``projects``.

        Optionally sets ``watch_dir_id``. File rows are not updated; paths stay
        project-relative.

        ``projects`` reads/writes here are scoped to the current
        ``server_instance_id``. A row can exist under a different/rotated
        ``server_instance_id`` (orphan instance after a server reinstall/rebind)
        while still being the same on-disk project - reads fall back to the
        unscoped global-by-id lookup (:func:`_project_row_by_id_global`, mirrors
        ``get_project``'s fallback) and writes reclaim the orphan row before
        retrying (:func:`_reclaim_orphan_and_retry_scoped_projects_write`, same
        helper ``update_project``/``sync_project_metadata_from_projectid`` use).
        """
        try:
            old_r = Path(old_root_path).expanduser().resolve()
            new_r = Path(new_root_path).expanduser().resolve()
        except OSError as e:
            logger.warning(
                "relocate_project_root_after_disk_move: cannot resolve old=%s new=%s: %s",
                old_root_path,
                new_root_path,
                e,
            )
            return False

        def _fetchone(sql: str, params: tuple[Any, ...]) -> Optional[Dict[str, Any]]:
            """Return fetchone."""
            r = self.execute(sql, params)
            if not isinstance(r, dict):
                return None
            data = r.get("data")
            if isinstance(data, list) and data:
                row0 = data[0]
                return row0 if isinstance(row0, dict) else None
            return None

        def _affected_rows(result: Any) -> int:
            """Return ``affected_rows`` from a ``self.execute`` UPDATE result."""
            affected = result.get("affected_rows", 0) if isinstance(result, dict) else 0
            return int(affected) if isinstance(affected, int) else 0

        now_sql = sql_julian_timestamp_now_expr(self)
        sid = current_server_instance_id()

        if old_r == new_r:
            if new_watch_dir_id is not None:

                def _write_watch_dir_only() -> int:
                    """Scoped ``watch_dir_id``-only UPDATE; returns affected row count."""
                    return _affected_rows(
                        self.execute(
                            f"UPDATE projects SET watch_dir_id = ?, "
                            f"updated_at = {now_sql} "
                            "WHERE server_instance_id = ? AND id = ?",
                            (new_watch_dir_id, sid, project_id),
                        )
                    )

                _reclaim_orphan_and_retry_scoped_projects_write(
                    self,
                    sid=sid,
                    project_id=project_id,
                    write_fn=_write_watch_dir_only,
                )
            return True

        cur = _fetchone(
            "SELECT watch_dir_id FROM projects WHERE server_instance_id = ? AND id = ?",
            (sid, project_id),
        )
        if cur is None:
            global_cur = _project_row_by_id_global(self, project_id)
            if global_cur is not None:
                cur = global_cur
        effective_wd = (
            str(new_watch_dir_id)
            if new_watch_dir_id is not None
            else (
                str(cur.get("watch_dir_id"))
                if isinstance(cur, dict) and cur.get("watch_dir_id")
                else ""
            )
        )
        new_stored = persist_projects_root_path_stored_value(
            project_root_absolute=new_r,
            watch_dir_id=effective_wd or None,
            database=self,
        )
        if effective_wd:
            other = _fetchone(
                "SELECT id FROM projects WHERE server_instance_id = ? "
                "AND watch_dir_id IS NOT NULL AND watch_dir_id = ? "
                "AND root_path = ? AND id != ? LIMIT 1",
                (sid, effective_wd, new_stored, project_id),
            )
        else:
            other = _fetchone(
                "SELECT id FROM projects WHERE server_instance_id = ? "
                "AND root_path = ? AND id != ? LIMIT 1",
                (sid, new_stored, project_id),
            )
        if other:
            logger.error(
                "relocate_project_root_after_disk_move: root_path %s already used by "
                "project %s; refusing to move project %s from %s",
                new_stored,
                other.get("id"),
                project_id,
                old_r,
            )
            return False

        if (
            _fetchone(
                "SELECT id FROM projects WHERE server_instance_id = ? AND id = ?",
                (sid, project_id),
            )
            is None
            and _project_row_by_id_global(self, project_id) is None
        ):
            logger.warning(
                "relocate_project_root_after_disk_move: project %s not found",
                project_id,
            )
            return False

        new_name = new_r.name
        if new_watch_dir_id is not None:

            def _write_root() -> int:
                """Scoped root-relocation UPDATE incl. ``watch_dir_id``."""
                return _affected_rows(
                    self.execute(
                        f"UPDATE projects SET root_path = ?, name = ?, watch_dir_id = ?, "
                        f"updated_at = {now_sql} WHERE server_instance_id = ? AND id = ?",
                        (new_stored, new_name, new_watch_dir_id, sid, project_id),
                    )
                )

        else:

            def _write_root() -> int:
                """Scoped root-relocation UPDATE (``watch_dir_id`` unchanged)."""
                return _affected_rows(
                    self.execute(
                        f"UPDATE projects SET root_path = ?, name = ?, "
                        f"updated_at = {now_sql} "
                        "WHERE server_instance_id = ? AND id = ?",
                        (new_stored, new_name, sid, project_id),
                    )
                )

        _reclaim_orphan_and_retry_scoped_projects_write(
            self,
            sid=sid,
            project_id=project_id,
            write_fn=_write_root,
        )

        logger.info(
            "relocate_project_root_after_disk_move: project_id=%s root %s -> %s "
            "(projects row only; file paths unchanged)",
            project_id,
            old_r,
            new_r,
        )
        return True
