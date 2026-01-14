"""
Project object model.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from .base import BaseObject


@dataclass
class Project(BaseObject):
    """Project entity object.

    Represents a code analysis project in the database.

    Attributes:
        id: Project identifier (UUID4 from projectid file)
        root_path: Absolute path to project root
        name: Project directory name
        comment: Optional project description
        watch_dir_id: Watch directory identifier (optional)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: str
    root_path: str
    name: Optional[str] = None
    comment: Optional[str] = None
    watch_dir_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "Project":
        """Create Project from dictionary.

        Args:
            data: Dictionary with project data

        Returns:
            Project instance

        Raises:
            ValueError: If required fields are missing
        """
        if "id" not in data:
            raise ValueError("Project id is required")
        if "root_path" not in data:
            raise ValueError("Project root_path is required")

        return cls(
            id=data["id"],
            root_path=data["root_path"],
            name=data.get("name"),
            comment=data.get("comment"),
            watch_dir_id=data.get("watch_dir_id"),
            created_at=cls._parse_timestamp(data.get("created_at")),
            updated_at=cls._parse_timestamp(data.get("updated_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "Project":
        """Create Project from database row.

        Args:
            row: Database row as dictionary

        Returns:
            Project instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert Project to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "id": self.id,
            "root_path": self.root_path,
        }
        if self.name is not None:
            result["name"] = self.name
        if self.comment is not None:
            result["comment"] = self.comment
        if self.watch_dir_id is not None:
            result["watch_dir_id"] = self.watch_dir_id
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        if self.updated_at is not None:
            result["updated_at"] = self._to_timestamp(self.updated_at)
        return result
