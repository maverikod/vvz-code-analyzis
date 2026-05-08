"""
Base database driver interface (legacy CodeDatabase / in-process stack).

This ABC matches the pre-universal driver contract used by :class:`SQLiteDriverProxy`
and the worker-only in-process SQLite driver. It is unrelated to
:class:`~code_analysis.core.database_driver_pkg.drivers.base.BaseDatabaseDriver`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class BaseDatabaseDriver(ABC):
    """Base class for database drivers (legacy interface)."""

    @property
    @abstractmethod
    def is_thread_safe(self) -> bool:
        """Whether the driver is thread-safe."""
        raise NotImplementedError

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> None:
        """Establish database connection."""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """Close database connection."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> None:
        """Execute SQL statement (INSERT, UPDATE, DELETE, CREATE, etc.)."""
        raise NotImplementedError

    @abstractmethod
    def fetchone(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> Optional[Dict[str, Any]]:
        """Execute SELECT query and return first row."""
        raise NotImplementedError

    @abstractmethod
    def fetchall(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
        """Execute SELECT query and return all rows."""
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        """Commit current transaction."""
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        """Rollback current transaction."""
        raise NotImplementedError

    @abstractmethod
    def lastrowid(self) -> Optional[int]:
        """Get last inserted row ID."""
        raise NotImplementedError

    @abstractmethod
    def create_schema(self, schema_sql: List[str]) -> None:
        """Create database schema."""
        raise NotImplementedError

    @abstractmethod
    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get information about table columns."""
        raise NotImplementedError
