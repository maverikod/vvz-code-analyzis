"""
Vector index and code chunk objects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from .base import BaseObject


@dataclass
class VectorIndex(BaseObject):
    """Vector Index entity object.

    Maps entities to vectors in FAISS index.

    Attributes:
        id: Vector index identifier
        project_id: Project identifier
        entity_type: Entity type (file, chunk, class, function, method)
        entity_id: Entity identifier
        vector_id: Vector identifier in FAISS index
        vector_dim: Vector dimension
        embedding_model: Embedding model used
        created_at: Creation timestamp
    """

    id: Optional[int] = None
    project_id: str = ""
    entity_type: str = ""
    entity_id: int = 0
    vector_id: int = 0
    vector_dim: int = 0
    embedding_model: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "VectorIndex":
        """Create VectorIndex from dictionary.

        Args:
            data: Dictionary with vector index data

        Returns:
            VectorIndex instance

        Raises:
            ValueError: If required fields are missing
        """
        if "project_id" not in data:
            raise ValueError("VectorIndex project_id is required")
        if "entity_type" not in data:
            raise ValueError("VectorIndex entity_type is required")
        if "entity_id" not in data:
            raise ValueError("VectorIndex entity_id is required")
        if "vector_id" not in data:
            raise ValueError("VectorIndex vector_id is required")
        if "vector_dim" not in data:
            raise ValueError("VectorIndex vector_dim is required")

        return cls(
            id=data.get("id"),
            project_id=data["project_id"],
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
            vector_id=data["vector_id"],
            vector_dim=data["vector_dim"],
            embedding_model=data.get("embedding_model"),
            created_at=cls._parse_timestamp(data.get("created_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "VectorIndex":
        """Create VectorIndex from database row.

        Args:
            row: Database row as dictionary

        Returns:
            VectorIndex instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert VectorIndex to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "project_id": self.project_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "vector_id": self.vector_id,
            "vector_dim": self.vector_dim,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.embedding_model is not None:
            result["embedding_model"] = self.embedding_model
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        return result


@dataclass
class CodeChunk(BaseObject):
    """Code Chunk entity object.

    Stores code chunks for vectorization and semantic search.

    Attributes:
        id: Chunk identifier
        file_id: File identifier
        project_id: Project identifier
        chunk_uuid: Unique chunk identifier (UUID4)
        chunk_type: Type of chunk (docstring, class, function, etc.)
        chunk_text: Chunk text content
        chunk_ordinal: Chunk order in file
        vector_id: Vector identifier in FAISS index
        embedding_model: Embedding model used
        bm25_score: BM25 relevance score
        embedding_vector: Embedding vector as JSON
        class_id: Associated class (if applicable)
        function_id: Associated function (if applicable)
        method_id: Associated method (if applicable)
        line: Line number in file
        ast_node_type: AST node type
        source_type: Source type (docstring, code, etc.)
        binding_level: Binding level for context
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: Optional[int] = None
    file_id: int = 0
    project_id: str = ""
    chunk_uuid: str = ""
    chunk_type: str = ""
    chunk_text: str = ""
    chunk_ordinal: Optional[int] = None
    vector_id: Optional[int] = None
    embedding_model: Optional[str] = None
    bm25_score: Optional[float] = None
    embedding_vector: Optional[str] = None
    class_id: Optional[int] = None
    function_id: Optional[int] = None
    method_id: Optional[int] = None
    line: Optional[int] = None
    ast_node_type: Optional[str] = None
    source_type: Optional[str] = None
    binding_level: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def get_embedding_vector(self) -> Optional[List[float]]:
        """Get parsed embedding vector from JSON.

        Returns:
            List of floats or None
        """
        if self.embedding_vector is None:
            return None
        return self._parse_json_field(self.embedding_vector, None)

    def set_embedding_vector(self, vector: Optional[List[float]]) -> None:
        """Set embedding vector as JSON string.

        Args:
            vector: Embedding vector to serialize
        """
        self.embedding_vector = self._to_json_field(vector)

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "CodeChunk":
        """Create CodeChunk from dictionary.

        Args:
            data: Dictionary with code chunk data

        Returns:
            CodeChunk instance

        Raises:
            ValueError: If required fields are missing
        """
        if "file_id" not in data:
            raise ValueError("CodeChunk file_id is required")
        if "project_id" not in data:
            raise ValueError("CodeChunk project_id is required")
        if "chunk_uuid" not in data:
            raise ValueError("CodeChunk chunk_uuid is required")
        if "chunk_type" not in data:
            raise ValueError("CodeChunk chunk_type is required")
        if "chunk_text" not in data:
            raise ValueError("CodeChunk chunk_text is required")

        return cls(
            id=data.get("id"),
            file_id=data["file_id"],
            project_id=data["project_id"],
            chunk_uuid=data["chunk_uuid"],
            chunk_type=data["chunk_type"],
            chunk_text=data["chunk_text"],
            chunk_ordinal=data.get("chunk_ordinal"),
            vector_id=data.get("vector_id"),
            embedding_model=data.get("embedding_model"),
            bm25_score=data.get("bm25_score"),
            embedding_vector=data.get("embedding_vector"),
            class_id=data.get("class_id"),
            function_id=data.get("function_id"),
            method_id=data.get("method_id"),
            line=data.get("line"),
            ast_node_type=data.get("ast_node_type"),
            source_type=data.get("source_type"),
            binding_level=data.get("binding_level", 0),
            created_at=cls._parse_timestamp(data.get("created_at")),
            updated_at=cls._parse_timestamp(data.get("updated_at")),
        )

    @classmethod
    def from_db_row(cls, row: Dict[str, any]) -> "CodeChunk":
        """Create CodeChunk from database row.

        Args:
            row: Database row as dictionary

        Returns:
            CodeChunk instance

        Raises:
            ValueError: If required fields are missing
        """
        return cls.from_dict(row)

    def to_db_row(self) -> Dict[str, any]:
        """Convert CodeChunk to database row format.

        Returns:
            Dictionary suitable for database insertion/update
        """
        result = {
            "file_id": self.file_id,
            "project_id": self.project_id,
            "chunk_uuid": self.chunk_uuid,
            "chunk_type": self.chunk_type,
            "chunk_text": self.chunk_text,
            "binding_level": self.binding_level,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.chunk_ordinal is not None:
            result["chunk_ordinal"] = self.chunk_ordinal
        if self.vector_id is not None:
            result["vector_id"] = self.vector_id
        if self.embedding_model is not None:
            result["embedding_model"] = self.embedding_model
        if self.bm25_score is not None:
            result["bm25_score"] = self.bm25_score
        if self.embedding_vector is not None:
            result["embedding_vector"] = self.embedding_vector
        if self.class_id is not None:
            result["class_id"] = self.class_id
        if self.function_id is not None:
            result["function_id"] = self.function_id
        if self.method_id is not None:
            result["method_id"] = self.method_id
        if self.line is not None:
            result["line"] = self.line
        if self.ast_node_type is not None:
            result["ast_node_type"] = self.ast_node_type
        if self.source_type is not None:
            result["source_type"] = self.source_type
        if self.created_at is not None:
            result["created_at"] = self._to_timestamp(self.created_at)
        if self.updated_at is not None:
            result["updated_at"] = self._to_timestamp(self.updated_at)
        return result
