"""
Method and Import operations API methods for database client.

Provides object-oriented API methods for Method, Import operations and relationship navigation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional

from .client_base import _DatabaseClientBase
from .objects.method_import import Method
from .objects.mappers import db_rows_to_objects


class _ClientAPIMethodsImportsMixin(_DatabaseClientBase):
    """Mixin class with Method, Import operation and relationship navigation methods."""

    # ============================================================================
    # Method Operations
    # ============================================================================

    def get_class_methods(self, class_id: int) -> List[Method]:
        """Get all methods for a class.

        Args:
            class_id: Class identifier

        Returns:
            List of Method objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("methods", where={"class_id": class_id}, order_by=["line"])
        return db_rows_to_objects(rows, Method)

    def search_methods(
        self,
        class_id: Optional[int] = None,
        name: Optional[str] = None,
        is_abstract: Optional[bool] = None,
    ) -> List[Method]:
        """Search methods by criteria.

        Args:
            class_id: Class identifier (optional)
            name: Method name pattern (optional)
            is_abstract: Filter by abstract methods (optional)

        Returns:
            List of Method objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        # Use SQL for LIKE pattern matching when name is specified
        if name:
            sql = "SELECT * FROM methods WHERE 1=1"
            params = []
            if class_id:
                sql += " AND class_id = ?"
                params.append(class_id)
            sql += " AND name LIKE ?"
            params.append(f"%{name}%")
            if is_abstract is not None:
                sql += " AND is_abstract = ?"
                params.append(bool(is_abstract))
            sql += " ORDER BY line"
            result = self.execute(sql, tuple(params))
            rows = result.get("data", [])
        else:
            where = {}
            if class_id:
                where["class_id"] = class_id
            if is_abstract is not None:
                where["is_abstract"] = bool(is_abstract)
            rows = self.select("methods", where=where, order_by=["line"])

        return db_rows_to_objects(rows, Method)
