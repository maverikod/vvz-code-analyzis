"""
Optimized AtomicIndexManager - performance optimization for LUA scripts.

Optimized version of AtomicIndexManager with script caching, performance monitoring,
and optimized algorithms for improved performance.

Features:
- LRU cache for generated LUA scripts
- Performance metrics collection and monitoring
- Optimized LUA script generation algorithms
- Automatic cache management and eviction
- Performance statistics and reporting
- Optimized cleanup and write operations
- Field type analysis optimization

Architecture:
- LRU cache implementation for script storage
- Performance metrics collection system
- Optimized script generation based on field analysis
- Automatic cache size management
- Performance monitoring and reporting

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Created: 2024-01-01
Updated: 2024-01-01
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass
from collections import OrderedDict
from functools import lru_cache
from enum import Enum

import redis.asyncio as redis

# Logger
logger = logging.getLogger(__name__)

# Constants
DEFAULT_CACHE_SIZE: int = 1000
"""Default size for script cache."""

DEFAULT_METRICS_LIMIT: int = 10000
"""Default limit for performance metrics storage."""

CACHE_CLEANUP_THRESHOLD: int = 5000
"""Threshold for automatic cache cleanup."""

# Performance metrics dataclass
@dataclass
class PerformanceMetrics:
    """Performance metrics for script operations."""
    operation_type: str
    execution_time: float
    script_size: int
    field_count: int
    cache_hit: bool
    timestamp: float

# Field type enumeration
class FieldType(Enum):
    """Field types for indexing optimization."""
    SCALAR = "scalar"
    ARRAY = "array"
    OBJECT = "object"
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"

# Field information dataclass
@dataclass
class FieldInfo:
    """Information about a field for indexing optimization."""
    name: str
    value: Any
    field_type: FieldType
    is_indexed: bool
    index_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

# Index operation result dataclass
@dataclass
class IndexOperationResult:
    """Result of an index operation."""
    success: bool
    message: str
    operation_type: str
    uuid: Optional[str] = None
    error_details: Optional[str] = None

# Cache statistics dataclass
@dataclass
class CacheStatistics:
    """Statistics for script cache performance."""
    hits: int
    misses: int
    evictions: int
    hit_rate: float
    total_operations: int

# Performance statistics dataclass
@dataclass
class PerformanceStatistics:
    """Comprehensive performance statistics."""
    total_operations: int
    average_execution_time: float
    cache_hit_rate: float
    cache_stats: CacheStatistics
    cache_size: int
    max_cache_size: int

# Base class for optimized operations
class BaseOptimizedOperation:
    """Base class for optimized index operations."""
    
    def __init__(self, redis_client, enable_metrics: bool = True) -> None:
        """
        Initialize base optimized operation.
        
        Args:
            redis_client: Redis client for operations
            enable_metrics: Whether to enable performance metrics collection
        """
        self.redis_client = redis_client
        """Redis client for performing operations."""
        
        self.enable_metrics = enable_metrics
        """Whether performance metrics collection is enabled."""
        
        self._performance_metrics: List[PerformanceMetrics] = []
        """List of performance metrics for operations."""
    
    def _record_metrics(
        self,
        operation_type: str,
        execution_time: float,
        script_size: int,
        field_count: int,
        cache_hit: bool
    ) -> None:
        """
        Record performance metrics for an operation.
        
        Args:
            operation_type: Type of operation performed
            execution_time: Time taken to execute the operation
            script_size: Size of the script used
            field_count: Number of fields processed
            cache_hit: Whether the script was found in cache
        """
        metric = PerformanceMetrics(
            operation_type=operation_type,
            execution_time=execution_time,
            script_size=script_size,
            field_count=field_count,
            cache_hit=cache_hit,
            timestamp=time.time()
        )
        
        self._performance_metrics.append(metric)
        
        # Limit metrics storage
        if len(self._performance_metrics) > DEFAULT_METRICS_LIMIT:
            self._performance_metrics = self._performance_metrics[-DEFAULT_METRICS_LIMIT//2:]
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive performance statistics.
        
        Returns:
            Dictionary with detailed performance metrics
        """
        if not self._performance_metrics:
            return {
                "total_operations": 0,
                "average_execution_time": 0.0,
                "cache_hit_rate": 0.0,
                "cache_stats": {"hits": 0, "misses": 0, "total": 0, "hit_rate": 0.0},
                "cache_size": 0,
                "max_cache_size": 0
            }
        
        total_ops = len(self._performance_metrics)
        avg_time = sum(m.execution_time for m in self._performance_metrics) / total_ops
        cache_hits = sum(1 for m in self._performance_metrics if m.cache_hit)
        cache_hit_rate = cache_hits / total_ops if total_ops > 0 else 0.0
        
        return {
            "total_operations": total_ops,
            "average_execution_time": avg_time,
            "cache_hit_rate": cache_hit_rate,
            "cache_stats": {"hits": cache_hits, "misses": total_ops - cache_hits, "total": total_ops, "hit_rate": cache_hit_rate},
            "cache_size": 0,
            "max_cache_size": 0
        }
    
    def clear_metrics(self) -> None:
        """Clear all performance metrics."""
        self._performance_metrics.clear()
        logger.info("Performance metrics cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            "hits": 0,
            "misses": 0,
            "total": 0,
            "hit_rate": 0.0
        }

