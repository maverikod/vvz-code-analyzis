"""
DB-API compatibility layer for CodeDatabase when using proxy drivers.

This module provides lightweight objects that mimic a subset of the sqlite3
connection/cursor API used across the legacy `code_analysis.core.database.*`
modules.

Goal:
    Allow old code paths that expect `database.conn.cursor().execute(...)` to keep
    working while the actual reads/writes are routed through the configured
    database driver (e.g. `sqlite_proxy` via a queue-backed worker).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..db_driver.base import BaseDatabaseDriver


def _is_select_like(sql: str) -> bool:
    """Return True for SQL statements that produce rows.

    Args:
        sql: SQL statement.

    Returns:
        True if the statement is SELECT/PRAGMA/WITH-like.
    """
    head = sql.lstrip().lower()
    return head.startswith("select") or head.startswith("pragma") or head.startswith("with")


class DriverBackedCursor:
    """A minimal DB-API cursor backed by BaseDatabaseDriver operations."""

    def __init__(self, driver: BaseDatabaseDriver) -> None:
        """
        Initialize cursor.

        Args:
            driver: Database driver instance.
        """
        self._driver = driver
        self._rows: List[Dict[str, Any]] = []
        self._row_index: int = 0
        self.lastrowid: Optional[int] = None

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> "DriverBackedCursor":
        """
        Execute SQL and cache rows for fetchone/fetchall when applicable.

        Args:
            sql: SQL statement.
            params: Optional parameters.

        Returns:
            Self.
        """
        tup: Optional[Tuple[Any, ...]] = tuple(params) if params is not None else None

        self._rows = []
        self._row_index = 0

        if _is_select_like(sql):
            self._rows = self._driver.fetchall(sql, tup)
        else:
            self._driver.execute(sql, tup)
            self.lastrowid = self._driver.lastrowid()

        return self

    def fetchone(self) -> Optional[Dict[str, Any]]:
        """
        Fetch one cached row.

        Returns:
            Row dict or None.
        """
        if self._row_index >= len(self._rows):
            return None
        row = self._rows[self._row_index]
        self._row_index += 1
        return row

    def fetchall(self) -> List[Dict[str, Any]]:
        """
        Fetch all cached rows.

        Returns:
            List of row dicts.
        """
        if self._row_index == 0:
            return list(self._rows)
        remaining = self._rows[self._row_index :]
        self._row_index = len(self._rows)
        return list(remaining)

    def close(self) -> None:
        """Close cursor (no-op)."""
        self._rows = []
        self._row_index = 0


class DriverBackedConnection:
    """A minimal DB-API connection backed by BaseDatabaseDriver operations."""

    def __init__(self, driver: BaseDatabaseDriver) -> None:
        """
        Initialize connection wrapper.

        Args:
            driver: Database driver instance.
        """
        self._driver = driver

    def cursor(self) -> DriverBackedCursor:
        """
        Create a cursor.

        Returns:
            DriverBackedCursor instance.
        """
        return DriverBackedCursor(self._driver)

    def commit(self) -> None:
        """Commit current transaction."""
        self._driver.commit()

    def rollback(self) -> None:
        """Rollback current transaction."""
        self._driver.rollback()

    def close(self) -> None:
        """Close connection (no-op; driver lifecycle is managed by CodeDatabase)."""
        return None


