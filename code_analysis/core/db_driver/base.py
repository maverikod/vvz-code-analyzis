"""
Base database driver interface.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class BaseDatabaseDriver(ABC):
    """Base class for database drivers."""

    @property
    @abstractmethod
    def is_thread_safe(self) -> bool:
        """
        Whether the driver is thread-safe.

        If False, the database layer will use locks for synchronization.

        Returns:
            True if driver is thread-safe, False otherwise
        """
        pass

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> None:
        """
        Establish database connection.

        Args:
            config: Driver-specific configuration
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close database connection."""
        pass

    @abstractmethod
    def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> None:
        """
        Execute SQL statement (INSERT, UPDATE, DELETE, CREATE, etc.).

        Args:
            sql: SQL statement
            params: Optional parameters for parameterized query
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def commit(self) -> None:
        """Commit current transaction."""
        pass

    @abstractmethod
    def rollback(self) -> None:
        """Rollback current transaction."""
        pass

    @abstractmethod
    def lastrowid(self) -> Optional[int]:
        """
        Get last inserted row ID.

        Returns:
            Last inserted row ID or None
        """
        pass

    @abstractmethod
    def create_schema(self, schema_sql: List[str]) -> None:
        """
        Create database schema.

        Args:
            schema_sql: List of SQL statements for schema creation
        """
        pass

    @abstractmethod
    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get information about table columns.

        Args:
            table_name: Name of the table

        Returns:
            List of dictionaries with column information (name, type, etc.)
        """
        pass
