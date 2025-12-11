"""
Declarative base classes and interfaces for IndexManager.

This file contains only declarations of classes, methods, signatures
and documentation without implementation.

Features:
- Base classes for index management
- Enum definitions for index types and operators
- Utility classes for index operations
- Result classes for index operations

Architecture:
- Defines the core interfaces for index management
- Provides type definitions for all index operations
- Establishes the foundation for atomic operations

Author: Vasiliy Zdanovskiy <vasilyvz@gmail.com>
Created: 2024-01-15
Updated: 2024-01-15
"""

from typing import Dict, List, Any, Optional, Union, Set
from abc import ABC, abstractmethod
from enum import Enum
from datetime import datetime
import hashlib
import redis.asyncio as redis


# Constants
DEFAULT_BATCH_SIZE: int = 100
"""Default batch size for index operations."""

DEFAULT_TTL_DAYS: int = 7
"""Default TTL for index keys in days."""

INDEX_PREFIX: str = "index"
"""Prefix for all index keys."""

FIELD_INDEX_PREFIX: str = "field_index"
"""Prefix for scalar field index keys."""

ARRAY_ELEMENT_PREFIX: str = "array_element_index"
"""Prefix for array element index keys."""

ARRAY_EXACT_PREFIX: str = "array_exact_index"
"""Prefix for array exact match index keys."""

RANGE_INDEX_PREFIX: str = "range_index"
"""Prefix for range index keys."""

PREFIX_INDEX_PREFIX: str = "prefix_index"
"""Prefix for prefix index keys."""

META_PREFIX: str = "index_meta"
"""Prefix for index metadata keys."""


# Import exceptions from main exceptions module
from vector_store.exceptions import (
    IndexManagerError,
    IndexNotFoundError,
    IndexAlreadyExistsError,
    IndexOperationError,
    IndexValidationError as ValidationError
)


# Enums
class IndexType(Enum):
    """Types of indexes supported by the index manager."""
    SCALAR = "scalar"           # Regular scalar fields
    ARRAY = "array"             # Array fields with double indexing
    RANGE = "range"             # Numeric range indexes
    PREFIX = "prefix"           # String prefix indexes
    COMPOUND = "compound"       # Compound indexes


class IndexOperator(Enum):
    """Search operators supported by the index manager."""
    EQUALS = "="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    GREATER_EQUAL = ">="
    LESS_THAN = "<"
    LESS_EQUAL = "<="
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    RANGE = "range"


class IndexStatus(Enum):
    """Status of index operations."""
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    ERROR = "error"
    NOT_FOUND = "not_found"


