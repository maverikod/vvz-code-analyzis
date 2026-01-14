"""
Method and Import objects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from .base import BaseObject


@dataclass
class Method(BaseObject):
    """Method entity object.

    Represents a Python method in the database.

    Attributes:
        id: Method identifier
        class_id: Class identifier
        name: Method name
        line: Line number where method is defined
        args: Method arguments as list of strings
        docstring: Method docstring
        is_abstract: Whether method is abstract
        has_pass: Whether method body is just `pass`
        has_not_implemented: Whether method raises `NotImplementedError`
        created_at: Creation timestamp
    """

    id: Optional[int] = None
    class_id: int = 0
    name: str = ""
    line: int = 0
    args: List[str] = None
    docstring: Optional[str] = None
    is_abstract: bool = False
    has_pass: bool = False
    has_not_implemented: bool = False
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Initialize args as empty list if None."""
        if self.args is None:
            self.args = []

    def get_args(self) -> List[str]:
        """Get method arguments as list.

        Returns:
            List of argument names
        """
        return self.args if self.args else []

    def set_args(self, args: List[str]) -> None:
        """Set method arguments.

        Args:
            args: List of argument names
        """
        self.args = args if args else []

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "Method":
        """Create Method from dictionary.

        Args:
            data: Dictionary with method data

        Returns:
            Method instance

        Raises:
            ValueError: If required fields are missing
        """
        if "class_id" not in data:
            raise ValueError("Method class_id is required")
        if "name" not in data:
            raise ValueError("Method name is required")
        if "line" not in data:
            raise ValueError("Method line is required")

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
            class_id=data["class_id"],
            name=data["name"],
            line=data["line"],
            args=args,
            docstring=data.get("docstring"),
            is_abstract=bool(data.get("is_abstract", False)),
            has_pass=bool(data.get("has_pass", False)),
            has_not_implemented=bool(data.get("has_not_implemented", False)),
            created_at=cls._parse_timestamp(data.get("created_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "Method":
        """Create Method from database row.

        Args:
            row: Database row as dictionary

        Returns:
            Method instance

        Raises:
            ValueError: If required fields are missing
        """
        # Convert boolean values from database (0/1 or True/False)
        if "is_abstract" in row and row["is_abstract"] is not None:
            row["is_abstract"] = bool(row["is_abstract"])
        if "has_pass" in row and row["has_pass"] is not None:
            row["has_pass"] = bool(row["has_pass"])
        if "has_not_implemented" in row and row["has_not_implemented"] is not None:
            row["has_not_implemented"] = bool(row["has_not_implemented"])

        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert Method to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "class_id": self.class_id,
            "name": self.name,
            "line": self.line,
            "is_abstract": 1 if self.is_abstract else 0,
            "has_pass": 1 if self.has_pass else 0,
            "has_not_implemented": 1 if self.has_not_implemented else 0,
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


@dataclass
class Import(BaseObject):
    """Import entity object.

    Represents a Python import statement in the database.

    Attributes:
        id: Import identifier
        file_id: File identifier
        name: Import name
        module: Module name
        import_type: Import type (import, from_import, etc.)
        line: Line number where import is defined
        created_at: Creation timestamp
    """

    id: Optional[int] = None
    file_id: int = 0
    name: str = ""
    module: Optional[str] = None
    import_type: str = ""
    line: int = 0
    created_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "Import":
        """Create Import from dictionary.

        Args:
            data: Dictionary with import data

        Returns:
            Import instance

        Raises:
            ValueError: If required fields are missing
        """
        if "file_id" not in data:
            raise ValueError("Import file_id is required")
        if "name" not in data:
            raise ValueError("Import name is required")
        if "import_type" not in data:
            raise ValueError("Import import_type is required")
        if "line" not in data:
            raise ValueError("Import line is required")

        return cls(
            id=data.get("id"),
            file_id=data["file_id"],
            name=data["name"],
            module=data.get("module"),
            import_type=data["import_type"],
            line=data["line"],
            created_at=cls._parse_timestamp(data.get("created_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "Import":
        """Create Import from database row.

        Args:
            row: Database row as dictionary

        Returns:
            Import instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert Import to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "file_id": self.file_id,
            "name": self.name,
            "import_type": self.import_type,
            "line": self.line,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.module is not None:
            result["module"] = self.module
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        return result
