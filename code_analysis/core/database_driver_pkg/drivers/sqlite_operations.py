"""
SQLite CRUD operations for SQLite driver.

Handles insert, update, delete, and select operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, List, Optional

from ..exceptions import DriverOperationError
from .base import DbIdentity


def _normalize_sqlite_insert_identity(value: Any) -> DbIdentity:
    """Normalize explicit or lastrowid primary key for universal driver contract."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        return value
    return str(value)


class SQLiteOperations:
    """Handles SQLite CRUD operations. Thread-safe for shared connection (e.g. RPC)."""

    def __init__(self, connection):
        """Initialize operations manager.

        Args:
            connection: SQLite connection object
        """
        self.conn = connection
        self._lock = threading.Lock()

    def insert(self, table_name: str, data: Dict[str, Any]) -> Optional[DbIdentity]:
        """Insert row into table.

        Args:
            table_name: Name of the table
            data: Dictionary with column names as keys and values as values

        Returns:
            Primary key of the inserted row. For INTEGER PRIMARY KEY tables without
            ``id`` in ``data``, returns SQLite ``lastrowid``. For TEXT/UUID primary keys
            (and any insert that includes ``id`` in ``data``), returns that identity
            (string UUID for migrated tables), not ``lastrowid``.

        Raises:
            DriverOperationError: If operation fails
        """
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        with self._lock:
            try:
                columns = list(data.keys())
                values = tuple(data.values())  # SQLite requires tuple, not list
                placeholders = ", ".join(["?" for _ in values])

                sql = (
                    f"INSERT INTO {table_name} ({', '.join(columns)}) "
                    f"VALUES ({placeholders})"
                )
                cursor = self.conn.cursor()
                cursor.execute(sql, values)
                self.conn.commit()
                if "id" in data:
                    return _normalize_sqlite_insert_identity(data["id"])
                lid = cursor.lastrowid
                if lid is not None and lid != 0:
                    return int(lid)
                return 0
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

        with self._lock:
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

        with self._lock:
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

        with self._lock:
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
                # SQLite requires LIMIT when using OFFSET
                if limit is not None:
                    sql += f" LIMIT {limit}"
                    if offset is not None:
                        sql += f" OFFSET {offset}"
                elif offset is not None:
                    # Use a large limit when only offset is provided
                    sql += f" LIMIT -1 OFFSET {offset}"

                cursor = self.conn.cursor()
                try:
                    cursor.execute(sql, where_values)
                    rows = cursor.fetchall()
                    out = [dict(row) for row in rows]
                finally:
                    cursor.close()
                # Align with PostgreSQL driver: end implicit transaction after SELECT so
                # long gaps between RPCs do not leave the connection in an open txn.
                try:
                    self.conn.commit()
                except Exception:
                    pass
                return out
            except Exception as e:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                raise DriverOperationError(f"Failed to select rows: {e}") from e
