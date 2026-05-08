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

        data = object_to_db_row(project)
        self.insert(table_name, data)

        # Fetch created project to get all fields including timestamps
        rows = self.select(table_name, where={"id": project.id})
        if not rows:
            raise ValueError(f"Failed to create project {project.id}")

        return db_row_to_object(rows[0], Project)

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

        return db_row_to_object(rows[0], Project)

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
        data = object_to_db_row(project)
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

        other = _fetchone(
            "SELECT id FROM projects WHERE root_path = ? AND id != ? LIMIT 1",
            (str(new_r), project_id),
        )
        if other:
            logger.error(
                "relocate_project_root_after_disk_move: root_path %s already used by "
                "project %s; refusing to move project %s from %s",
                new_r,
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
                (str(new_r), new_name, new_watch_dir_id, project_id),
            )
        else:
            self.execute(
                f"UPDATE projects SET root_path = ?, name = ?, updated_at = {now_sql} "
                "WHERE id = ?",
                (str(new_r), new_name, project_id),
            )

        logger.info(
            "relocate_project_root_after_disk_move: project_id=%s root %s -> %s "
            "(projects row only; file paths unchanged)",
            project_id,
            old_r,
            new_r,
        )
        return True
