"""
Analysis objects: Issue, Usage, CodeDuplicate.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from .base import BaseObject


@dataclass
class Issue(BaseObject):
    """Issue entity object.

    Represents a code quality issue detected during analysis.

    Attributes:
        id: Issue identifier
        file_id: File identifier (optional)
        project_id: Project identifier (optional)
        class_id: Class identifier (optional)
        function_id: Function identifier (optional)
        method_id: Method identifier (optional)
        issue_type: Issue type (missing_docstring, long_file, etc.)
        line: Line number where issue occurs
        description: Issue description
        metadata: Additional metadata as dictionary
        created_at: Creation timestamp
    """

    id: Optional[int] = None
    file_id: Optional[int] = None
    project_id: Optional[str] = None
    class_id: Optional[int] = None
    function_id: Optional[int] = None
    method_id: Optional[int] = None
    issue_type: str = ""
    line: Optional[int] = None
    description: Optional[str] = None
    metadata: Dict[str, Any] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Initialize metadata as empty dict if None."""
        if self.metadata is None:
            self.metadata = {}

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata as dictionary.

        Returns:
            Metadata dictionary
        """
        return self.metadata if self.metadata else {}

    def set_metadata(self, metadata: Dict[str, Any]) -> None:
        """Set metadata.

        Args:
            metadata: Metadata dictionary
        """
        self.metadata = metadata if metadata else {}

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "Issue":
        """Create Issue from dictionary.

        Args:
            data: Dictionary with issue data

        Returns:
            Issue instance

        Raises:
            ValueError: If required fields are missing
        """
        if "issue_type" not in data:
            raise ValueError("Issue issue_type is required")

        # Parse metadata from JSON string if present
        metadata = {}
        if "metadata" in data:
            if isinstance(data["metadata"], str):
                metadata = cls._parse_json_field(data["metadata"], {})
            elif isinstance(data["metadata"], dict):
                metadata = data["metadata"]
            else:
                metadata = {}

        return cls(
            id=data.get("id"),
            file_id=data.get("file_id"),
            project_id=data.get("project_id"),
            class_id=data.get("class_id"),
            function_id=data.get("function_id"),
            method_id=data.get("method_id"),
            issue_type=data["issue_type"],
            line=data.get("line"),
            description=data.get("description"),
            metadata=metadata,
            created_at=cls._parse_timestamp(data.get("created_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "Issue":
        """Create Issue from database row.

        Args:
            row: Database row as dictionary

        Returns:
            Issue instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert Issue to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "issue_type": self.issue_type,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.file_id is not None:
            result["file_id"] = self.file_id
        if self.project_id is not None:
            result["project_id"] = self.project_id
        if self.class_id is not None:
            result["class_id"] = self.class_id
        if self.function_id is not None:
            result["function_id"] = self.function_id
        if self.method_id is not None:
            result["method_id"] = self.method_id
        if self.line is not None:
            result["line"] = self.line
        if self.description is not None:
            result["description"] = self.description
        if self.metadata:
            result["metadata"] = self._to_json_field(self.metadata)
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        return result


@dataclass
class Usage(BaseObject):
    """Usage entity object.

    Tracks usage of classes, functions, methods, and variables.

    Attributes:
        id: Usage identifier
        file_id: File identifier
        line: Line number where usage occurs
        usage_type: Usage type (call, attribute, etc.)
        target_type: Target type (class, function, method, variable)
        target_class: Target class name (if applicable)
        target_name: Target name
        context: Usage context as dictionary
        created_at: Creation timestamp
    """

    id: Optional[int] = None
    file_id: int = 0
    line: int = 0
    usage_type: str = ""
    target_type: str = ""
    target_class: Optional[str] = None
    target_name: str = ""
    context: Dict[str, Any] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Initialize context as empty dict if None."""
        if self.context is None:
            self.context = {}

    def get_context(self) -> Dict[str, Any]:
        """Get context as dictionary.

        Returns:
            Context dictionary
        """
        return self.context if self.context else {}

    def set_context(self, context: Dict[str, Any]) -> None:
        """Set context.

        Args:
            context: Context dictionary
        """
        self.context = context if context else {}

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "Usage":
        """Create Usage from dictionary.

        Args:
            data: Dictionary with usage data

        Returns:
            Usage instance

        Raises:
            ValueError: If required fields are missing
        """
        if "file_id" not in data:
            raise ValueError("Usage file_id is required")
        if "line" not in data:
            raise ValueError("Usage line is required")
        if "usage_type" not in data:
            raise ValueError("Usage usage_type is required")
        if "target_type" not in data:
            raise ValueError("Usage target_type is required")
        if "target_name" not in data:
            raise ValueError("Usage target_name is required")

        # Parse context from JSON string if present
        context = {}
        if "context" in data:
            if isinstance(data["context"], str):
                context = cls._parse_json_field(data["context"], {})
            elif isinstance(data["context"], dict):
                context = data["context"]
            else:
                context = {}

        return cls(
            id=data.get("id"),
            file_id=data["file_id"],
            line=data["line"],
            usage_type=data["usage_type"],
            target_type=data["target_type"],
            target_class=data.get("target_class"),
            target_name=data["target_name"],
            context=context,
            created_at=cls._parse_timestamp(data.get("created_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "Usage":
        """Create Usage from database row.

        Args:
            row: Database row as dictionary

        Returns:
            Usage instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert Usage to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "file_id": self.file_id,
            "line": self.line,
            "usage_type": self.usage_type,
            "target_type": self.target_type,
            "target_name": self.target_name,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.target_class is not None:
            result["target_class"] = self.target_class
        if self.context:
            result["context"] = self._to_json_field(self.context)
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        return result


@dataclass
class CodeDuplicate(BaseObject):
    """Code Duplicate entity object.

    Represents duplicate code detected in the project.

    Attributes:
        id: Duplicate identifier
        project_id: Project identifier
        duplicate_hash: Hash of duplicate code
        similarity: Similarity score (0.0-1.0)
        created_at: Creation timestamp
    """

    id: Optional[int] = None
    project_id: str = ""
    duplicate_hash: str = ""
    similarity: float = 0.0
    created_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "CodeDuplicate":
        """Create CodeDuplicate from dictionary.

        Args:
            data: Dictionary with duplicate data

        Returns:
            CodeDuplicate instance

        Raises:
            ValueError: If required fields are missing
        """
        if "project_id" not in data:
            raise ValueError("CodeDuplicate project_id is required")
        if "duplicate_hash" not in data:
            raise ValueError("CodeDuplicate duplicate_hash is required")
        if "similarity" not in data:
            raise ValueError("CodeDuplicate similarity is required")

        return cls(
            id=data.get("id"),
            project_id=data["project_id"],
            duplicate_hash=data["duplicate_hash"],
            similarity=float(data["similarity"]),
            created_at=cls._parse_timestamp(data.get("created_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "CodeDuplicate":
        """Create CodeDuplicate from database row.

        Args:
            row: Database row as dictionary

        Returns:
            CodeDuplicate instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert CodeDuplicate to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "project_id": self.project_id,
            "duplicate_hash": self.duplicate_hash,
            "similarity": self.similarity,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        return result
