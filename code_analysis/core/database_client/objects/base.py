"""
Base object model for database entities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Type, TypeVar

T = TypeVar("T", bound="BaseObject")


@dataclass
class BaseObject(ABC):
    """Base class for all database entity objects.

    Provides common functionality for serialization, deserialization,
    and conversion to/from database row format.
    """

    def to_dict(self) -> Dict[str, Any]:
        """Convert object to dictionary.

        Returns:
            Dictionary representation of object
        """
        result = asdict(self)
        # Convert None values to appropriate types for database
        return {k: v for k, v in result.items() if v is not None}

    def to_json(self) -> str:
        """Convert object to JSON string.

        Returns:
            JSON string representation of object
        """
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    @abstractmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """Create object from dictionary.

        Args:
            data: Dictionary with object data

        Returns:
            Object instance

        Raises:
            ValueError: If required fields are missing
        """
        raise NotImplementedError

    @classmethod
    def from_json(cls: Type[T], json_str: str) -> T:
        """Create object from JSON string.

        Args:
            json_str: JSON string representation

        Returns:
            Object instance

        Raises:
            ValueError: If JSON is invalid or required fields are missing
        """
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    @abstractmethod
    def from_db_row(cls: Type[T], row: Dict[str, Any]) -> T:
        """Create object from database row.

        Args:
            row: Database row as dictionary

        Returns:
            Object instance

        Raises:
            ValueError: If required fields are missing
        """
        raise NotImplementedError

    def to_db_row(self) -> Dict[str, Any]:
        """Convert object to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        return self.to_dict()

    @staticmethod
    def _parse_json_field(value: Optional[str], default: Any = None) -> Any:
        """Parse JSON field from database.

        Args:
            value: JSON string or None
            default: Default value if parsing fails

        Returns:
            Parsed value or default
        """
        if value is None:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default

    @staticmethod
    def _to_json_field(value: Any) -> Optional[str]:
        """Convert value to JSON string for database storage.

        Args:
            value: Value to convert

        Returns:
            JSON string or None
        """
        if value is None:
            return None
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_timestamp(value: Optional[float]) -> Optional[datetime]:
        """Parse timestamp from database (Julian day).

        Args:
            value: Julian day timestamp or None

        Returns:
            Datetime object or None
        """
        if value is None:
            return None
        try:
            # Convert Julian day to datetime
            # Julian day 0 = 4713-01-01 BC, but SQLite uses modified Julian day
            # Modified Julian day 0 = 1858-11-17
            # For simplicity, we'll use a conversion
            from datetime import timedelta

            # Modified Julian Day epoch
            mjd_epoch = datetime(1858, 11, 17)
            days = value - 2400000.5  # Convert to modified Julian day
            return mjd_epoch + timedelta(days=days)
        except (ValueError, TypeError, OverflowError):
            return None

    @staticmethod
    def _to_timestamp(value: Optional[datetime]) -> Optional[float]:
        """Convert datetime to Julian day timestamp for database.

        Args:
            value: Datetime object or None

        Returns:
            Julian day timestamp or None
        """
        if value is None:
            return None
        try:
            # Modified Julian Day epoch
            mjd_epoch = datetime(1858, 11, 17)
            delta = value - mjd_epoch
            days = delta.total_seconds() / 86400.0
            return days + 2400000.5  # Convert to modified Julian day
        except (ValueError, TypeError, OverflowError):
            return None
