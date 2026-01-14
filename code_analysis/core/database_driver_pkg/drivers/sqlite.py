"""
SQLite driver implementation for database driver process.

Works with tables, columns, and cells (low-level operations).
This driver runs in the driver process and handles table-level operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..exceptions import DriverConnectionError, DriverOperationError
from .base import BaseDatabaseDriver
from .sqlite_operations import SQLiteOperations
from .sqlite_schema import SQLiteSchemaManager
from .sqlite_transactions import SQLiteTransactionManager

logger = logging.getLogger(__name__)


class SQLiteDriver(BaseDatabaseDriver):
    """SQLite driver for database driver process.

    Works with tables directly (insert, update, delete, select).
    All operations are table-level, not object-level.
    """

    def __init__(self) -> None:
        """Initialize SQLite driver."""
        self.conn: Optional[sqlite3.Connection] = None
        self.db_path: Optional[Path] = None
        self._transaction_manager: Optional[SQLiteTransactionManager] = None
        self._schema_manager: Optional[SQLiteSchemaManager] = None
        self._operations: Optional[SQLiteOperations] = None

    def connect(self, config: Dict[str, Any]) -> None:
        """Establish SQLite connection.

        Args:
            config: Configuration dict with 'path' key pointing to database file

        Raises:
            DriverConnectionError: If connection fails
        """
        if "path" not in config:
            raise DriverConnectionError("SQLite driver requires 'path' in config")

        try:
            self.db_path = Path(config["path"]).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Create connection
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self.conn.execute("PRAGMA foreign_keys = ON")
            # Enable WAL mode for better concurrency
            try:
                self.conn.execute("PRAGMA journal_mode = WAL")
            except Exception as e:
                # WAL might not be supported in some SQLite configurations
                # Log warning but continue - database will work without WAL
                logger.warning(
                    f"Failed to enable WAL mode for database {self.db_path}: {e}. "
                    "Continuing without WAL mode."
                )

            # Initialize managers
            self._transaction_manager = SQLiteTransactionManager(self.db_path)
            self._schema_manager = SQLiteSchemaManager(self.conn)
            self._operations = SQLiteOperations(self.conn)
        except Exception as e:
            raise DriverConnectionError(f"Failed to connect to database: {e}") from e

    def disconnect(self) -> None:
        """Close SQLite connection.

        Raises:
            DriverConnectionError: If disconnection fails
        """
        try:
            # Close all transactions
            if self._transaction_manager:
                self._transaction_manager.close_all()

            if self.conn:
                self.conn.close()
                self.conn = None
        except Exception as e:
            raise DriverConnectionError(f"Failed to disconnect: {e}") from e

    def create_table(self, schema: Dict[str, Any]) -> bool:
        """Create database table.

        Args:
            schema: Table schema definition with keys:
                - name: Table name
                - columns: List of column definitions (name, type, nullable, default, etc.)
                - constraints: Optional list of constraints (primary_key, foreign_key, etc.)

        Returns:
            True if table was created successfully, False otherwise

        Raises:
            DriverOperationError: If operation fails
        """
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        try:
            table_name = schema.get("name")
            if not table_name:
                raise DriverOperationError("Table name is required in schema")

            columns = schema.get("columns", [])
            if not columns:
                raise DriverOperationError("At least one column is required")

            # Build CREATE TABLE SQL
            column_defs = []
            for col in columns:
                col_name = col.get("name")
                col_type = col.get("type", "TEXT")
                nullable = col.get("nullable", True)
                default = col.get("default")
                primary_key = col.get("primary_key", False)

                col_def = f"{col_name} {col_type}"
                if not nullable:
                    col_def += " NOT NULL"
                if default is not None:
                    if isinstance(default, str):
                        col_def += f" DEFAULT '{default}'"
                    else:
                        col_def += f" DEFAULT {default}"
                if primary_key:
                    col_def += " PRIMARY KEY"

                column_defs.append(col_def)

            # Add constraints
            constraints = schema.get("constraints", [])
            for constraint in constraints:
                if constraint.get("type") == "primary_key":
                    cols = constraint.get("columns", [])
                    if cols:
                        column_defs.append(f"PRIMARY KEY ({', '.join(cols)})")
                elif constraint.get("type") == "foreign_key":
                    cols = constraint.get("columns", [])
                    ref_table = constraint.get("references_table")
                    ref_cols = constraint.get("references_columns", [])
                    if cols and ref_table and ref_cols:
                        column_defs.append(
                            f"FOREIGN KEY ({', '.join(cols)}) "
                            f"REFERENCES {ref_table} ({', '.join(ref_cols)})"
                        )

            sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(column_defs)})"
            self.conn.execute(sql)
            self.conn.commit()
            return True
        except Exception as e:
            raise DriverOperationError(f"Failed to create table: {e}") from e

    def drop_table(self, table_name: str) -> bool:
        """Drop database table.

        Args:
            table_name: Name of the table to drop

        Returns:
            True if table was dropped successfully, False otherwise

        Raises:
            DriverOperationError: If operation fails
        """
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        try:
            sql = f"DROP TABLE IF EXISTS {table_name}"
            self.conn.execute(sql)
            self.conn.commit()
            return True
        except Exception as e:
            raise DriverOperationError(f"Failed to drop table: {e}") from e

    def insert(self, table_name: str, data: Dict[str, Any]) -> int:
        """Insert row into table."""
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        return self._operations.insert(table_name, data)

    def update(
        self, table_name: str, where: Dict[str, Any], data: Dict[str, Any]
    ) -> int:
        """Update rows in table."""
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        return self._operations.update(table_name, where, data)

    def delete(self, table_name: str, where: Dict[str, Any]) -> int:
        """Delete rows from table."""
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        return self._operations.delete(table_name, where)

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Select rows from table."""
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        return self._operations.select(
            table_name, where, columns, limit, offset, order_by
        )

    def execute(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        """Execute raw SQL statement.

        Args:
            sql: SQL statement
            params: Optional tuple of parameters for parameterized query

        Returns:
            Dictionary with operation result (affected_rows, lastrowid, data, etc.)

        Raises:
            DriverOperationError: If operation fails
        """
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        try:
            cursor = self.conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            result: Dict[str, Any] = {
                "affected_rows": cursor.rowcount,
                "lastrowid": cursor.lastrowid,
            }

            # If it's a SELECT statement, fetch data
            if sql.strip().upper().startswith("SELECT"):
                rows = cursor.fetchall()
                result["data"] = [dict(row) for row in rows]

            self.conn.commit()
            return result
        except Exception as e:
            self.conn.rollback()
            raise DriverOperationError(f"Failed to execute SQL: {e}") from e

    def begin_transaction(self) -> str:
        """Begin database transaction.

        Returns:
            Transaction ID (string)

        Raises:
            TransactionError: If transaction cannot be started
        """
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.begin_transaction()

    def commit_transaction(self, transaction_id: str) -> bool:
        """Commit database transaction.

        Args:
            transaction_id: Transaction ID returned by begin_transaction()

        Returns:
            True if transaction was committed successfully, False otherwise

        Raises:
            TransactionError: If transaction cannot be committed
        """
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.commit_transaction(transaction_id)

    def rollback_transaction(self, transaction_id: str) -> bool:
        """Rollback database transaction.

        Args:
            transaction_id: Transaction ID returned by begin_transaction()

        Returns:
            True if transaction was rolled back successfully, False otherwise

        Raises:
            TransactionError: If transaction cannot be rolled back
        """
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.rollback_transaction(transaction_id)

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get information about table columns.

        Args:
            table_name: Name of the table

        Returns:
            List of dictionaries with column information (name, type, nullable, etc.)

        Raises:
            DriverOperationError: If operation fails
        """
        if not self._schema_manager:
            raise DriverOperationError("Schema manager not initialized")
        return self._schema_manager.get_table_info(table_name)

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
        if not self._schema_manager:
            raise DriverOperationError("Schema manager not initialized")
        return self._schema_manager.sync_schema(
            schema_definition, backup_dir, self.create_table
        )
