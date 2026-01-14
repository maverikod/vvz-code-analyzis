"""
Class and Function operations API methods for database client.

Provides object-oriented API methods for Class and Function operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional

from .objects.class_function import Class, Function
from .objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
    get_table_name_for_object,
    object_to_db_row,
)


class _ClientAPIClassesFunctionsMixin:
    """Mixin class with Class and Function operation methods."""

    # ============================================================================
    # Class Operations
    # ============================================================================

    def create_class(self, class_obj: Class) -> Class:
        """Create new class in database.

        Args:
            class_obj: Class object to create

        Returns:
            Created Class object with ID and updated timestamps

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If class data is invalid
        """
        table_name = get_table_name_for_object(class_obj)
        if table_name is None:
            raise ValueError("Unknown table for Class object")

        data = object_to_db_row(class_obj)
        self.insert(table_name, data)

        # Fetch created class
        rows = self.select(
            table_name,
            where={
                "file_id": class_obj.file_id,
                "name": class_obj.name,
                "line": class_obj.line,
            },
        )
        if not rows:
            raise ValueError(
                f"Failed to create class {class_obj.name} in file {class_obj.file_id}"
            )

        return db_row_to_object(rows[0], Class)

    def get_class(self, class_id: int) -> Optional[Class]:
        """Get class by ID.

        Args:
            class_id: Class identifier

        Returns:
            Class object or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("classes", where={"id": class_id})
        if not rows:
            return None

        return db_row_to_object(rows[0], Class)

    def get_file_classes(self, file_id: int) -> List[Class]:
        """Get all classes for a file.

        Args:
            file_id: File identifier

        Returns:
            List of Class objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("classes", where={"file_id": file_id}, order_by=["line"])
        return db_rows_to_objects(rows, Class)

    def search_classes(
        self, project_id: Optional[str] = None, name: Optional[str] = None
    ) -> List[Class]:
        """Search classes by criteria.

        Args:
            project_id: Project identifier (optional)
            name: Class name pattern (optional)

        Returns:
            List of Class objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        where = {}
        if project_id:
            # Need to join with files table, use execute for complex query
            sql = """
                SELECT c.* FROM classes c
                JOIN files f ON c.file_id = f.id
                WHERE f.project_id = ?
            """
            params = [project_id]
            if name:
                sql += " AND c.name LIKE ?"
                params.append(f"%{name}%")
            sql += " ORDER BY c.line"
            result = self.execute(sql, tuple(params))
            rows = result.get("data", [])
        else:
            # Use SQL for LIKE pattern matching when project_id is not specified
            if name:
                sql = "SELECT * FROM classes WHERE name LIKE ? ORDER BY line"
                result = self.execute(sql, (f"%{name}%",))
                rows = result.get("data", [])
            else:
                rows = self.select("classes", order_by=["line"])

        return db_rows_to_objects(rows, Class)

    # ============================================================================
    # Function Operations
    # ============================================================================

    def create_function(self, function: Function) -> Function:
        """Create new function in database.

        Args:
            function: Function object to create

        Returns:
            Created Function object with ID and updated timestamps

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If function data is invalid
        """
        table_name = get_table_name_for_object(function)
        if table_name is None:
            raise ValueError("Unknown table for Function object")

        data = object_to_db_row(function)
        self.insert(table_name, data)

        # Fetch created function
        rows = self.select(
            table_name,
            where={
                "file_id": function.file_id,
                "name": function.name,
                "line": function.line,
            },
        )
        if not rows:
            raise ValueError(
                f"Failed to create function {function.name} in file {function.file_id}"
            )

        return db_row_to_object(rows[0], Function)

    def get_function(self, function_id: int) -> Optional[Function]:
        """Get function by ID.

        Args:
            function_id: Function identifier

        Returns:
            Function object or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("functions", where={"id": function_id})
        if not rows:
            return None

        return db_row_to_object(rows[0], Function)

    def get_file_functions(self, file_id: int) -> List[Function]:
        """Get all functions for a file.

        Args:
            file_id: File identifier

        Returns:
            List of Function objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("functions", where={"file_id": file_id}, order_by=["line"])
        return db_rows_to_objects(rows, Function)

    def search_functions(
        self, project_id: Optional[str] = None, name: Optional[str] = None
    ) -> List[Function]:
        """Search functions by criteria.

        Args:
            project_id: Project identifier (optional)
            name: Function name pattern (optional)

        Returns:
            List of Function objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        if project_id:
            sql = """
                SELECT f.* FROM functions f
                JOIN files fi ON f.file_id = fi.id
                WHERE fi.project_id = ?
            """
            params = [project_id]
            if name:
                sql += " AND f.name LIKE ?"
                params.append(f"%{name}%")
            sql += " ORDER BY f.line"
            result = self.execute(sql, tuple(params))
            rows = result.get("data", [])
        else:
            # Use SQL for LIKE pattern matching when project_id is not specified
            if name:
                sql = "SELECT * FROM functions WHERE name LIKE ? ORDER BY line"
                result = self.execute(sql, (f"%{name}%",))
                rows = result.get("data", [])
            else:
                rows = self.select("functions", order_by=["line"])

        return db_rows_to_objects(rows, Function)
