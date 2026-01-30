"""
File operations API methods for database client.

Provides object-oriented API methods for File operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional

from .objects.file import File
from .objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
    get_table_name_for_object,
    object_to_db_row,
)


class _ClientAPIFilesMixin:
    """Mixin class with File operation methods."""

    def create_file(self, file: File) -> File:
        """Create new file in database.

        Args:
            file: File object to create

        Returns:
            Created File object with ID and updated timestamps

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If file data is invalid
        """
        table_name = get_table_name_for_object(file)
        if table_name is None:
            raise ValueError("Unknown table for File object")

        data = object_to_db_row(file)
        self.insert(table_name, data)

        # Fetch created file to get all fields including ID and timestamps
        rows = self.select(
            table_name,
            where={
                "project_id": file.project_id,
                "path": file.path,
            },
        )
        if not rows:
            raise ValueError(
                f"Failed to create file {file.path} in project {file.project_id}"
            )

        return db_row_to_object(rows[0], File)

    def get_file(self, file_id: int) -> Optional[File]:
        """Get file by ID.

        Args:
            file_id: File identifier

        Returns:
            File object or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("files", where={"id": file_id})
        if not rows:
            return None

        return db_row_to_object(rows[0], File)

    def update_file(self, file: File) -> File:
        """Update existing file in database.

        Args:
            file: File object with updated data

        Returns:
            Updated File object

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If file not found
        """
        if file.id is None:
            raise ValueError("File id is required for update")

        # Check if file exists
        existing = self.get_file(file.id)
        if existing is None:
            raise ValueError(f"File {file.id} not found")

        # Update file
        data = object_to_db_row(file)
        # Remove id from update data (it's in where clause)
        update_data = {k: v for k, v in data.items() if k != "id"}
        self.update("files", where={"id": file.id}, data=update_data)

        # Fetch updated file
        return self.get_file(file.id) or file

    def delete_file(self, file_id: int) -> bool:
        """Delete file from database.

        Args:
            file_id: File identifier

        Returns:
            True if file was deleted, False if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        affected_rows = self.delete("files", where={"id": file_id})
        return affected_rows > 0

    def get_project_files(
        self, project_id: str, include_deleted: bool = False
    ) -> List[File]:
        """Get all files for a project.

        Args:
            project_id: Project identifier
            include_deleted: Whether to include deleted files

        Returns:
            List of File objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        where = {"project_id": project_id}
        if not include_deleted:
            where["deleted"] = 0

        rows = self.select("files", where=where, order_by=["path"])
        return db_rows_to_objects(rows, File)