# Base Classes
class BaseIndexManager(ABC):
    """
    Base class for all index managers.
    
    Defines the common interface for index management operations
    with support for validation and error handling.
    
    Features:
    - Abstract methods for core index operations
    - Common validation and error handling
    - Connection management
    
    Architecture:
    - Provides the foundation for all index managers
    - Defines the contract for index operations
    - Supports different storage backends
    """
    
    def __init__(self, redis_client: redis.Redis) -> None:
        """
        Initialize the base index manager.
        
        Args:
            redis_client: Redis client for index operations
        """
        self.redis: redis.Redis = redis_client
        """Redis client for index operations."""
        
        self.index_prefix: str = INDEX_PREFIX
        """Prefix for all index keys."""
        
        self.field_index_prefix: str = FIELD_INDEX_PREFIX
        """Prefix for scalar field index keys."""
        
        self.array_element_prefix: str = ARRAY_ELEMENT_PREFIX
        """Prefix for array element index keys."""
        
        self.array_exact_prefix: str = ARRAY_EXACT_PREFIX
        """Prefix for array exact match index keys."""
        
        self.range_index_prefix: str = RANGE_INDEX_PREFIX
        """Prefix for range index keys."""
        
        self.prefix_index_prefix: str = PREFIX_INDEX_PREFIX
        """Prefix for prefix index keys."""
        
        self.meta_prefix: str = META_PREFIX
        """Prefix for index metadata keys."""
    
    @abstractmethod
    async def ping(self) -> bool:
        """
        Check connection to the index storage.
        
        Returns:
            True if connection is successful, False otherwise
        """
        ...
    
    @abstractmethod
    async def create_index(self, field_name: str, index_type: IndexType) -> None:
        """
        Create an index for a field.
        
        Args:
            field_name: Name of the field to index
            index_type: Type of index to create
            
        Raises:
            IndexAlreadyExistsError: If index already exists
            IndexOperationError: If index creation fails
        """
        ...
    
    @abstractmethod
    async def drop_index(self, field_name: str) -> None:
        """
        Drop an index for a field.
        
        Args:
            field_name: Name of the field to drop index for
            
        Raises:
            IndexNotFoundError: If index does not exist
            IndexOperationError: If index deletion fails
        """
        pass
    
    @abstractmethod
    async def index_chunk(self, uuid: str, chunk_data: Dict[str, Any]) -> None:
        """
        Index a chunk by all indexed fields.
        
        Args:
            uuid: Unique identifier of the chunk
            chunk_data: Chunk data to index
            
        Raises:
            ValidationError: If chunk data is invalid
            IndexOperationError: If indexing fails
        """
        pass
    
    @abstractmethod
    async def remove_chunk_from_indexes(self, uuid: str, chunk_data: Dict[str, Any]) -> None:
        """
        Remove a chunk from all indexes.
        
        Args:
            uuid: Unique identifier of the chunk
            chunk_data: Chunk data to remove from indexes
            
        Raises:
            IndexOperationError: If removal fails
        """
        pass
    
    @abstractmethod
    async def search_by_field(self, field_name: str, value: Any, operator: str = "=") -> List[str]:
        """
        Search by a scalar field.
        
        Args:
            field_name: Name of the field to search
            value: Value to search for
            operator: Search operator to use
            
        Returns:
            List of UUIDs matching the search criteria
            
        Raises:
            IndexNotFoundError: If index does not exist
            IndexOperationError: If search fails
        """
        pass
    
    @abstractmethod
    async def search_by_array_element(self, field_name: str, element: Any) -> List[str]:
        """
        Search by an array element.
        
        Args:
            field_name: Name of the array field to search
            element: Element to search for
            
        Returns:
            List of UUIDs containing the element
            
        Raises:
            IndexNotFoundError: If index does not exist
            IndexOperationError: If search fails
        """
        pass
    
    @abstractmethod
    async def search_by_array_exact(self, field_name: str, array: List[Any]) -> List[str]:
        """
        Search by exact array match.
        
        Args:
            field_name: Name of the array field to search
            array: Array to search for exact match
            
        Returns:
            List of UUIDs with exact array match
            
        Raises:
            IndexNotFoundError: If index does not exist
            IndexOperationError: If search fails
        """
        pass
    
    @abstractmethod
    async def search_combined(self, criteria: Dict[str, Any]) -> List[str]:
        """
        Combined search by multiple criteria.
        
        Args:
            criteria: Dictionary of search criteria
            
        Returns:
            List of UUIDs matching all criteria
            
        Raises:
            IndexOperationError: If search fails
        """
        pass
    
    @abstractmethod
    async def get_index_stats(self) -> Dict[str, Any]:
        """
        Get statistics about all indexes.
        
        Returns:
            Dictionary with index statistics
        """
        pass
    
    @abstractmethod
    async def rebuild_indexes(self, field_names: Optional[List[str]] = None) -> None:
        """
        Rebuild indexes for specified fields or all fields.
        
        Args:
            field_names: List of field names to rebuild, None for all fields
            
        Raises:
            IndexOperationError: If rebuild fails
        """
        pass


