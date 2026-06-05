"""
Project operations API methods for database client.

Provides object-oriented API methods for Project operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    """Fetch a ``projects`` row by ``id`` without ``server_instance_id`` filter."""
    return _execute_select_first_row(
        database,
        "SELECT id, server_instance_id, root_path, name, comment, watch_dir_id "
        "FROM projects WHERE id = ? LIMIT 1",
        (project_id,),
        priority=priority,
        transaction_id=transaction_id,
    )


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
                id, server_instance_id, root_path, name, comment, watch_dir_id, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, {_now})
            """,
            (
                project_id,
                sid,
                root_path_stored,
                name,
                comment,
                watch_dir_id,
            ),
            transaction_id=transaction_id,
            priority=priority,
        )

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
        if not rows:
            return None

        row = enrich_project_dict_resolve_root_path(dict(rows[0]), self)
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
        self.update(
            "projects",
            where={"server_instance_id": sid, "id": project.id},
            data=update_data,
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
            r = self.execute(sql, params)
            if not isinstance(r, dict):
                return None
            data = r.get("data")
            if isinstance(data, list) and data:
                row0 = data[0]
                return row0 if isinstance(row0, dict) else None
            return None

        now_sql = sql_julian_timestamp_now_expr(self)
        sid = current_server_instance_id()

        if old_r == new_r:
            if new_watch_dir_id is not None:
                self.execute(
                    f"UPDATE projects SET watch_dir_id = ?, updated_at = {now_sql} "
                    "WHERE server_instance_id = ? AND id = ?",
                    (new_watch_dir_id, sid, project_id),
                )
            return True

        cur = _fetchone(
            "SELECT watch_dir_id FROM projects WHERE server_instance_id = ? AND id = ?",
            (sid, project_id),
        )
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

        if not _fetchone(
            "SELECT id FROM projects WHERE server_instance_id = ? AND id = ?",
            (sid, project_id),
        ):
            logger.warning(
                "relocate_project_root_after_disk_move: project %s not found",
                project_id,
            )
            return False

        new_name = new_r.name
        if new_watch_dir_id is not None:
            self.execute(
                f"UPDATE projects SET root_path = ?, name = ?, watch_dir_id = ?, "
                f"updated_at = {now_sql} WHERE server_instance_id = ? AND id = ?",
                (new_stored, new_name, new_watch_dir_id, sid, project_id),
            )
        else:
            self.execute(
                f"UPDATE projects SET root_path = ?, name = ?, updated_at = {now_sql} "
                "WHERE server_instance_id = ? AND id = ?",
                (new_stored, new_name, sid, project_id),
            )

        logger.info(
            "relocate_project_root_after_disk_move: project_id=%s root %s -> %s "
            "(projects row only; file paths unchanged)",
            project_id,
            old_r,
            new_r,
        )
        return True
