"""
Class and Function objects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from .base import BaseObject


@dataclass
class Class(BaseObject):
    """Class entity object.

    Represents a Python class in the database.

    Attributes:
        id: Class identifier
        file_id: File identifier
        name: Class name
        line: Line number where class is defined
        docstring: Class docstring
        bases: Base classes as list of strings
        created_at: Creation timestamp
    """

    id: Optional[int] = None
    file_id: int = 0
    name: str = ""
    line: int = 0
    docstring: Optional[str] = None
    bases: List[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Initialize bases as empty list if None."""
        if self.bases is None:
            self.bases = []

    def get_bases(self) -> List[str]:
        """Get base classes as list.

        Returns:
            List of base class names
        """
        return self.bases if self.bases else []

    def set_bases(self, bases: List[str]) -> None:
        """Set base classes.

        Args:
            bases: List of base class names
        """
        self.bases = bases if bases else []

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "Class":
        """Create Class from dictionary.

        Args:
            data: Dictionary with class data

        Returns:
            Class instance

        Raises:
            ValueError: If required fields are missing
        """
        if "file_id" not in data:
            raise ValueError("Class file_id is required")
        if "name" not in data:
            raise ValueError("Class name is required")
        if "line" not in data:
            raise ValueError("Class line is required")

        # Parse bases from JSON string if present
        bases = []
        if "bases" in data:
            if isinstance(data["bases"], str):
                bases = cls._parse_json_field(data["bases"], [])
            elif isinstance(data["bases"], list):
                bases = data["bases"]
            else:
                bases = []

        return cls(
            id=data.get("id"),
            file_id=data["file_id"],
            name=data["name"],
            line=data["line"],
            docstring=data.get("docstring"),
            bases=bases,
            created_at=cls._parse_timestamp(data.get("created_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "Class":
        """Create Class from database row.

        Args:
            row: Database row as dictionary

        Returns:
            Class instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert Class to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "file_id": self.file_id,
            "name": self.name,
            "line": self.line,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.docstring is not None:
            result["docstring"] = self.docstring
        if self.bases:
            result["bases"] = self._to_json_field(self.bases)
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        return result


@dataclass
class Function(BaseObject):
    """Function entity object.

    Represents a Python function in the database.

    Attributes:
        id: Function identifier
        file_id: File identifier
        name: Function name
        line: Line number where function is defined
        args: Function arguments as list of strings
        docstring: Function docstring
        created_at: Creation timestamp
    """

    id: Optional[int] = None
    file_id: int = 0
    name: str = ""
    line: int = 0
    args: List[str] = None
    docstring: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Initialize args as empty list if None."""
        if self.args is None:
            self.args = []

    def get_args(self) -> List[str]:
        """Get function arguments as list.

        Returns:
            List of argument names
        """
        return self.args if self.args else []

    def set_args(self, args: List[str]) -> None:
        """Set function arguments.

        Args:
            args: List of argument names
        """
        self.args = args if args else []

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "Function":
        """Create Function from dictionary.

        Args:
            data: Dictionary with function data

        Returns:
            Function instance

        Raises:
            ValueError: If required fields are missing
        """
        if "file_id" not in data:
            raise ValueError("Function file_id is required")
        if "name" not in data:
            raise ValueError("Function name is required")
        if "line" not in data:
            raise ValueError("Function line is required")

        # Parse args from JSON string if present
        args = []
        if "args" in data:
            if isinstance(data["args"], str):
                args = cls._parse_json_field(data["args"], [])
            elif isinstance(data["args"], list):
                args = data["args"]
            else:
                args = []

        return cls(
            id=data.get("id"),
            file_id=data["file_id"],
            name=data["name"],
            line=data["line"],
            args=args,
            docstring=data.get("docstring"),
            created_at=cls._parse_timestamp(data.get("created_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "Function":
        """Create Function from database row.

        Args:
            row: Database row as dictionary

        Returns:
            Function instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert Function to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "file_id": self.file_id,
            "name": self.name,
            "line": self.line,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.args:
            result["args"] = self._to_json_field(self.args)
        if self.docstring is not None:
            result["docstring"] = self.docstring
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        return result
