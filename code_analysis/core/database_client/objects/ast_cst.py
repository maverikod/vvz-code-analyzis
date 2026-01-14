"""
AST and CST node objects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from .base import BaseObject


@dataclass
class ASTNode(BaseObject):
    """AST Tree entity object.

    Represents an Abstract Syntax Tree stored in the database.

    Attributes:
        id: AST tree identifier
        file_id: File identifier
        project_id: Project identifier
        ast_json: AST tree as JSON string
        ast_hash: Hash of AST tree content
        file_mtime: File modification time when AST was created
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: Optional[int] = None
    file_id: int = 0
    project_id: str = ""
    ast_json: str = ""
    ast_hash: str = ""
    file_mtime: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def get_ast_data(self) -> Any:
        """Get parsed AST data from JSON.

        Returns:
            Parsed AST data (dict or list)
        """
        return self._parse_json_field(self.ast_json, {})

    def set_ast_data(self, ast_data: Any) -> None:
        """Set AST data as JSON string.

        Args:
            ast_data: AST data to serialize
        """
        self.ast_json = self._to_json_field(ast_data) or ""

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "ASTNode":
        """Create ASTNode from dictionary.

        Args:
            data: Dictionary with AST node data

        Returns:
            ASTNode instance

        Raises:
            ValueError: If required fields are missing
        """
        if "file_id" not in data:
            raise ValueError("ASTNode file_id is required")
        if "project_id" not in data:
            raise ValueError("ASTNode project_id is required")
        if "ast_json" not in data:
            raise ValueError("ASTNode ast_json is required")
        if "ast_hash" not in data:
            raise ValueError("ASTNode ast_hash is required")

        return cls(
            id=data.get("id"),
            file_id=data["file_id"],
            project_id=data["project_id"],
            ast_json=data["ast_json"],
            ast_hash=data["ast_hash"],
            file_mtime=cls._parse_timestamp(data.get("file_mtime")),
            created_at=cls._parse_timestamp(data.get("created_at")),
            updated_at=cls._parse_timestamp(data.get("updated_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "ASTNode":
        """Create ASTNode from database row.

        Args:
            row: Database row as dictionary

        Returns:
            ASTNode instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert ASTNode to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "file_id": self.file_id,
            "project_id": self.project_id,
            "ast_json": self.ast_json,
            "ast_hash": self.ast_hash,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.file_mtime is not None:
            result["file_mtime"] = self._to_timestamp(self.file_mtime)
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        if self.updated_at is not None:
            result["updated_at"] = self._to_timestamp(self.updated_at)
        return result


@dataclass
class CSTNode(BaseObject):
    """CST Tree entity object.

    Represents a Concrete Syntax Tree (source code) stored in the database.

    Attributes:
        id: CST tree identifier
        file_id: File identifier
        project_id: Project identifier
        cst_code: CST tree as source code string
        cst_hash: Hash of CST tree content
        file_mtime: File modification time when CST was created
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: Optional[int] = None
    file_id: int = 0
    project_id: str = ""
    cst_code: str = ""
    cst_hash: str = ""
    file_mtime: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "CSTNode":
        """Create CSTNode from dictionary.

        Args:
            data: Dictionary with CST node data

        Returns:
            CSTNode instance

        Raises:
            ValueError: If required fields are missing
        """
        if "file_id" not in data:
            raise ValueError("CSTNode file_id is required")
        if "project_id" not in data:
            raise ValueError("CSTNode project_id is required")
        if "cst_code" not in data:
            raise ValueError("CSTNode cst_code is required")
        if "cst_hash" not in data:
            raise ValueError("CSTNode cst_hash is required")

        return cls(
            id=data.get("id"),
            file_id=data["file_id"],
            project_id=data["project_id"],
            cst_code=data["cst_code"],
            cst_hash=data["cst_hash"],
            file_mtime=cls._parse_timestamp(data.get("file_mtime")),
            created_at=cls._parse_timestamp(data.get("created_at")),
            updated_at=cls._parse_timestamp(data.get("updated_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "CSTNode":
        """Create CSTNode from database row.

        Args:
            row: Database row as dictionary

        Returns:
            CSTNode instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert CSTNode to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "file_id": self.file_id,
            "project_id": self.project_id,
            "cst_code": self.cst_code,
            "cst_hash": self.cst_hash,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.file_mtime is not None:
            result["file_mtime"] = self._to_timestamp(self.file_mtime)
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        if self.updated_at is not None:
            result["updated_at"] = self._to_timestamp(self.updated_at)
        return result
