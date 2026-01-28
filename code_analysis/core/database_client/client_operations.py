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

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute raw SQL query.

        Args:
            sql: SQL query string
            params: Optional parameters for query

        Returns:
            Query result as dictionary. For SELECT queries, contains "data" key with list of rows.
            For other queries, contains "affected_rows" and "lastrowid" keys.

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rpc_params = {"sql": sql, "params": params}
        if transaction_id is not None:
            rpc_params["transaction_id"] = transaction_id
        response = self.rpc_client.call("execute", rpc_params)
        result = self._extract_result_data(response)
        # _extract_result_data() returns the full result dict from RPC
        # For SuccessResult: {"success": True, "data": {"affected_rows": ..., "lastrowid": ..., "data": [...]}}
        # The "data" key contains the actual driver result
        if isinstance(result, dict):
            # Extract the actual driver result from "data" key
            driver_result = result.get("data", {})
            # driver_result should be the full result from driver.execute()
            # For SELECT: {"affected_rows": ..., "lastrowid": ..., "data": [...]}
            # For other: {"affected_rows": ..., "lastrowid": ...}
            if isinstance(driver_result, dict):
                return driver_result
            # Fallback: if not a dict, return empty dict
            return {}
        # Fallback: if result is not a dict, return empty dict
        return {}
