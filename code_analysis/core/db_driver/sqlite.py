"""
SQLite database driver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseDatabaseDriver


class SQLiteDriver(BaseDatabaseDriver):
    """SQLite database driver."""

    @property
    def is_thread_safe(self) -> bool:
        """SQLite is not thread-safe for concurrent writes."""
        return False

    def __init__(self) -> None:
        """Initialize SQLite driver."""
        self.conn: Optional[sqlite3.Connection] = None
        self.db_path: Optional[Path] = None

    def connect(self, config: Dict[str, Any]) -> None:
        """
        Establish SQLite connection.

        Args:
            config: Configuration dict with 'path' key pointing to database file
        """
        if "path" not in config:
            raise ValueError("SQLite driver requires 'path' in config")

        self.db_path = Path(config["path"]).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Allow connection to be used from different threads
        # Thread safety is ensured by locks in CodeDatabase
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")

    def disconnect(self) -> None:
        """Close SQLite connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> None:
        """
        Execute SQL statement.

        Args:
            sql: SQL statement
            params: Optional parameters for parameterized query
        """
        if not self.conn:
            raise RuntimeError("Database connection not established")

        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

    def fetchone(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute SELECT query and return first row.

        Args:
            sql: SQL SELECT statement
            params: Optional parameters for parameterized query

        Returns:
            Dictionary with column names as keys, or None if no rows
        """
        if not self.conn:
            raise RuntimeError("Database connection not established")

        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute SELECT query and return all rows.

        Args:
            sql: SQL SELECT statement
            params: Optional parameters for parameterized query

        Returns:
            List of dictionaries with column names as keys
        """
        if not self.conn:
            raise RuntimeError("Database connection not established")

        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def commit(self) -> None:
        """Commit current transaction."""
        if not self.conn:
            raise RuntimeError("Database connection not established")
        self.conn.commit()

    def rollback(self) -> None:
        """Rollback current transaction."""
        if not self.conn:
            raise RuntimeError("Database connection not established")
        self.conn.rollback()

    def lastrowid(self) -> Optional[int]:
        """
        Get last inserted row ID.

        Returns:
            Last inserted row ID or None
        """
        if not self.conn:
            raise RuntimeError("Database connection not established")
        cursor = self.conn.cursor()
        return cursor.lastrowid

    def create_schema(self, schema_sql: List[str]) -> None:
        """
        Create database schema.

        Args:
            schema_sql: List of SQL statements for schema creation
        """
        if not self.conn:
            raise RuntimeError("Database connection not established")

        cursor = self.conn.cursor()
        for sql in schema_sql:
            cursor.execute(sql)
        self.conn.commit()

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get information about table columns using PRAGMA.

        Args:
            table_name: Name of the table

        Returns:
            List of dictionaries with column information
        """
        if not self.conn:
            raise RuntimeError("Database connection not established")

        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        rows = cursor.fetchall()
        # Convert to list of dicts
        columns = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
        return [dict(zip(columns, row)) for row in rows]
