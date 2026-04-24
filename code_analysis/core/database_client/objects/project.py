"""
Project object model.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

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
        processing_paused: When True, indexing and vectorization workers skip this project.
        created_at: Creation timestamp
        updated_at: Last update timestamp
        deleted: When True, project is soft-deleted (trash / recovery path).
    """

    id: str
    root_path: str
    name: Optional[str] = None
    comment: Optional[str] = None
    watch_dir_id: Optional[str] = None
    processing_paused: bool = False
    deleted: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
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

        del_raw = data.get("deleted")
        deleted_flag = bool(del_raw) if del_raw is not None else False
        return cls(
            id=data["id"],
            root_path=data["root_path"],
            name=data.get("name"),
            comment=data.get("comment"),
            watch_dir_id=data.get("watch_dir_id"),
            processing_paused=bool(data.get("processing_paused")),
            deleted=deleted_flag,
            created_at=cls._parse_timestamp(data.get("created_at")),
            updated_at=cls._parse_timestamp(data.get("updated_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "Project":
        """Create Project from database row.

        Args:
            row: Database row as dictionary

        Returns:
            Project instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, Any]:
        """Convert Project to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result: Dict[str, Any] = {
            "id": self.id,
            "root_path": self.root_path,
        }
        if self.name is not None:
            result["name"] = self.name
        if self.comment is not None:
            result["comment"] = self.comment
        if self.watch_dir_id is not None:
            result["watch_dir_id"] = self.watch_dir_id
        result["processing_paused"] = 1 if self.processing_paused else 0
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        if self.updated_at is not None:
            result["updated_at"] = self._to_timestamp(self.updated_at)
        return result
