"""
Base database driver interface.

Defines the interface that all database drivers must implement.
Drivers work with tables, columns, and cells (low-level operations).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class BaseDatabaseDriver(ABC):
    """Base class for all database drivers (DB-agnostic abstraction).

    All drivers must implement table-level operations.
    Drivers work with tables, columns, and cells - not objects.
    Batch execution (execute_batch) is part of the interface with a default
    implementation; concrete drivers may override for DB-specific optimization.
    """

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> None:
        """Establish database connection.

        Args:
            config: Driver-specific configuration dictionary

        Raises:
            DriverConnectionError: If connection fails
        """
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """Close database connection.

        Raises:
            DriverConnectionError: If disconnection fails
        """
        raise NotImplementedError

    @abstractmethod
    def create_table(self, schema: Dict[str, Any]) -> bool:
        """Create database table.

        Args:
            schema: Table schema definition (name, columns, constraints, etc.)

        Returns:
            True if table was created successfully, False otherwise

        Raises:
            DriverOperationError: If operation fails
        """
        raise NotImplementedError

    @abstractmethod
    def drop_table(self, table_name: str) -> bool:
        """Drop database table.

        Args:
            table_name: Name of the table to drop

        Returns:
            True if table was dropped successfully, False otherwise

        Raises:
            DriverOperationError: If operation fails
        """
        raise NotImplementedError

    @abstractmethod
    def insert(self, table_name: str, data: Dict[str, Any]) -> int:
        """Insert row into table.

        Args:
            table_name: Name of the table
            data: Dictionary with column names as keys and values as values

        Returns:
            ID of inserted row (lastrowid)

        Raises:
            DriverOperationError: If operation fails
        """
        raise NotImplementedError

    @abstractmethod
    def update(
        self, table_name: str, where: Dict[str, Any], data: Dict[str, Any]
    ) -> int:
        """Update rows in table.

        Args:
            table_name: Name of the table
            where: Dictionary with conditions (column_name: value)
            data: Dictionary with column names as keys and new values as values

        Returns:
            Number of affected rows

        Raises:
            DriverOperationError: If operation fails
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, table_name: str, where: Dict[str, Any]) -> int:
        """Delete rows from table.

        Args:
            table_name: Name of the table
            where: Dictionary with conditions (column_name: value)

        Returns:
            Number of affected rows

        Raises:
            DriverOperationError: If operation fails
        """
        raise NotImplementedError

    @abstractmethod
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
            table_name: Name of the table
            where: Optional dictionary with conditions (column_name: value)
            columns: Optional list of column names to select (None = all columns)
            limit: Optional maximum number of rows to return
            offset: Optional number of rows to skip
            order_by: Optional list of column names for ordering

        Returns:
            List of dictionaries, each representing a row

        Raises:
            DriverOperationError: If operation fails
        """
        raise NotImplementedError

    @abstractmethod
    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute raw SQL statement.

        Args:
            sql: SQL statement
            params: Optional tuple of parameters for parameterized query
            transaction_id: Optional transaction ID. If provided, uses transaction connection.

        Returns:
            Dictionary with operation result (affected_rows, lastrowid, data, etc.)

        Raises:
            DriverOperationError: If operation fails
        """
        raise NotImplementedError

    def execute_batch(
        self,
        operations: List[Tuple[str, Optional[tuple]]],
        transaction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute multiple SQL statements in one logical batch (universal driver interface).

        Part of the DB-agnostic driver contract. When transaction_id is provided,
        all statements run on the same connection/transaction. Concrete drivers
        may override for DB-specific batch optimization (e.g. native batch APIs);
        this default implementation runs each (sql, params) via execute().

        Args:
            operations: List of (sql, params) tuples; params may be None.
            transaction_id: Optional transaction ID; when set, same connection used.

        Returns:
            List of result dicts (same shape as execute(): affected_rows, lastrowid, data).
        """
        return [self.execute(sql, params, transaction_id) for sql, params in operations]

    @abstractmethod
    def begin_transaction(self) -> str:
        """Begin database transaction.

        Returns:
            Transaction ID (string)

        Raises:
            TransactionError: If transaction cannot be started
        """
        raise NotImplementedError

    @abstractmethod
    def commit_transaction(self, transaction_id: str) -> bool:
        """Commit database transaction.

        Args:
            transaction_id: Transaction ID returned by begin_transaction()

        Returns:
            True if transaction was committed successfully, False otherwise

        Raises:
            TransactionError: If transaction cannot be committed
        """
        raise NotImplementedError

    @abstractmethod
    def rollback_transaction(self, transaction_id: str) -> bool:
        """Rollback database transaction.

        Args:
            transaction_id: Transaction ID returned by begin_transaction()

        Returns:
            True if transaction was rolled back successfully, False otherwise

        Raises:
            TransactionError: If transaction cannot be rolled back
        """
        raise NotImplementedError

    @abstractmethod
    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get information about table columns.

        Args:
            table_name: Name of the table

        Returns:
            List of dictionaries with column information (name, type, nullable, etc.)

        Raises:
            DriverOperationError: If operation fails
        """
        raise NotImplementedError

    @abstractmethod
    def sync_schema(
        self, schema_definition: Dict[str, Any], backup_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """Synchronize database schema.

        Args:
            schema_definition: Complete schema definition (tables, columns, constraints)
            backup_dir: Optional directory for backups before schema changes

        Returns:
            Dictionary with sync results (created_tables, modified_tables, etc.)

        Raises:
            DriverOperationError: If operation fails
        """
        raise NotImplementedError
