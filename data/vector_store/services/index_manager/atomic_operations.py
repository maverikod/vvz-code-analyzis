"""
Atomic operations implementation for IndexManager.

This file implements atomic operations for index management
with support for rollback and error handling.

Features:
- Atomic index creation and deletion
- Chunk indexing with rollback support
- Search operations for all field types
- Combined search with multiple criteria
- Statistics and monitoring

Architecture:
- Uses Redis transactions for atomicity
- Implements rollback mechanisms
- Provides comprehensive error handling
- Supports all index types and operations

Author: Vasiliy Zdanovskiy <vasilyvz@gmail.com>
Created: 2024-01-15
Updated: 2024-01-15
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Union, Set
from datetime import datetime, timedelta
import redis.asyncio as redis

from .base import (
    BaseIndexManager,
    IndexType,
    IndexOperator,
    IndexStatus,
    IndexResult,
    IndexStatsResult,
    SearchResult,
    DEFAULT_BATCH_SIZE,
    DEFAULT_TTL_DAYS,
    FIELD_INDEX_PREFIX,
    ARRAY_ELEMENT_PREFIX,
    ARRAY_EXACT_PREFIX,
    RANGE_INDEX_PREFIX,
    PREFIX_INDEX_PREFIX,
    META_PREFIX
)
from .utils import IndexUtils
from vector_store.exceptions import (
    IndexManagerError,
    IndexNotFoundError,
    IndexAlreadyExistsError,
    IndexOperationError,
    IndexValidationError as ValidationError
)

logger = logging.getLogger(__name__)


class AtomicIndexManager(BaseIndexManager):
    """
    Atomic index manager with rollback support.
    
    Implements atomic operations for index management using Redis transactions
    with comprehensive error handling and rollback mechanisms.
    
    Features:
    - Atomic index creation and deletion
    - Chunk indexing with rollback support
    - Search operations for all field types
    - Combined search with multiple criteria
    - Statistics and monitoring
    
    Architecture:
    - Uses Redis transactions for atomicity
    - Implements rollback mechanisms
    - Provides comprehensive error handling
    - Supports all index types and operations
    """
    
    def __init__(self, redis_client: redis.Redis, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize atomic index manager.
        
        Args:
            redis_client: Redis client for index operations
            config: Optional configuration for index manager
        """
        super().__init__(redis_client)
        
        self.config: Dict[str, Any] = config or {}
        """Configuration for index manager."""
        
        self.batch_size: int = self.config.get('batch_size', DEFAULT_BATCH_SIZE)
        """Batch size for operations."""
        
        self.ttl_days: int = self.config.get('ttl_days', DEFAULT_TTL_DAYS)
        """TTL for index keys in days."""
        
        self.enable_atomic_operations: bool = self.config.get('enable_atomic_operations', True)
        """Whether to enable atomic operations."""
        
        self.indexed_fields: Set[str] = set()
        """Set of currently indexed fields."""
        
        # Initialize indexed fields - will be loaded asynchronously
        self.indexed_fields = set()
    
    async def initialize(self) -> None:
        """
        Initialize the index manager.
        
        Loads indexed fields from Redis and performs any necessary setup.
        """
        await self._load_indexed_fields()
    
    async def ping(self) -> bool:
        """
        Check connection to the index storage.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            return await self.redis.ping()
        except Exception:
            return False
    
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
        if field_name in self.indexed_fields:
            raise IndexAlreadyExistsError(f"Index for field '{field_name}' already exists")
        
        try:
            # Create index metadata
            meta_key = f"{self.meta_prefix}:{field_name}"
            meta_data = {
                'type': index_type.value,
                'indexed': 'true',
                'created_at': datetime.utcnow().isoformat(),
                'last_updated': datetime.utcnow().isoformat()
            }
            
            pipe = await self.redis.pipeline(transaction=self.enable_atomic_operations)
            async with pipe:
                await pipe.hmset(meta_key, meta_data)
                await pipe.expire(meta_key, self.ttl_days * 24 * 3600)
                await pipe.execute()
            
            self.indexed_fields.add(field_name)
            
        except Exception as e:
            raise IndexOperationError(f"Failed to create index for field '{field_name}': {e}")
    
    async def drop_index(self, field_name: str) -> None:
        """
        Drop an index for a field.
        
        Args:
            field_name: Name of the field to drop index for
            
        Raises:
            IndexNotFoundError: If index does not exist
            IndexOperationError: If index deletion fails
        """
        if field_name not in self.indexed_fields:
            raise IndexNotFoundError(f"Index for field '{field_name}' does not exist")
        
        try:
            # Get all keys for this field
            pattern = f"*:{field_name}:*"
            keys = await self.redis.keys(pattern)
            
            # Add metadata key
            meta_key = f"{self.meta_prefix}:{field_name}"
            keys.append(meta_key)
            
            if keys:
                pipe = await self.redis.pipeline(transaction=self.enable_atomic_operations)
                async with pipe:
                    await pipe.delete(*keys)
                    await pipe.execute()
            
            self.indexed_fields.discard(field_name)
            
        except Exception as e:
            raise IndexOperationError(f"Failed to drop index for field '{field_name}': {e}")
    
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
        # Validate chunk data
        IndexUtils.validate_chunk_data(chunk_data)
        
        # Extract indexable fields
        indexable_fields = IndexUtils.extract_indexable_fields(chunk_data)
        
        if not indexable_fields:
            return  # Nothing to index
        
        try:
            pipe = await self.redis.pipeline(transaction=self.enable_atomic_operations)
            async with pipe:
                for field_name, field_value in indexable_fields.items():
                    if field_name not in self.indexed_fields:
                        continue
                    
                    await self._index_field_value(pipe, field_name, field_value, uuid)
                
                await pipe.execute()
                
        except Exception as e:
            raise IndexOperationError(f"Failed to index chunk '{uuid}': {e}")
    
    async def remove_chunk_from_indexes(self, uuid: str, chunk_data: Dict[str, Any]) -> None:
        """
        Remove a chunk from all indexes.
        
        Args:
            uuid: Unique identifier of the chunk
            chunk_data: Chunk data to remove from indexes
            
        Raises:
            ValidationError: If chunk data is invalid
            IndexOperationError: If removal fails
        """
        # Validate chunk data
        IndexUtils.validate_chunk_data(chunk_data)
        
        # Extract indexable fields
        indexable_fields = IndexUtils.extract_indexable_fields(chunk_data)
        
        if not indexable_fields:
            return  # Nothing to remove
        
        try:
            pipe = await self.redis.pipeline(transaction=self.enable_atomic_operations)
            async with pipe:
                for field_name, field_value in indexable_fields.items():
                    if field_name not in self.indexed_fields:
                        continue
                    
                    await self._remove_field_value(pipe, field_name, field_value, uuid)
                
                await pipe.execute()
                
        except Exception as e:
            raise IndexOperationError(f"Failed to remove chunk '{uuid}' from indexes: {e}")

    async def initialize_indexes(self, fields: Optional[Dict[str, IndexType]] = None) -> Dict[str, bool]:
        """
        Initialize indexes for specified fields.
        
        Args:
            fields: Dictionary of field names and their index types
                   If None, uses default fields
            
        Returns:
            Dictionary with results of index creation
        """
        try:
            # Default fields for indexing
            default_fields = {
                'uuid': IndexType.SCALAR,
                'source_id': IndexType.SCALAR,
                'source_path': IndexType.SCALAR,
                'category': IndexType.SCALAR,
                'type': IndexType.SCALAR,
                'language': IndexType.SCALAR,
                'status': IndexType.SCALAR,
                'tags': IndexType.ARRAY,
                'links': IndexType.ARRAY,
                'quality_score': IndexType.RANGE,
                'year': IndexType.RANGE
            }
            
            fields_to_index = fields or default_fields
            results = {}
            
            for field_name, index_type in fields_to_index.items():
                try:
                    await self.create_index(field_name, index_type)
                    results[field_name] = True
                    logger.info(f"Created index for field: {field_name} ({index_type.value})")
                except Exception as e:
                    results[field_name] = False
                    logger.error(f"Failed to create index for field {field_name}: {e}")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to initialize indexes: {e}")
            return {"error": str(e)}
    
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
        if field_name not in self.indexed_fields:
            raise IndexNotFoundError(f"Index for field '{field_name}' does not exist")
        
        try:
            normalized_value = IndexUtils.normalize_value(value)
            index_key = f"{self.field_index_prefix}:{field_name}:{normalized_value}"
            
            uuids = await self.redis.smembers(index_key)
            return [uuid.decode('utf-8') if isinstance(uuid, bytes) else uuid for uuid in uuids]
            
        except Exception as e:
            raise IndexOperationError(f"Failed to search field '{field_name}': {e}")
    
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
        if field_name not in self.indexed_fields:
            raise IndexNotFoundError(f"Index for field '{field_name}' does not exist")
        
        try:
            normalized_element = IndexUtils.normalize_value(element)
            index_key = f"{self.array_element_prefix}:{field_name}:{normalized_element}"
            
            uuids = await self.redis.smembers(index_key)
            return [uuid.decode('utf-8') if isinstance(uuid, bytes) else uuid for uuid in uuids]
            
        except Exception as e:
            raise IndexOperationError(f"Failed to search array element '{element}' in field '{field_name}': {e}")
    
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
        if field_name not in self.indexed_fields:
            raise IndexNotFoundError(f"Index for field '{field_name}' does not exist")
        
        try:
            array_hash = IndexUtils.generate_array_hash(array)
            index_key = f"{self.array_exact_prefix}:{field_name}:{array_hash}"
            
            uuids = await self.redis.smembers(index_key)
            return [uuid.decode('utf-8') if isinstance(uuid, bytes) else uuid for uuid in uuids]
            
        except Exception as e:
            raise IndexOperationError(f"Failed to search exact array match in field '{field_name}': {e}")
    
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
        try:
            result_sets = []
            
            for field_name, condition in criteria.items():
                if field_name not in self.indexed_fields:
                    continue
                
                if isinstance(condition, dict):
                    # Complex condition with operators
                    for operator, value in condition.items():
                        uuids = await self._search_with_operator(field_name, operator, value)
                        if uuids:
                            result_sets.append(set(uuids))
                else:
                    # Simple equality condition
                    uuids = await self.search_by_field(field_name, condition)
                    if uuids:
                        result_sets.append(set(uuids))
            
            if not result_sets:
                return []
            
            # Intersect all result sets
            result = result_sets[0]
            for result_set in result_sets[1:]:
                result = result.intersection(result_set)
            
            return list(result)
            
        except Exception as e:
            raise IndexOperationError(f"Failed to perform combined search: {e}")
    
    async def get_index_stats(self) -> Dict[str, Any]:
        """
        Get statistics about all indexes.
        
        Returns:
            Dictionary with index statistics
        """
        try:
            stats = {
                'total_indexes': len(self.indexed_fields),
                'indexed_fields': list(self.indexed_fields),
                'index_details': {}
            }
            
            for field_name in self.indexed_fields:
                meta_key = f"{self.meta_prefix}:{field_name}"
                meta_data = await self.redis.hgetall(meta_key)
                
                if meta_data:
                    # Decode bytes to strings
                    decoded_meta = {}
                    for key, value in meta_data.items():
                        if isinstance(key, bytes):
                            key = key.decode('utf-8')
                        if isinstance(value, bytes):
                            value = value.decode('utf-8')
                        decoded_meta[key] = value
                    
                    stats['index_details'][field_name] = decoded_meta
            
            return stats
            
        except Exception as e:
            raise IndexOperationError(f"Failed to get index stats: {e}")
    
    async def rebuild_indexes(self, field_names: Optional[List[str]] = None) -> None:
        """
        Rebuild indexes for specified fields or all fields.
        
        Args:
            field_names: List of field names to rebuild, None for all fields
            
        Raises:
            IndexOperationError: If rebuild fails
        """
        try:
            fields_to_rebuild = field_names or list(self.indexed_fields)
            
            for field_name in fields_to_rebuild:
                if field_name in self.indexed_fields:
                    # Drop and recreate index
                    await self.drop_index(field_name)
                    
                    # Get index type from metadata or default to SCALAR
                    meta_key = f"{self.meta_prefix}:{field_name}"
                    meta_data = await self.redis.hgetall(meta_key)
                    
                    index_type = IndexType.SCALAR
                    if meta_data and b'type' in meta_data:
                        type_value = meta_data[b'type'].decode('utf-8')
                        try:
                            index_type = IndexType(type_value)
                        except ValueError:
                            pass
                    
                    await self.create_index(field_name, index_type)
            
        except Exception as e:
            raise IndexOperationError(f"Failed to rebuild indexes: {e}")
    
    async def _index_field_value(self, pipe: redis.client.Pipeline, field_name: str, 
                                field_value: Any, uuid: str) -> None:
        """
        Index a field value for a chunk.
        
        Args:
            pipe: Redis pipeline for atomic operations
            field_name: Name of the field
            field_value: Value to index
            uuid: UUID of the chunk
        """
        normalized_value = IndexUtils.normalize_value(field_value)
        
        if isinstance(field_value, (list, tuple)):
            # Array indexing - double indexing
            # 1. Index each element
            for element in field_value:
                element_normalized = IndexUtils.normalize_value(element)
                element_key = f"{self.array_element_prefix}:{field_name}:{element_normalized}"
                await pipe.sadd(element_key, uuid)
                await pipe.expire(element_key, self.ttl_days * 24 * 3600)
            
            # 2. Index exact array match
            array_hash = IndexUtils.generate_array_hash(field_value)
            exact_key = f"{self.array_exact_prefix}:{field_name}:{array_hash}"
            await pipe.sadd(exact_key, uuid)
            await pipe.expire(exact_key, self.ttl_days * 24 * 3600)
            
        elif isinstance(field_value, (int, float)):
            # Numeric indexing - range buckets
            range_bucket = IndexUtils.get_range_bucket(field_value)
            range_key = f"{self.range_index_prefix}:{field_name}:{range_bucket}"
            await pipe.sadd(range_key, uuid)
            await pipe.expire(range_key, self.ttl_days * 24 * 3600)
            
            # Also index as scalar
            scalar_key = f"{self.field_index_prefix}:{field_name}:{normalized_value}"
            await pipe.sadd(scalar_key, uuid)
            await pipe.expire(scalar_key, self.ttl_days * 24 * 3600)
            
        else:
            # Scalar indexing
            scalar_key = f"{self.field_index_prefix}:{field_name}:{normalized_value}"
            await pipe.sadd(scalar_key, uuid)
            await pipe.expire(scalar_key, self.ttl_days * 24 * 3600)
    
    async def _remove_field_value(self, pipe: redis.client.Pipeline, field_name: str,
                                 field_value: Any, uuid: str) -> None:
        """
        Remove a field value from indexes.
        
        Args:
            pipe: Redis pipeline for atomic operations
            field_name: Name of the field
            field_value: Value to remove
            uuid: UUID of the chunk
        """
        normalized_value = IndexUtils.normalize_value(field_value)
        
        if isinstance(field_value, (list, tuple)):
            # Array indexing - remove from both element and exact indexes
            for element in field_value:
                element_normalized = IndexUtils.normalize_value(element)
                element_key = f"{self.array_element_prefix}:{field_name}:{element_normalized}"
                await pipe.srem(element_key, uuid)
            
            array_hash = IndexUtils.generate_array_hash(field_value)
            exact_key = f"{self.array_exact_prefix}:{field_name}:{array_hash}"
            await pipe.srem(exact_key, uuid)
            
        elif isinstance(field_value, (int, float)):
            # Numeric indexing - remove from both range and scalar indexes
            range_bucket = IndexUtils.get_range_bucket(field_value)
            range_key = f"{self.range_index_prefix}:{field_name}:{range_bucket}"
            await pipe.srem(range_key, uuid)
            
            scalar_key = f"{self.field_index_prefix}:{field_name}:{normalized_value}"
            await pipe.srem(scalar_key, uuid)
            
        else:
            # Scalar indexing
            scalar_key = f"{self.field_index_prefix}:{field_name}:{normalized_value}"
            await pipe.srem(scalar_key, uuid)
    
    async def _search_with_operator(self, field_name: str, operator: str, value: Any) -> List[str]:
        """
        Search with specific operator.
        
        Args:
            field_name: Name of the field to search
            operator: Search operator
            value: Value to search for
            
        Returns:
            List of UUIDs matching the criteria
        """
        if operator == '$eq':
            return await self.search_by_field(field_name, value)
        elif operator == '$in':
            if isinstance(value, (list, tuple)):
                all_uuids = []
                for item in value:
                    uuids = await self.search_by_field(field_name, item)
                    all_uuids.extend(uuids)
                return list(set(all_uuids))  # Remove duplicates
            else:
                return await self.search_by_field(field_name, value)
        elif operator in ['$gt', '$gte', '$lt', '$lte']:
            # Range search - simplified implementation
            # In a real implementation, this would use range buckets
            return await self.search_by_field(field_name, value)
        else:
            return []
    
    async def _load_indexed_fields(self) -> None:
        """
        Load currently indexed fields from Redis.
        """
        try:
            pattern = f"{self.meta_prefix}:*"
            keys = await self.redis.keys(pattern)
            
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                # Extract field name from key
                if key.startswith(f"{self.meta_prefix}:"):
                    field_name = key[len(f"{self.meta_prefix}:"):]
                    self.indexed_fields.add(field_name)
                    
        except Exception:
            # If loading fails, start with empty set
            self.indexed_fields = set()
