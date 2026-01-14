"""
File object model.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from .base import BaseObject


@dataclass
class File(BaseObject):
    """File entity object.

    Represents a source code file in the database.

    Attributes:
        id: File identifier (INTEGER, PRIMARY KEY)
        project_id: Project identifier
        dataset_id: Dataset identifier
        watch_dir_id: Watch directory identifier (optional)
        path: Absolute file path
        relative_path: Relative path from project root (preferred)
        lines: Number of lines in file
        last_modified: Last modification timestamp
        has_docstring: Whether file has docstring
        deleted: Whether file is deleted
        original_path: Original path before moving to version_dir
        version_dir: Version directory path for deleted files
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: Optional[int] = None
    project_id: str = ""
    dataset_id: str = ""
    watch_dir_id: Optional[str] = None
    path: str = ""
    relative_path: Optional[str] = None
    lines: Optional[int] = None
    last_modified: Optional[datetime] = None
    has_docstring: Optional[bool] = None
    deleted: bool = False
    original_path: Optional[str] = None
    version_dir: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "File":
        """Create File from dictionary.

        Args:
            data: Dictionary with file data

        Returns:
            File instance

        Raises:
            ValueError: If required fields are missing
        """
        if "project_id" not in data:
            raise ValueError("File project_id is required")
        if "dataset_id" not in data:
            raise ValueError("File dataset_id is required")
        if "path" not in data:
            raise ValueError("File path is required")

        return cls(
            id=data.get("id"),
            project_id=data["project_id"],
            dataset_id=data["dataset_id"],
            watch_dir_id=data.get("watch_dir_id"),
            path=data["path"],
            relative_path=data.get("relative_path"),
            lines=data.get("lines"),
            last_modified=cls._parse_timestamp(data.get("last_modified")),
            has_docstring=data.get("has_docstring"),
            deleted=bool(data.get("deleted", False)),
            original_path=data.get("original_path"),
            version_dir=data.get("version_dir"),
            created_at=cls._parse_timestamp(data.get("created_at")),
            updated_at=cls._parse_timestamp(data.get("updated_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "File":
        """Create File from database row.

        Args:
            row: Database row as dictionary

        Returns:
            File instance

        Raises:
            ValueError: If required fields are missing
        """
        # Convert boolean values from database (0/1 or True/False)
        if "has_docstring" in row and row["has_docstring"] is not None:
            row["has_docstring"] = bool(row["has_docstring"])
        if "deleted" in row and row["deleted"] is not None:
            row["deleted"] = bool(row["deleted"])

        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert File to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "project_id": self.project_id,
            "dataset_id": self.dataset_id,
            "path": self.path,
            "deleted": 1 if self.deleted else 0,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.watch_dir_id is not None:
            result["watch_dir_id"] = self.watch_dir_id
        if self.relative_path is not None:
            result["relative_path"] = self.relative_path
        if self.lines is not None:
            result["lines"] = self.lines
        if self.last_modified is not None:
            result["last_modified"] = self._to_timestamp(self.last_modified)
        if self.has_docstring is not None:
            result["has_docstring"] = 1 if self.has_docstring else 0
        if self.original_path is not None:
            result["original_path"] = self.original_path
        if self.version_dir is not None:
            result["version_dir"] = self.version_dir
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        if self.updated_at is not None:
            result["updated_at"] = self._to_timestamp(self.updated_at)
        return result
