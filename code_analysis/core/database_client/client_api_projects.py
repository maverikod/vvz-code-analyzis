"""
Project operations API methods for database client.

Provides object-oriented API methods for Project operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional

from .objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
    get_table_name_for_object,
    object_to_db_row,
)
from .objects.project import Project


class _ClientAPIProjectsMixin:
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

    def list_projects(self) -> List[Project]:
        """List all projects in database.

        Returns:
            List of Project objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("projects", order_by=["created_at"])
        return db_rows_to_objects(rows, Project)
