"""
Class and Function operations API methods for database client.

Provides object-oriented API methods for Class and Function operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional

from .client_base import _DatabaseClientBase
from .objects.class_function import Class
from .objects.mappers import db_rows_to_objects


class _ClientAPIClassesFunctionsMixin(_DatabaseClientBase):
    """Mixin class with Class and Function operation methods."""

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
