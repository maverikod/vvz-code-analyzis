"""
Dataset object model.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from .base import BaseObject


@dataclass
class Dataset(BaseObject):
    """Dataset entity object.

    Represents a dataset (multi-root indexing) within a project.

    Attributes:
        id: Dataset identifier (UUID4)
        project_id: Project identifier
        root_path: Absolute path to dataset root
        name: Dataset name (optional)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: str
    project_id: str
    root_path: str
    name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "Dataset":
        """Create Dataset from dictionary.

        Args:
            data: Dictionary with dataset data

        Returns:
            Dataset instance

        Raises:
            ValueError: If required fields are missing
        """
        if "id" not in data:
            raise ValueError("Dataset id is required")
        if "project_id" not in data:
            raise ValueError("Dataset project_id is required")
        if "root_path" not in data:
            raise ValueError("Dataset root_path is required")

        return cls(
            id=data["id"],
            project_id=data["project_id"],
            root_path=data["root_path"],
            name=data.get("name"),
            created_at=cls._parse_timestamp(data.get("created_at")),
            updated_at=cls._parse_timestamp(data.get("updated_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "Dataset":
        """Create Dataset from database row.

        Args:
            row: Database row as dictionary

        Returns:
            Dataset instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert Dataset to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "id": self.id,
            "project_id": self.project_id,
            "root_path": self.root_path,
        }
        if self.name is not None:
            result["name"] = self.name
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        if self.updated_at is not None:
            result["updated_at"] = self._to_timestamp(self.updated_at)
        return result
