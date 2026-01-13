"""
SQLite CRUD operations for SQLite driver.

Handles insert, update, delete, and select operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..exceptions import DriverOperationError


class SQLiteOperations:
    """Handles SQLite CRUD operations."""

    def __init__(self, connection):
        """Initialize operations manager.

        Args:
            connection: SQLite connection object
        """
        self.conn = connection

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

            sql = (
                f"INSERT INTO {table_name} ({', '.join(columns)}) "
                f"VALUES ({placeholders})"
            )
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
