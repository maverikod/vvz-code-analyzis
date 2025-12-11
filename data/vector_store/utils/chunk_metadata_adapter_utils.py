"""
Utilities for chunk_metadata_adapter integration: builders only.

This module provides builder classes for ChunkQuery and SemanticChunk.

Features:
- ChunkQuery building utilities
- SemanticChunk creation utilities

Architecture:
- Integration with chunk_metadata_adapter
- Error handling

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
from typing import Dict, List, Any
from chunk_metadata_adapter import SemanticChunk, ChunkQuery
from chunk_metadata_adapter.query_validator import QueryValidator
from chunk_metadata_adapter.ast_optimizer import ASTOptimizer
from chunk_metadata_adapter.data_types import ChunkType, LanguageEnum
from vector_store.exceptions import ValidationError, InvalidParamsError

logger = logging.getLogger("vector_store.utils.chunk_metadata_adapter")


class ChunkQueryBuilder:
    """
    Builder for ChunkQuery objects.
    
    Provides fluent interface for building complex ChunkQuery objects
    with proper validation and optimization.
    
    Features:
    - Fluent query building
    - Automatic validation
    - Query optimization
    - Error handling
    """
    
    def __init__(self) -> None:
        """Initialize ChunkQuery builder."""
        self.query_validator: QueryValidator = QueryValidator()
        """Query validator."""
        
        self.ast_optimizer: ASTOptimizer = ASTOptimizer()
        """AST optimizer."""
        
        self.query_data: Dict[str, Any] = {}
        """Query data dictionary."""
    
    def with_metadata_filter(
        self,
        metadata_filter: Dict[str, Any]
    ) -> 'ChunkQueryBuilder':
        """
        Add metadata filter to query.
        
        Args:
            metadata_filter: Metadata filter dictionary
            
        Returns:
            Self for chaining
        """
        if not isinstance(metadata_filter, dict):
            raise InvalidParamsError(
                message="Metadata filter must be a dictionary",
                data={"parameter_name": "metadata_filter"}
            )
        
        self.query_data["metadata"] = metadata_filter
        return self
    
    def with_search_text(
        self,
        search_text: str
    ) -> 'ChunkQueryBuilder':
        """
        Add search text to query.
        
        Args:
            search_text: Text to search for
            
        Returns:
            Self for chaining
        """
        if not isinstance(search_text, str):
            raise InvalidParamsError(
                message="Search text must be a string",
                data={"parameter_name": "search_text"}
            )
        
        if not search_text.strip():
            raise InvalidParamsError(
                message="Search text cannot be empty",
                data={"parameter_name": "search_text"}
            )
        
        self.query_data["search_text"] = search_text
        return self
    
    def with_embedding(
        self,
        embedding: List[float]
    ) -> 'ChunkQueryBuilder':
        """
        Add embedding vector to query.
        
        Args:
            embedding: Embedding vector
            
        Returns:
            Self for chaining
        """
        if not isinstance(embedding, list):
            raise InvalidParamsError(
                message="Embedding must be a list",
                data={"parameter_name": "embedding"}
            )
        
        if not all(isinstance(x, (int, float)) for x in embedding):
            raise InvalidParamsError(
                message="Embedding must contain only numbers",
                data={"parameter_name": "embedding"}
            )
        
        self.query_data["embedding"] = embedding
        return self
    
    def with_limit(
        self,
        limit: int
    ) -> 'ChunkQueryBuilder':
        """
        Add limit to query.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            Self for chaining
        """
        if not isinstance(limit, int) or limit <= 0:
            raise InvalidParamsError(
                message="Limit must be a positive integer",
                data={"parameter_name": "limit"}
            )
        
        self.query_data["limit"] = limit
        return self
    
    def with_offset(
        self,
        offset: int
    ) -> 'ChunkQueryBuilder':
        """
        Add offset to query.
        
        Args:
            offset: Number of results to skip
            
        Returns:
            Self for chaining
        """
        if not isinstance(offset, int) or offset < 0:
            raise InvalidParamsError(
                message="Offset must be a non-negative integer",
                data={"parameter_name": "offset"}
            )
        
        self.query_data["offset"] = offset
        return self
    
    def build(self) -> ChunkQuery:
        """
        Build ChunkQuery object.
        
        Returns:
            Built ChunkQuery object
            
        Raises:
            ValidationError: If query is invalid
        """
        try:
            chunk_query = ChunkQuery(**self.query_data)
            
            # Optimize the query
            optimized_query = self.ast_optimizer.optimize(chunk_query)
            
            return optimized_query
        except Exception as e:
            if isinstance(e, (ValidationError, InvalidParamsError)):
                raise
            raise ValidationError(
                message=f"Failed to build ChunkQuery: {str(e)}"
            )


class SemanticChunkBuilder:
    """
    Builder for SemanticChunk objects.
    
    Provides fluent interface for building SemanticChunk objects
    with proper validation and data transformation.
    
    Features:
    - Fluent chunk building
    - Automatic validation
    - Data transformation
    - Error handling
    """
    
    def __init__(self) -> None:
        """Initialize SemanticChunk builder."""
        self.chunk_data: Dict[str, Any] = {}
        """Chunk data dictionary."""
    
    def with_text(
        self,
        text: str
    ) -> 'SemanticChunkBuilder':
        """
        Add text to chunk.
        
        Args:
            text: Chunk text content
            
        Returns:
            Self for chaining
        """
        if not isinstance(text, str):
            raise ValidationError(
                message="Text must be a string",
                data={"field_name": "text"}
            )
        
        if not text.strip():
            raise ValidationError(
                message="Text cannot be empty",
                data={"field_name": "text"}
            )
        
        self.chunk_data["text"] = text
        return self
    
    def with_uuid(
        self,
        uuid_str: str
    ) -> 'SemanticChunkBuilder':
        """
        Add UUID to chunk.
        
        Args:
            uuid_str: Chunk UUID
            
        Returns:
            Self for chaining
        """
        if not isinstance(uuid_str, str):
            raise ValidationError(
                message="UUID must be a string",
                data={"field_name": "uuid"}
            )
        
        # Validate UUID format
        try:
            import uuid
            uuid.UUID(uuid_str)
        except (ValueError, TypeError):
            raise ValidationError(
                message="Invalid UUID format",
                data={"field_name": "uuid"}
            )
        
        self.chunk_data["uuid"] = uuid_str
        return self
    
    def with_metadata(
        self,
        metadata: Dict[str, Any]
    ) -> 'SemanticChunkBuilder':
        """
        Add metadata to chunk.
        
        Args:
            metadata: Chunk metadata
            
        Returns:
            Self for chaining
        """
        if not isinstance(metadata, dict):
            raise ValidationError(
                message="Metadata must be a dictionary",
                data={"field_name": "metadata"}
            )
        
        self.chunk_data["metadata"] = metadata
        return self
    
    def with_embedding(
        self,
        embedding: List[float]
    ) -> 'SemanticChunkBuilder':
        """
        Add embedding to chunk.
        
        Args:
            embedding: Chunk embedding vector
            
        Returns:
            Self for chaining
        """
        if not isinstance(embedding, list):
            raise ValidationError(
                message="Embedding must be a list",
                data={"field_name": "embedding"}
            )
        
        if not all(isinstance(x, (int, float)) for x in embedding):
            raise ValidationError(
                message="Embedding must contain only numbers",
                data={"field_name": "embedding"}
            )
        
        self.chunk_data["embedding"] = embedding
        return self
    
    def with_source_id(
        self,
        source_id: str
    ) -> 'SemanticChunkBuilder':
        """
        Add source ID to chunk.
        
        Args:
            source_id: Source identifier
            
        Returns:
            Self for chaining
        """
        if not isinstance(source_id, str):
            raise ValidationError(
                message="Source ID must be a string",
                data={"field_name": "source_id"}
            )
        
        self.chunk_data["source_id"] = source_id
        return self
    
    def build(self) -> SemanticChunk:
        """
        Build SemanticChunk object.
        
        Returns:
            Built SemanticChunk object
            
        Raises:
            ValidationError: If chunk data is invalid
        """
        try:
            # Add required fields if missing
            if "type" not in self.chunk_data:
                self.chunk_data["type"] = ChunkType.DOC_BLOCK
            
            if "body" not in self.chunk_data:
                self.chunk_data["body"] = self.chunk_data.get("text", "")
            
            if "language" not in self.chunk_data:
                self.chunk_data["language"] = LanguageEnum.EN
            
            chunk = SemanticChunk(**self.chunk_data)
            return chunk
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise ValidationError(
                message=f"Failed to build SemanticChunk: {str(e)}"
            )