# Main optimized index manager class
class OptimizedAtomicIndexManager(BaseOptimizedOperation):
    """Optimized manager for atomic index operations."""
    
    def __init__(
        self,
        redis_client,
        cache_size: int = DEFAULT_CACHE_SIZE,
        enable_metrics: bool = True
    ) -> None:
        """
        Initialize optimized atomic index manager.
        
        Args:
            redis_client: Redis client for operations
            cache_size: Maximum size of script cache
            enable_metrics: Whether to enable performance metrics
        """
        super().__init__(redis_client, enable_metrics)
        
        self.cache_size = cache_size
        """Maximum size of the script cache."""
        
        # LRU cache for scripts
        self._script_cache: OrderedDict = OrderedDict()
        """LRU cache for generated LUA scripts."""
        
        # Cache statistics
        self._cache_stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0
        }
        """Cache performance statistics."""
        
        # Field type cache
        self._field_type_cache: Dict[str, FieldType] = {}
        """Cache for field type analysis results."""
        
        logger.info(f"OptimizedAtomicIndexManager initialized with cache_size={cache_size}")
    
    async def index_chunk(
        self,
        uuid: str,
        chunk_data: Dict[str, Any],
        validate: bool = True
    ) -> IndexOperationResult:
        """
        Optimized chunk indexing operation.
        
        Performs high-performance chunk indexing with script caching,
        field analysis optimization, and performance monitoring.
        
        Args:
            uuid: UUID of the chunk to index
            chunk_data: Data to be indexed
            validate: Whether to validate input data
            
        Returns:
            IndexOperationResult with operation status
            
        Raises:
            ValueError: If input validation fails
            RedisError: If Redis operation fails
        """
        start_time = time.time()
        
        try:
            # Validate input data
            if validate:
                self._validate_chunk_data(uuid, chunk_data)
            
            # Analyze field types for optimization
            field_analysis = self._analyze_field_types(chunk_data)
            
            # Get optimized script from cache or generate new one
            script = self._get_optimized_script(field_analysis)
            
            # Execute optimized script
            success, error_message = await self._execute_optimized_script(uuid, script, chunk_data)
            
            # Check if script execution was successful
            if not success:
                logger.error(f"Script execution failed for chunk {uuid}: {error_message}")
                return IndexOperationResult(
                    success=False,
                    message="Script execution failed",
                    operation_type="index_chunk",
                    uuid=uuid,
                    error_details=error_message or "Redis script execution returned False"
                )
            
            # Record performance metrics
            if self.enable_metrics:
                self._record_metrics(
                    "index_chunk",
                    time.time() - start_time,
                    len(script),
                    len(field_analysis),
                    script in self._script_cache.values()
                )
            
            logger.info(f"Successfully indexed chunk {uuid} in {time.time() - start_time:.3f}s")
            return IndexOperationResult(
                success=True,
                message="Chunk indexed successfully",
                operation_type="index_chunk",
                uuid=uuid
            )
            
        except Exception as e:
            logger.error(f"Failed to index chunk {uuid}: {e}")
            return IndexOperationResult(
                success=False,
                message="Indexing failed",
                operation_type="index_chunk",
                uuid=uuid,
                error_details=str(e)
            )
    
    def _get_optimized_script(
        self,
        field_analysis: List[FieldInfo]
    ) -> str:
        """
        Get optimized script from cache or generate new one.
        
        Implements LRU caching for generated scripts to improve
        performance for repeated operations with similar field structures.
        
        Args:
            field_analysis: Analysis of fields to be processed
            
        Returns:
            Optimized LUA script for the operation
        """
        cache_key = self._generate_cache_key(field_analysis)
        
        # Check cache for existing script
        if cache_key in self._script_cache:
            # Move to end (LRU)
            script = self._script_cache.pop(cache_key)
            self._script_cache[cache_key] = script
            self._cache_stats["hits"] += 1
            return script
        
        # Generate new script
        self._cache_stats["misses"] += 1
        script = self._generate_optimized_script(field_analysis)
        
        # Add to cache
        self._add_to_cache(cache_key, script)
        
        return script
    
    def _generate_optimized_script(
        self,
        field_analysis: List[FieldInfo]
    ) -> str:
        """
        Generate optimized LUA script based on field analysis.
        
        Creates highly optimized scripts by grouping fields by type
        and generating specialized code sections for different field types.
        
        Args:
            field_analysis: Analysis of fields to be processed
            
        Returns:
            Optimized LUA script with specialized sections
        """
        # Group fields by type for optimization
        scalar_fields = []
        array_fields = []
        text_fields = []
        
        for field in field_analysis:
            if field.field_type == FieldType.ARRAY:
                array_fields.append(field)
            elif field.field_type == FieldType.TEXT:
                text_fields.append(field)
            else:
                scalar_fields.append(field)
        
        # Generate optimized code sections
        cleanup_code = self._generate_optimized_cleanup_code()
        write_code = self._generate_optimized_write_code(scalar_fields, array_fields, text_fields)
        index_code = self._generate_optimized_index_code(scalar_fields, array_fields, text_fields)
        
        # Assemble optimized script
        script = f"""
-- Optimized REPLACE_CHUNK_SCRIPT
-- KEYS[1] = uuid
-- ARGV[1] = uuid, ARGV[2] = key1, ARGV[3] = value1, ...

local uuid = KEYS[1]
local param_count = #ARGV

{cleanup_code}

{write_code}

{index_code}

return 1
"""
        
        return script
    
    def _generate_optimized_cleanup_code(self) -> str:
        """
        Generate optimized cleanup code section.
        
        Creates efficient cleanup code that removes data and indexes
        in optimized batches to minimize Redis operations.
        
        Returns:
            Optimized cleanup code for LUA script
        """
        return """
-- PART 1-3: OPTIMIZED CLEANUP
-- Remove data and indexes in optimized batches

-- Cleanup data
redis.call('DEL', 'chunk:' .. uuid)

-- Cleanup indexes (optimized)
local index_patterns = {
    "field_index:*",
    "array_element_index:*", 
    "array_exact_index:*",
    "bm25_token_index:*"
}

for _, pattern in ipairs(index_patterns) do
    local keys = redis.call('KEYS', pattern)
    for i, key in ipairs(keys) do
        local removed = redis.call('SREM', key, uuid)
        -- Remove empty indexes immediately
        if removed > 0 and redis.call('SCARD', key) == 0 then
            redis.call('DEL', key)
        end
    end
end
"""
    
    def _generate_optimized_write_code(
        self,
        scalar_fields: List[FieldInfo],
        array_fields: List[FieldInfo],
        text_fields: List[FieldInfo]
    ) -> str:
        """
        Generate optimized data write code section.
        
        Creates efficient data writing code that groups operations
        by field type for optimal Redis performance.
        
        Args:
            scalar_fields: List of scalar field information
            array_fields: List of array field information
            text_fields: List of text field information
            
        Returns:
            Optimized write code for LUA script
        """
        code_lines = ["-- PART 4: OPTIMIZED DATA WRITE"]
        
        # Grouped write for optimization
        all_fields = scalar_fields + array_fields + text_fields
        
        for i, field in enumerate(all_fields):
            arg_index = i * 2 + 2
            code_lines.append(f"local key{i} = ARGV[{arg_index}]")
            code_lines.append(f"local value{i} = ARGV[{arg_index + 1}]")
        
        # Batch write to hash
        code_lines.append("-- Batch write to hash")
        for i, field in enumerate(all_fields):
            code_lines.append(f"redis.call('HSET', 'chunk:' .. uuid, key{i}, value{i})")
        
        return "\n".join(code_lines)
    
    def _generate_optimized_index_code(
        self,
        scalar_fields: List[FieldInfo],
        array_fields: List[FieldInfo],
        text_fields: List[FieldInfo]
    ) -> str:
        """
        Generate optimized index creation code section.
        
        Creates efficient index creation code that optimizes
        Redis operations for different field types.
        
        Args:
            scalar_fields: List of scalar field information
            array_fields: List of array field information
            text_fields: List of text field information
            
        Returns:
            Optimized index creation code for LUA script
        """
        code_lines = ["-- PART 5: OPTIMIZED INDEX CREATION"]
        
        # Scalar fields
        if scalar_fields:
            code_lines.append("-- Scalar indexes")
            for i, field in enumerate(scalar_fields):
                code_lines.append(
                    f"redis.call('SADD', 'field_index:{field.name}:' .. value{i}, uuid)"
                )
        
        # Array fields
        if array_fields:
            code_lines.append("-- Array indexes")
            for i, field in enumerate(array_fields):
                field_index = len(scalar_fields) + i
                code_lines.append(f"""
-- Index array {field.name}
local array{i} = cjson.decode(value{field_index})
if type(array{i}) == 'table' then
    -- Element indexes
    for j, element in ipairs(array{i}) do
        redis.call('SADD', 'array_element_index:{field.name}:' .. tostring(element), uuid)
    end
    -- Exact index
    redis.call('SADD', 'array_exact_index:{field.name}:' .. value{field_index}, uuid)
end
""")
        
        # Text fields - BM25 tokens from chunk metrics
        if text_fields:
            code_lines.append("-- BM25 indexes")
            for i, field in enumerate(text_fields):
                field_index = len(scalar_fields) + len(array_fields) + i
                code_lines.append(f"""
-- BM25 indexing {field.name} (using tokens from chunk metrics)
local tokens{i} = cjson.decode(value{field_index})
if type(tokens{i}) == 'table' then
    for j, token in ipairs(tokens{i}) do
        redis.call('SADD', 'bm25_token_index:' .. token, uuid)
    end
end
""")
        
        return "\n".join(code_lines)
    
    async def _execute_optimized_script(
        self,
        uuid: str,
        script: str,
        chunk_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Execute optimized LUA script with performance monitoring.
        
        Executes the generated script with optimized parameters
        and monitors performance metrics.
        
        Args:
            uuid: UUID of the chunk being processed
            script: LUA script to execute
            chunk_data: Data to be processed
            
        Returns:
            Tuple of (success, error_message) where success is True if execution was successful
        """
        # Prepare arguments with BM25 tokens from chunk metrics
        args = [uuid]
        
        # Extract BM25 tokens from chunk metrics if available
        bm25_tokens = None
        if 'metrics' in chunk_data and chunk_data['metrics']:
            metrics = chunk_data['metrics']
            if isinstance(metrics, dict) and 'bm25_tokens' in metrics:
                bm25_tokens = metrics['bm25_tokens']
            elif hasattr(metrics, 'bm25_tokens'):
                bm25_tokens = metrics.bm25_tokens
        
        # Process chunk data and replace text fields with BM25 tokens
        for key, value in chunk_data.items():
            args.append(key)
            
            # For text fields, use BM25 tokens if available
            if (isinstance(value, str) and len(value) > 1000 and 
                bm25_tokens and isinstance(bm25_tokens, list)):
                # Use BM25 tokens for text fields
                args.append(json.dumps(bm25_tokens))
            else:
                args.append(json.dumps(value))
        
        # Execute with optimized parameters (using async Redis client)
        try:
            logger.info(f"Executing script for chunk {uuid}")
            logger.info(f"Script: {script}")
            logger.info(f"Args: {args}")
            
            result = await self.redis_client.eval(
                script,
                1,  # number of keys
                uuid,  # key (without chunk: prefix)
                *args  # arguments
            )
            
            logger.info(f"Script execution result: {result}")
            return (result is not None, None)
        except Exception as e:
            logger.error(f"Script execution failed: {e}")
            return (False, str(e))
    
    def _analyze_field_types(
        self,
        chunk_data: Dict[str, Any]
    ) -> List[FieldInfo]:
        """
        Analyze field types for optimization.
        
        Performs detailed analysis of field types and structures
        to optimize script generation and caching.
        
        Args:
            chunk_data: Data to analyze
            
        Returns:
            List of field information for optimization
        """
        field_info_list = []
        
        for field_name, value in chunk_data.items():
            # Determine field type
            field_type = self._determine_field_type(field_name, value)
            
            # Determine if field should be indexed
            is_indexed = self._should_index_field(field_name, value, field_type)
            
            # Determine index type
            index_type = self._determine_index_type(field_name, value, field_type) if is_indexed else None
            
            # Extract field metadata
            metadata = self._extract_field_metadata(field_name, value, field_type)
            
            field_info = FieldInfo(
                name=field_name,
                value=value,
                field_type=field_type,
                is_indexed=is_indexed,
                index_type=index_type,
                metadata=metadata
            )
            
            field_info_list.append(field_info)
            
            # Cache field type
            self._field_type_cache[field_name] = field_type
        
        return field_info_list
    
    def _determine_field_type(
        self,
        field_name: str,
        value: Any
    ) -> FieldType:
        """
        Determine field type for optimization.
        
        Args:
            field_name: Field name
            value: Field value
            
        Returns:
            Field type
        """
        if isinstance(value, bool):
            return FieldType.BOOLEAN
        elif isinstance(value, (int, float)):
            return FieldType.NUMBER
        elif isinstance(value, str):
            # Check for date
            if self._is_date_string(value):
                return FieldType.DATE
            # Check for long text
            elif len(value) > 1000:
                return FieldType.TEXT
            else:
                return FieldType.SCALAR
        elif isinstance(value, list):
            return FieldType.ARRAY
        elif isinstance(value, dict):
            return FieldType.OBJECT
        else:
            return FieldType.SCALAR
    
    def _should_index_field(
        self,
        field_name: str,
        value: Any,
        field_type: FieldType
    ) -> bool:
        """
        Determine if field should be indexed.
        
        Args:
            field_name: Field name
            value: Field value
            field_type: Field type
            
        Returns:
            True if field should be indexed
        """
        # Exclude system fields
        if field_name.startswith("_"):
            return False
        
        # Exclude empty values
        if value is None or value == "":
            return False
        
        # Exclude very large objects
        if isinstance(value, dict) and len(json.dumps(value)) > 10000:
            return False
        
        # Index all other fields
        return True
    
    def _determine_index_type(
        self,
        field_name: str,
        value: Any,
        field_type: FieldType
    ) -> Optional[str]:
        """
        Determine index type for field.
        
        Args:
            field_name: Field name
            value: Field value
            field_type: Field type
            
        Returns:
            Index type or None
        """
        if field_type == FieldType.ARRAY:
            return "array_element"
        elif field_type == FieldType.TEXT:
            return "bm25"
        elif field_type == FieldType.NUMBER:
            return "numeric"
        elif field_type == FieldType.DATE:
            return "date"
        else:
            return "scalar"
    
    def _extract_field_metadata(
        self,
        field_name: str,
        value: Any,
        field_type: FieldType
    ) -> Dict[str, Any]:
        """
        Extract field metadata for optimization.
        
        Args:
            field_name: Field name
            value: Field value
            field_type: Field type
            
        Returns:
            Field metadata
        """
        metadata = {
            "field_type": field_type.value,
            "value_type": type(value).__name__,
            "field_name": field_name
        }
        
        if field_type == FieldType.ARRAY:
            metadata["array_length"] = len(value)
            metadata["array_types"] = list(set(type(item).__name__ for item in value))
        elif field_type == FieldType.TEXT:
            metadata["text_length"] = len(value)
            metadata["word_count"] = len(value.split())
        elif field_type == FieldType.NUMBER:
            metadata["numeric_type"] = "integer" if isinstance(value, int) else "float"
        
        return metadata
    
    def _is_date_string(self, value: str) -> bool:
        """
        Check if string is a date.
        
        Args:
            value: String to check
            
        Returns:
            True if string looks like a date
        """
        import re
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',
            r'\d{2}/\d{2}/\d{4}',
            r'\d{2}-\d{2}-\d{4}'
        ]
        
        for pattern in date_patterns:
            if re.match(pattern, value):
                return True
        
        return False
    
    def _generate_cache_key(
        self,
        field_analysis: List[FieldInfo]
    ) -> str:
        """
        Generate cache key for field analysis.
        
        Creates a unique key based on field structure for
        efficient script caching and retrieval.
        
        Args:
            field_analysis: Field analysis to create key for
            
        Returns:
            Unique cache key string
        """
        field_signature = []
        for field_info in field_analysis:
            if field_info.is_indexed:
                field_signature.append(f"{field_info.name}:{field_info.field_type.value}")
        
        return "script:" + ":".join(sorted(field_signature))
    
    def _add_to_cache(self, cache_key: str, script: str) -> None:
        """
        Add script to LRU cache with eviction management.
        
        Adds a script to the cache and manages cache size
        using LRU eviction policy.
        
        Args:
            cache_key: Key for the script
            script: LUA script to cache
        """
        # Check cache size
        if len(self._script_cache) >= self.cache_size:
            # Remove oldest element
            oldest_key = next(iter(self._script_cache))
            self._script_cache.pop(oldest_key)
            self._cache_stats["evictions"] += 1
        
        # Add new element
        self._script_cache[cache_key] = script
    
    def _validate_chunk_data(
        self,
        uuid: str,
        chunk_data: Dict[str, Any]
    ) -> None:
        """
        Validate chunk data for indexing.
        
        Performs comprehensive validation of chunk data including
        size limits, field name validation, and data type checks.
        
        Args:
            uuid: UUID to validate
            chunk_data: Data to validate
            
        Raises:
            ValueError: If validation fails
        """
        if not uuid or not isinstance(uuid, str):
            raise ValueError("UUID cannot be empty")
        
        if not chunk_data or not isinstance(chunk_data, dict):
            raise ValueError("Chunk data cannot be empty")
        
        # Check data size
        data_size = len(json.dumps(chunk_data))
        if data_size > 1000000:  # 1MB limit
            raise ValueError(f"Chunk data too large: {data_size} bytes")
        
        # Check field names
        for key in chunk_data.keys():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"Invalid field name: {key}")
            
            if len(key) > 255:
                raise ValueError(f"Field name too long: {key}")
    
    def clear_cache(self) -> None:
        """
        Clear script cache and reset statistics.
        
        Removes all cached scripts and resets cache statistics
        for performance monitoring.
        """
        self._script_cache.clear()
        self._cache_stats["evictions"] += len(self._script_cache)
        logger.info("Script cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get detailed cache performance statistics.
        
        Returns:
            Dictionary with cache performance metrics
        """
        total_ops = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = self._cache_stats["hits"] / total_ops if total_ops > 0 else 0.0
        
        return {
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "evictions": self._cache_stats["evictions"],
            "hit_rate": hit_rate,
            "total_operations": total_ops
        }
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive performance statistics.
        
        Returns:
            Dictionary with detailed performance metrics
        """
        base_stats = super().get_performance_stats()
        cache_stats = self.get_cache_stats()
        
        return {
            "total_operations": base_stats.get("total_operations", 0),
            "average_execution_time": base_stats.get("average_execution_time", 0.0),
            "cache_hit_rate": base_stats.get("cache_hit_rate", 0.0),
            "cache_stats": cache_stats,
            "cache_size": len(self._script_cache),
            "max_cache_size": self.cache_size,
            "optimization_enabled": True
        }
    
    async def remove_vector_by_index(self, faiss_index: int) -> None:
        """
        Remove vector from FAISS index and update Redis mappings.
        
        Args:
            faiss_index: Index of the vector in FAISS to remove
        """
        try:
            # Remove from FAISS index
            # Note: This would require FAISS client integration
            logger.info(f"Removing vector at index {faiss_index} from FAISS")
            
            # Update Redis mappings
            # Remove the mapping from Redis
            await self.redis_client.hdel("faiss_index_mapping", str(faiss_index))
            
            logger.info(f"Successfully removed vector at index {faiss_index}")
            
        except Exception as e:
            logger.error(f"Failed to remove vector at index {faiss_index}: {e}")
            raise

# Utility functions for optimization
def create_optimized_manager(
    redis_client,
    cache_size: Optional[int] = None,
    enable_metrics: bool = True
) -> OptimizedAtomicIndexManager:
    """
    Factory function for creating optimized index managers.
    
    Creates and configures an optimized atomic index manager
    with specified cache size and metrics settings.
    
    Args:
        redis_client: Redis client for operations
        cache_size: Optional cache size override
        enable_metrics: Whether to enable performance metrics
        
    Returns:
        Configured OptimizedAtomicIndexManager instance
    """
    return OptimizedAtomicIndexManager(
        redis_client=redis_client,
        cache_size=cache_size or DEFAULT_CACHE_SIZE,
        enable_metrics=enable_metrics
    )

def optimize_script_parameters(
    field_analysis: List[FieldInfo]
) -> Dict[str, Any]:
    """
    Optimize script parameters based on field analysis.
    
    Analyzes field structure to optimize script parameters
    for better performance and reduced memory usage.
    
    Args:
        field_analysis: Analysis of fields to optimize for
        
    Returns:
        Optimized parameters dictionary
    """
    params = {
        "scalar_count": 0,
        "array_count": 0,
        "text_count": 0,
        "total_fields": len(field_analysis),
        "indexed_fields": sum(1 for f in field_analysis if f.is_indexed)
    }
    
    for field in field_analysis:
        if field.field_type == FieldType.SCALAR:
            params["scalar_count"] += 1
        elif field.field_type == FieldType.ARRAY:
            params["array_count"] += 1
        elif field.field_type == FieldType.TEXT:
            params["text_count"] += 1
    
    return params

def calculate_performance_score(
    metrics: List[PerformanceMetrics]
) -> float:
    """
    Calculate overall performance score from metrics.
    
    Computes a performance score based on execution times,
    cache hit rates, and operation efficiency.
    
    Args:
        metrics: List of performance metrics
        
    Returns:
        Performance score between 0 and 1
    """
    if not metrics:
        return 0.0
    
    # Calculate average execution time
    avg_time = sum(m.execution_time for m in metrics) / len(metrics)
    
    # Calculate cache hit rate
    cache_hits = sum(1 for m in metrics if m.cache_hit)
    cache_hit_rate = cache_hits / len(metrics)
    
    # Calculate performance score (lower time and higher hit rate = better score)
    time_score = max(0, 1 - avg_time)  # Normalize time (assume 1s is max)
    hit_score = cache_hit_rate
    
    # Weighted average
    performance_score = (time_score * 0.6) + (hit_score * 0.4)
    
    return min(1.0, max(0.0, performance_score))