# Utility Classes
class IndexUtils:
    """
    Utility class for index operations.
    
    Provides static methods for common index operations
    like value normalization, hash generation, and validation.
    
    Features:
    - Value normalization for consistent indexing
    - Array hash generation for exact matching
    - Range bucket calculation for numeric fields
    - Data validation utilities
    
    Architecture:
    - Stateless utility methods
    - Consistent with index storage format
    - Supports all data types used in indexing
    """
    
    @staticmethod
    def generate_array_hash(array: List[Any]) -> str:
        """
        Generate hash for exact array matching.
        
        Args:
            array: Array to generate hash for
            
        Returns:
            MD5 hash of sorted array elements
            
        Performance:
            Time complexity: O(n log n) for sorting
            Space complexity: O(n) for temporary storage
        """
        pass
    
    @staticmethod
    def normalize_value(value: Any) -> str:
        """
        Normalize value for indexing.
        
        Args:
            value: Value to normalize
            
        Returns:
            Normalized string representation
            
        Performance:
            Time complexity: O(1) for most types
            Space complexity: O(1) for most types
        """
        pass
    
    @staticmethod
    def get_range_bucket(value: Union[int, float], bucket_size: int = 100) -> str:
        """
        Get range bucket for numeric values.
        
        Args:
            value: Numeric value to bucket
            bucket_size: Size of each bucket
            
        Returns:
            String representation of the bucket range
            
        Performance:
            Time complexity: O(1)
            Space complexity: O(1)
        """
        ...
    
    @staticmethod
    def validate_chunk_data(chunk_data: Dict[str, Any]) -> bool:
        """
        Validate chunk data for indexing.
        
        Args:
            chunk_data: Chunk data to validate
            
        Returns:
            True if data is valid, False otherwise
            
        Raises:
            ValidationError: If data validation fails
        """
        ...
    
    @staticmethod
    def extract_indexable_fields(chunk_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract fields that should be indexed.
        
        Args:
            chunk_data: Chunk data to extract fields from
            
        Returns:
            Dictionary of indexable fields
        """
        ...


# Result Classes
class IndexResult:
    """
    Base result class for index operations.
    
    Provides common structure for all index operation results
    with success status and metadata.
    
    Features:
    - Success/failure status
    - Operation metadata
    - Error information
    - Performance metrics
    """
    
    def __init__(self, success: bool, data: Optional[Dict[str, Any]] = None, 
                 error: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize index result.
        
        Args:
            success: Whether the operation was successful
            data: Operation result data
            error: Error message if operation failed
            metadata: Additional metadata about the operation
        """
        self.success: bool = success
        """Whether the operation was successful."""
        
        self.data: Optional[Dict[str, Any]] = data
        """Operation result data."""
        
        self.error: Optional[str] = error
        """Error message if operation failed."""
        
        self.metadata: Optional[Dict[str, Any]] = metadata
        """Additional metadata about the operation."""
        
        self.timestamp: datetime = datetime.utcnow()
        """Timestamp of the operation."""
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert result to dictionary.
        
        Returns:
            Dictionary representation of the result
        """
        result = {
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata
        }
        
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}


class IndexStatsResult(IndexResult):
    """
    Result class for index statistics.
    
    Extends base result with specific statistics data
    for index operations and performance metrics.
    """
    
    def __init__(self, stats: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize index stats result.
        
        Args:
            stats: Index statistics data
            metadata: Additional metadata
        """
        super().__init__(True, {"stats": stats}, None, metadata)
        
        self.stats: Dict[str, Any] = stats
        """Index statistics data."""
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for index stats result.
        
        Returns:
            JSON schema for validation
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "stats": {
                            "type": "object",
                            "additionalProperties": True
                        }
                    }
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                },
                "timestamp": {"type": "string", "format": "date-time"}
            }
        }


class SearchResult(IndexResult):
    """
    Result class for search operations.
    
    Extends base result with search-specific data
    including results and search metadata.
    """
    
    def __init__(self, uuids: List[str], search_criteria: Dict[str, Any], 
                 metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize search result.
        
        Args:
            uuids: List of UUIDs matching search criteria
            search_criteria: Criteria used for search
            metadata: Additional search metadata
        """
        super().__init__(True, {"uuids": uuids, "search_criteria": search_criteria}, None, metadata)
        
        self.uuids: List[str] = uuids
        """List of UUIDs matching search criteria."""
        
        self.search_criteria: Dict[str, Any] = search_criteria
        """Criteria used for search."""
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for search result.
        
        Returns:
            JSON schema for validation
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "uuids": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "search_criteria": {
                            "type": "object",
                            "additionalProperties": True
                        }
                    }
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                },
                "timestamp": {"type": "string", "format": "date-time"}
            }
        }


# Factory Functions
def create_index_manager(redis_client: redis.Redis, config: Optional[Dict[str, Any]] = None) -> BaseIndexManager:
    """
    Factory function to create index manager instance.
    
    Args:
        redis_client: Redis client for index operations
        config: Optional configuration for index manager
        
    Returns:
        Configured index manager instance
        
    Raises:
        ValueError: If invalid configuration provided
    """
    if not redis_client:
        raise ValueError("Redis client is required")
    
    if config is not None and not validate_index_config(config):
        raise ValueError("Invalid configuration provided")
    
    # Import here to avoid circular imports
    from .atomic_operations import AtomicIndexManager
    
    manager = AtomicIndexManager(redis_client, config or {})
    # Note: initialize() should be called by the caller
    return manager


def validate_index_config(config: Dict[str, Any]) -> bool:
    """
    Validate index manager configuration.
    
    Args:
        config: Configuration to validate
        
    Returns:
        True if configuration is valid, False otherwise
        
    Raises:
        ValidationError: If configuration validation fails
    """
    if not isinstance(config, dict):
        raise ValidationError(f"Expected dictionary, got {type(config)}")
    
    # Validate required fields if present
    if 'batch_size' in config:
        if not isinstance(config['batch_size'], int) or config['batch_size'] <= 0:
            raise ValidationError("batch_size must be a positive integer")
    
    if 'ttl_days' in config:
        if not isinstance(config['ttl_days'], int) or config['ttl_days'] <= 0:
            raise ValidationError("ttl_days must be a positive integer")
    
    if 'enable_atomic_operations' in config:
        if not isinstance(config['enable_atomic_operations'], bool):
            raise ValidationError("enable_atomic_operations must be a boolean")
    
    return True
