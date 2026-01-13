"""
SQLite driver implementation for database driver process.

Works with tables, columns, and cells (low-level operations).
This driver runs in the driver process and handles table-level operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..exceptions import (
    DriverConnectionError,
    DriverOperationError,
    TransactionError,
)
from .base import BaseDatabaseDriver


class SQLiteDriver(BaseDatabaseDriver):
    """SQLite driver for database driver process.

    Works with tables directly (insert, update, delete, select).
    All operations are table-level, not object-level.
    """

    def __init__(self) -> None:
        """Initialize SQLite driver."""
        self.conn: Optional[sqlite3.Connection] = None
        self.db_path: Optional[Path] = None
        self._transactions: Dict[str, sqlite3.Connection] = {}

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
            except Exception:
                pass  # WAL might not be supported
        except Exception as e:
            raise DriverConnectionError(f"Failed to connect to database: {e}") from e

    def disconnect(self) -> None:
        """Close SQLite connection.

        Raises:
            DriverConnectionError: If disconnection fails
        """
        try:
            # Close all transaction connections
            for transaction_id, conn in list(self._transactions.items()):
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
                del self._transactions[transaction_id]

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
        """Insert row into table.

        Args:
            table_name: Name of the table
            data: Dictionary with column names as keys and values as values

        Returns:
            ID of inserted row (lastrowid)

        Raises:
            DriverOperationError: If operation fails
        """
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        try:
            columns = list(data.keys())
            values = list(data.values())
            placeholders = ", ".join(["?" for _ in values])

            sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
            cursor = self.conn.cursor()
            cursor.execute(sql, values)
            self.conn.commit()
            return cursor.lastrowid or 0
        except Exception as e:
            self.conn.rollback()
            raise DriverOperationError(f"Failed to insert row: {e}") from e

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
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        try:
            # Build SET clause
            set_clauses = []
            set_values = []
            for col, val in data.items():
                set_clauses.append(f"{col} = ?")
                set_values.append(val)

            # Build WHERE clause
            where_clauses = []
            where_values = []
            for col, val in where.items():
                where_clauses.append(f"{col} = ?")
                where_values.append(val)

            sql = (
                f"UPDATE {table_name} SET {', '.join(set_clauses)} "
                f"WHERE {' AND '.join(where_clauses)}"
            )
            cursor = self.conn.cursor()
            cursor.execute(sql, set_values + where_values)
            self.conn.commit()
            return cursor.rowcount
        except Exception as e:
            self.conn.rollback()
            raise DriverOperationError(f"Failed to update rows: {e}") from e

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
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        try:
            # Build WHERE clause
            where_clauses = []
            where_values = []
            for col, val in where.items():
                where_clauses.append(f"{col} = ?")
                where_values.append(val)

            sql = f"DELETE FROM {table_name} WHERE {' AND '.join(where_clauses)}"
            cursor = self.conn.cursor()
            cursor.execute(sql, where_values)
            self.conn.commit()
            return cursor.rowcount
        except Exception as e:
            self.conn.rollback()
            raise DriverOperationError(f"Failed to delete rows: {e}") from e

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
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        try:
            # Build SELECT clause
            if columns:
                select_clause = ", ".join(columns)
            else:
                select_clause = "*"

            sql = f"SELECT {select_clause} FROM {table_name}"

            # Build WHERE clause
            where_values = []
            if where:
                where_clauses = []
                for col, val in where.items():
                    where_clauses.append(f"{col} = ?")
                    where_values.append(val)
                sql += f" WHERE {' AND '.join(where_clauses)}"

            # Build ORDER BY clause
            if order_by:
                sql += f" ORDER BY {', '.join(order_by)}"

            # Build LIMIT and OFFSET
            if limit is not None:
                sql += f" LIMIT {limit}"
                if offset is not None:
                    sql += f" OFFSET {offset}"
            elif offset is not None:
                sql += f" OFFSET {offset}"

            cursor = self.conn.cursor()
            cursor.execute(sql, where_values)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            raise DriverOperationError(f"Failed to select rows: {e}") from e

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
        if not self.conn:
            raise TransactionError("Database connection not established")

        try:
            import uuid

            transaction_id = str(uuid.uuid4())
            # Create separate connection for transaction
            if not self.db_path:
                raise TransactionError("Database path not set")

            trans_conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            trans_conn.row_factory = sqlite3.Row
            trans_conn.execute("PRAGMA foreign_keys = ON")
            trans_conn.execute("BEGIN TRANSACTION")
            self._transactions[transaction_id] = trans_conn
            return transaction_id
        except Exception as e:
            raise TransactionError(f"Failed to begin transaction: {e}") from e

    def commit_transaction(self, transaction_id: str) -> bool:
        """Commit database transaction.

        Args:
            transaction_id: Transaction ID returned by begin_transaction()

        Returns:
            True if transaction was committed successfully, False otherwise

        Raises:
            TransactionError: If transaction cannot be committed
        """
        if transaction_id not in self._transactions:
            raise TransactionError(f"Transaction {transaction_id} not found")

        try:
            conn = self._transactions[transaction_id]
            conn.commit()
            conn.close()
            del self._transactions[transaction_id]
            return True
        except Exception as e:
            raise TransactionError(f"Failed to commit transaction: {e}") from e

    def rollback_transaction(self, transaction_id: str) -> bool:
        """Rollback database transaction.

        Args:
            transaction_id: Transaction ID returned by begin_transaction()

        Returns:
            True if transaction was rolled back successfully, False otherwise

        Raises:
            TransactionError: If transaction cannot be rolled back
        """
        if transaction_id not in self._transactions:
            raise TransactionError(f"Transaction {transaction_id} not found")

        try:
            conn = self._transactions[transaction_id]
            conn.rollback()
            conn.close()
            del self._transactions[transaction_id]
            return True
        except Exception as e:
            raise TransactionError(f"Failed to rollback transaction: {e}") from e

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get information about table columns.

        Args:
            table_name: Name of the table

        Returns:
            List of dictionaries with column information (name, type, nullable, etc.)

        Raises:
            DriverOperationError: If operation fails
        """
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        try:
            cursor = self.conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            rows = cursor.fetchall()
            result = []
            for row in rows:
                result.append(
                    {
                        "name": row[1],
                        "type": row[2],
                        "nullable": not row[3],
                        "default": row[4],
                        "primary_key": bool(row[5]),
                    }
                )
            return result
        except Exception as e:
            raise DriverOperationError(f"Failed to get table info: {e}") from e

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
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        # This is a simplified implementation
        # Full implementation would compare existing schema with new schema
        # and apply changes incrementally
        try:
            result: Dict[str, Any] = {
                "created_tables": [],
                "modified_tables": [],
                "errors": [],
            }

            tables = schema_definition.get("tables", [])
            for table_schema in tables:
                try:
                    table_name = table_schema.get("name")
                    if not table_name:
                        continue

                    # Check if table exists
                    cursor = self.conn.cursor()
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (table_name,),
                    )
                    exists = cursor.fetchone() is not None

                    if not exists:
                        self.create_table(table_schema)
                        result["created_tables"].append(table_name)
                    else:
                        # Table exists - could implement ALTER TABLE logic here
                        result["modified_tables"].append(table_name)
                except Exception as e:
                    result["errors"].append(f"Error processing table {table_name}: {e}")

            self.conn.commit()
            return result
        except Exception as e:
            self.conn.rollback()
            raise DriverOperationError(f"Failed to sync schema: {e}") from e
