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

from code_analysis.core.project_root_path import (
    enrich_project_dict_resolve_root_path,
    persist_projects_root_path_stored_value,
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
    return out


class _ClientAPIProjectsMixin(_DatabaseClientBase):
    """Mixin class with Project operation methods."""

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
        rows = self.select(table_name, where={"id": project.id})
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
        rows = self.select("projects", where={"id": project_id})
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
        self.update("projects", where={"id": project.id}, data=update_data)

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
        if include_deleted:
            sql = "SELECT p.* FROM projects p ORDER BY p.created_at"
        else:
            _proj_del = f" AND {WHERE_PROJECTS_ACTIVE_P}"
            sql = (
                "SELECT p.* FROM projects p "
                "INNER JOIN ("
                "  SELECT project_id FROM files "
                f"  WHERE {WHERE_FILES_ACTIVE} "
                "  GROUP BY project_id"
                ") a ON p.id = a.project_id" + _proj_del + " UNION "
                "SELECT p.* FROM projects p "
                "WHERE p.id NOT IN (SELECT project_id FROM files)"
                + _proj_del
                + " ORDER BY created_at"
            )
        result = self.execute(sql, ())
        rows = (
            result.get("data", [])
            if isinstance(result, dict)
            else (result if isinstance(result, list) else [])
        )
        return db_rows_to_objects(rows, Project)

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """Get all active (non-soft-deleted) projects as row dicts.

        Matches legacy ``CodeDatabase.get_all_projects`` (used by file watcher init
        and :class:`~code_analysis.core.project_manager.ProjectManager`).

        Returns:
            List of dicts with id, root_path, name, comment, watch_dir_id, updated_at.
        """
        sql = (
            "SELECT p.id, p.root_path, p.name, p.comment, p.watch_dir_id, p.updated_at "
            "FROM projects p "
            "WHERE " + WHERE_FILES_ACTIVE_P + " "
            "AND (NOT EXISTS (SELECT 1 FROM files f WHERE f.project_id = p.id) "
            "   OR EXISTS (SELECT 1 FROM files f WHERE f.project_id = p.id "
            "              AND " + WHERE_FILES_ACTIVE_F + ")) "
            "ORDER BY p.name, p.root_path"
        )
        result = self.execute(sql, ())
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

        if old_r == new_r:
            if new_watch_dir_id is not None:
                self.execute(
                    f"UPDATE projects SET watch_dir_id = ?, updated_at = {now_sql} "
                    "WHERE id = ?",
                    (new_watch_dir_id, project_id),
                )
            return True

        cur = _fetchone("SELECT watch_dir_id FROM projects WHERE id = ?", (project_id,))
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
                "SELECT id FROM projects WHERE watch_dir_id IS NOT NULL AND watch_dir_id = ? "
                "AND root_path = ? AND id != ? LIMIT 1",
                (effective_wd, new_stored, project_id),
            )
        else:
            other = _fetchone(
                "SELECT id FROM projects WHERE root_path = ? AND id != ? LIMIT 1",
                (new_stored, project_id),
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

        if not _fetchone("SELECT id FROM projects WHERE id = ?", (project_id,)):
            logger.warning(
                "relocate_project_root_after_disk_move: project %s not found",
                project_id,
            )
            return False

        new_name = new_r.name
        if new_watch_dir_id is not None:
            self.execute(
                f"UPDATE projects SET root_path = ?, name = ?, watch_dir_id = ?, "
                f"updated_at = {now_sql} WHERE id = ?",
                (new_stored, new_name, new_watch_dir_id, project_id),
            )
        else:
            self.execute(
                f"UPDATE projects SET root_path = ?, name = ?, updated_at = {now_sql} "
                "WHERE id = ?",
                (new_stored, new_name, project_id),
            )

        logger.info(
            "relocate_project_root_after_disk_move: project_id=%s root %s -> %s "
            "(projects row only; file paths unchanged)",
            project_id,
            old_r,
            new_r,
        )
        return True
