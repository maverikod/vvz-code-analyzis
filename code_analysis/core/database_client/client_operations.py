"""
Database operations methods for client.

Provides CRUD operations (insert, update, delete, select, execute).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..database_driver_pkg.request import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    UpdateRequest,
)


class _ClientOperationsMixin:
    """Mixin class with database operation methods."""

    def insert(self, table_name: str, data: Dict[str, Any]) -> int:
        """Insert row into table.

        Args:
            table_name: Name of table
            data: Row data as dictionary

        Returns:
            Row ID of inserted row

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        request = InsertRequest(table_name=table_name, data=data)
        response = self.rpc_client.call("insert", request.to_dict())
        result_data = self._extract_result_data(response)
        return result_data.get("row_id", 0)

    def update(
        self,
        table_name: str,
        where: Dict[str, Any],
        data: Dict[str, Any],
    ) -> int:
        """Update rows in table.

        Args:
            table_name: Name of table
            where: WHERE clause conditions
            data: Data to update

        Returns:
            Number of affected rows

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        request = UpdateRequest(table_name=table_name, where=where, data=data)
        response = self.rpc_client.call("update", request.to_dict())
        result_data = self._extract_result_data(response)
        return result_data.get("affected_rows", 0)

    def delete(self, table_name: str, where: Dict[str, Any]) -> int:
        """Delete rows from table.

        Args:
            table_name: Name of table
            where: WHERE clause conditions

        Returns:
            Number of affected rows

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        request = DeleteRequest(table_name=table_name, where=where)
        response = self.rpc_client.call("delete", request.to_dict())
        result_data = self._extract_result_data(response)
        return result_data.get("affected_rows", 0)

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Select rows from table.

        Args:
            table_name: Name of table
            where: WHERE clause conditions (optional)
            columns: List of columns to select (optional, None = all)
            limit: Maximum number of rows to return (optional)
            offset: Number of rows to skip (optional)
            order_by: List of columns for ORDER BY (optional)

        Returns:
            List of rows as dictionaries

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        request = SelectRequest(
            table_name=table_name,
            where=where,
            columns=columns,
            limit=limit,
            offset=offset,
            order_by=order_by,
        )
        response = self.rpc_client.call("select", request.to_dict())
        result_data = self._extract_result_data(response)
        # For DataResult, _extract_result_data returns the list directly
        if isinstance(result_data, list):
            return result_data
        # Fallback: return empty list if not a list
        return []

    def execute(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        """Execute raw SQL query.

        Args:
            sql: SQL query string
            params: Optional parameters for query

        Returns:
            Query result as dictionary

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call("execute", {"sql": sql, "params": params})
        return self._extract_result_data(response)
