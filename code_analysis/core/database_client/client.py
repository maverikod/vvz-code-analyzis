"""
Database client base class.

Provides object-oriented API for database operations via RPC client.
Converts high-level operations to RPC calls.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..database_driver_pkg.request import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    UpdateRequest,
)
from ..database_driver_pkg.rpc_protocol import RPCResponse
from .exceptions import RPCResponseError
from .rpc_client import RPCClient

logger = logging.getLogger(__name__)


class DatabaseClient:
    """Database client for RPC-based database operations.

    Provides high-level API for database operations by converting
    them to RPC calls through RPCClient.
    """

    def __init__(
        self,
        socket_path: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 0.1,
        pool_size: int = 5,
    ):
        """Initialize database client.

        Args:
            socket_path: Path to Unix socket file
            timeout: Request timeout in seconds (default: 30.0)
            max_retries: Maximum number of retry attempts (default: 3)
            retry_delay: Delay between retries in seconds (default: 0.1)
            pool_size: Connection pool size (default: 5)
        """
        self.rpc_client = RPCClient(
            socket_path=socket_path,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
            pool_size=pool_size,
        )

    def connect(self) -> None:
        """Connect to database driver via RPC."""
        self.rpc_client.connect()

    def disconnect(self) -> None:
        """Disconnect from database driver."""
        self.rpc_client.disconnect()

    def is_connected(self) -> bool:
        """Check if client is connected.

        Returns:
            True if connected, False otherwise
        """
        return self.rpc_client.is_connected()

    def health_check(self) -> bool:
        """Check if database driver is healthy.

        Returns:
            True if driver is healthy, False otherwise
        """
        return self.rpc_client.health_check()

    def create_table(self, schema: Dict[str, Any]) -> bool:
        """Create table.

        Args:
            schema: Table schema definition

        Returns:
            True if table was created successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call("create_table", {"schema": schema})
        return self._extract_success(response)

    def drop_table(self, table_name: str) -> bool:
        """Drop table.

        Args:
            table_name: Name of table to drop

        Returns:
            True if table was dropped successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call("drop_table", {"table_name": table_name})
        return self._extract_success(response)

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
        return result_data.get("data", [])

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

    def begin_transaction(self) -> str:
        """Begin transaction.

        Returns:
            Transaction ID

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call("begin_transaction", {})
        result_data = self._extract_result_data(response)
        return result_data.get("transaction_id", "")

    def commit_transaction(self, transaction_id: str) -> bool:
        """Commit transaction.

        Args:
            transaction_id: Transaction ID

        Returns:
            True if transaction was committed successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call(
            "commit_transaction", {"transaction_id": transaction_id}
        )
        return self._extract_success(response)

    def rollback_transaction(self, transaction_id: str) -> bool:
        """Rollback transaction.

        Args:
            transaction_id: Transaction ID

        Returns:
            True if transaction was rolled back successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call(
            "rollback_transaction", {"transaction_id": transaction_id}
        )
        return self._extract_success(response)

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get table information.

        Args:
            table_name: Name of table

        Returns:
            List of column information dictionaries

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call("get_table_info", {"table_name": table_name})
        result_data = self._extract_result_data(response)
        return result_data.get("data", [])

    def sync_schema(
        self,
        schema_definition: Dict[str, Any],
        backup_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync database schema.

        Args:
            schema_definition: Schema definition dictionary
            backup_dir: Optional backup directory

        Returns:
            Sync results dictionary

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        params: Dict[str, Any] = {"schema_definition": schema_definition}
        if backup_dir:
            params["backup_dir"] = backup_dir
        response = self.rpc_client.call("sync_schema", params)
        return self._extract_result_data(response)

    def _extract_success(self, response: RPCResponse) -> bool:
        """Extract success value from response.

        Args:
            response: RPC response

        Returns:
            Success value

        Raises:
            RPCResponseError: If response contains error
        """
        if response.is_error():
            raise self._create_response_error(response)

        result_data = response.result
        if result_data and isinstance(result_data, dict):
            return result_data.get("success", False)
        return False

    def _extract_result_data(self, response: RPCResponse) -> Dict[str, Any]:
        """Extract result data from response.

        Args:
            response: RPC response

        Returns:
            Result data dictionary

        Raises:
            RPCResponseError: If response contains error
        """
        if response.is_error():
            raise self._create_response_error(response)

        result_data = response.result
        if result_data and isinstance(result_data, dict):
            # Handle both SuccessResult and DataResult formats
            if "data" in result_data:
                # DataResult format: {"success": True, "data": [...]}
                return result_data
            # SuccessResult format: {"success": True, "data": {...}}
            return result_data.get("data", {})
        return {}

    def _create_response_error(self, response: RPCResponse) -> RPCResponseError:
        """Create RPCResponseError from RPC response.

        Args:
            response: RPC response with error

        Returns:
            RPCResponseError instance
        """
        if response.error:
            return RPCResponseError(
                message=response.error.message,
                error_code=response.error.code.value,
                error_data=response.error.data,
            )
        return RPCResponseError(message="Unknown error")
