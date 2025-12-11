"""
Utilities for vector store command processing and utilities.

This module provides data processing, metadata, security, performance, and utility functions
for command operations.

Features:
- DataProcessor for batch and single chunk operations
- MetadataProcessor for metadata validation and transformation
- SecurityUtils for security checks and sanitization
- PerformanceMonitor for performance metrics
- Utility functions for UUID, hashing, timestamps, batching, retry

Architecture:
- Standalone processing and utility classes/functions
- Integration with chunk_metadata_adapter
- Comprehensive error handling

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
import time
import hashlib
import uuid
import re
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime, timezone
from chunk_metadata_adapter import SemanticChunk, ChunkQuery
from vector_store.exceptions import ValidationError, InvalidParamsError

logger = logging.getLogger("vector_store.utils.command")


class DataProcessor:
    """
    Processor for data transformation and validation.
    
    Provides utilities for processing and transforming data
    between different formats and structures.
    
    Features:
    - Data format conversion
    - Batch processing
    - Data validation
    - Performance optimization
    """
    
    def __init__(self) -> None:
        """Initialize data processor."""
        self.chunk_validator = None  # SemanticChunkValidator will be injected if needed
    
    def process_chunks_batch(
        self,
        chunks_data: List[Dict[str, Any]]
    ) -> List[SemanticChunk]:
        """
        Process batch of chunk data.
        
        Args:
            chunks_data: List of chunk data dictionaries
            
        Returns:
            List of validated SemanticChunk objects
            
        Raises:
            ValidationError: If any chunk is invalid
        """
        processed_chunks = []
        errors = []
        
        for i, chunk_data in enumerate(chunks_data):
            try:
                chunk = self.convert_to_semantic_chunk(chunk_data)
                processed_chunks.append(chunk)
            except Exception as e:
                errors.append(f"Chunk {i}: {str(e)}")
        
        if errors:
            raise ValidationError(
                message="Batch processing failed",
                data={"validation_errors": errors}
            )
        
        return processed_chunks
    
    def convert_to_semantic_chunk(
        self,
        chunk_data: Dict[str, Any]
    ) -> SemanticChunk:
        """
        Convert dictionary to SemanticChunk.
        
        Args:
            chunk_data: Chunk data dictionary
            
        Returns:
            SemanticChunk object
            
        Raises:
            ValidationError: If data is invalid
        """
        try:
            chunk = SemanticChunk(**chunk_data)
            # Optionally validate the created chunk if validator is set
            if self.chunk_validator:
                is_valid, errors = self.chunk_validator.validate_chunk(chunk)
                if not is_valid:
                    raise ValidationError(
                        message="Invalid chunk data",
                        data={"validation_errors": errors}
                    )
            return chunk
        except Exception as e:
            raise ValidationError(
                message=f"Failed to create SemanticChunk: {str(e)}"
            )
    
    def convert_from_semantic_chunk(
        self,
        chunk: SemanticChunk
    ) -> Dict[str, Any]:
        """
        Convert SemanticChunk to dictionary.
        
        Args:
            chunk: SemanticChunk object
            
        Returns:
            Dictionary representation
        """
        result = {}
        # If validator is set, use its fields, else use default
        fields = []
        if self.chunk_validator:
            fields = self.chunk_validator.required_fields + self.chunk_validator.optional_fields
        else:
            fields = ['text', 'uuid', 'metadata', 'embedding', 'source_id']
        for field in fields:
            if hasattr(chunk, field):
                value = getattr(chunk, field)
                if value is not None:
                    result[field] = value
        return result
    
    def validate_batch(
        self,
        chunks: List[SemanticChunk]
    ) -> Tuple[List[SemanticChunk], List[str]]:
        """
        Validate batch of chunks.
        
        Args:
            chunks: List of SemanticChunk objects
            
        Returns:
            Tuple of (valid_chunks, error_messages)
        """
        valid_chunks = []
        error_messages = []
        if not self.chunk_validator:
            return chunks, error_messages
        for i, chunk in enumerate(chunks):
            is_valid, errors = self.chunk_validator.validate_chunk(chunk)
            if is_valid:
                valid_chunks.append(chunk)
            else:
                error_messages.append(f"Chunk {i}: {', '.join(errors)}")
        return valid_chunks, error_messages


class MetadataProcessor:
    """
    Processor for metadata operations.
    
    Provides utilities for processing, validating, and transforming
    metadata dictionaries.
    
    Features:
    - Metadata validation
    - Metadata transformation
    - Metadata filtering
    - Metadata merging
    """
    
    def __init__(self) -> None:
        """Initialize metadata processor."""
        self.allowed_types = ["str", "int", "float", "bool", "list", "dict"]
    
    def validate_metadata(
        self,
        metadata: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate metadata dictionary.
        
        Args:
            metadata: Metadata to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        if not isinstance(metadata, dict):
            errors.append("Metadata must be a dictionary")
            return False, errors
        for key, value in metadata.items():
            if not isinstance(key, str):
                errors.append(f"Metadata key must be string: {key}")
                continue
            if not self._is_valid_metadata_value(value):
                errors.append(f"Invalid metadata value type for key '{key}': {type(value)}")
        return len(errors) == 0, errors
    
    def transform_metadata(
        self,
        metadata: Dict[str, Any],
        transformations: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Transform metadata using specified transformations.
        
        Args:
            metadata: Metadata to transform
            transformations: Dictionary of field transformations
            
        Returns:
            Transformed metadata
        """
        transformed = metadata.copy()
        for old_key, new_key in transformations.items():
            if old_key in transformed:
                transformed[new_key] = transformed.pop(old_key)
        return transformed
    
    def filter_metadata(
        self,
        metadata: Dict[str, Any],
        allowed_fields: List[str]
    ) -> Dict[str, Any]:
        """
        Filter metadata to include only allowed fields.
        
        Args:
            metadata: Metadata to filter
            allowed_fields: List of allowed field names
            
        Returns:
            Filtered metadata
        """
        return {key: value for key, value in metadata.items() if key in allowed_fields}
    
    def merge_metadata(
        self,
        metadata1: Dict[str, Any],
        metadata2: Dict[str, Any],
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Merge two metadata dictionaries.
        
        Args:
            metadata1: First metadata dictionary
            metadata2: Second metadata dictionary
            overwrite: Whether to overwrite existing fields
            
        Returns:
            Merged metadata
        """
        merged = metadata1.copy()
        for key, value in metadata2.items():
            if key not in merged or overwrite:
                merged[key] = value
        return merged
    
    def _is_valid_metadata_value(self, value: Any) -> bool:
        """Check if metadata value is of valid type."""
        valid_types = (str, int, float, bool, list, dict)
        return isinstance(value, valid_types)


class SecurityUtils:
    """
    Security utilities for command operations.
    
    Provides security validation and sanitization utilities
    for command parameters and data.
    
    Features:
    - Parameter sanitization
    - Security validation
    - Rate limiting utilities
    - Access control utilities
    """
    
    def __init__(self) -> None:
        """Initialize security utilities."""
        self.max_query_length = 10000
        self.max_batch_size = 1000
        self.forbidden_patterns = [
            r"<script>",
            r"javascript:",
            r"data:text/html"
        ]
        self.rate_limit_store = {}
    
    def sanitize_input(
        self,
        input_data: str
    ) -> str:
        """
        Sanitize input string.
        
        Args:
            input_data: Input string to sanitize
            
        Returns:
            Sanitized string
        """
        if not isinstance(input_data, str):
            return str(input_data)
        sanitized = input_data
        for pattern in self.forbidden_patterns:
            sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
        sanitized = sanitized.replace("<", "&lt;").replace(">", "&gt;")
        return sanitized
    
    def validate_query_security(
        self,
        query: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate query security.
        
        Args:
            query: Query string to validate
            
        Returns:
            Tuple of (is_safe, list_of_warnings)
        """
        warnings = []
        if not isinstance(query, str):
            warnings.append("Query must be a string")
            return False, warnings
        if len(query) > self.max_query_length:
            warnings.append(f"Query too long (max {self.max_query_length} characters)")
        for pattern in self.forbidden_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                warnings.append(f"Forbidden pattern detected: {pattern}")
        return len(warnings) == 0, warnings
    
    def check_rate_limit(
        self,
        operation: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Check rate limit for operation.
        
        Args:
            operation: Operation type
            user_id: User identifier
            
        Returns:
            True if operation is allowed
        """
        key = f"{operation}:{user_id or 'anonymous'}"
        now = time.time()
        if key not in self.rate_limit_store:
            self.rate_limit_store[key] = []
        self.rate_limit_store[key] = [
            timestamp for timestamp in self.rate_limit_store[key]
            if now - timestamp < 60
        ]
        if len(self.rate_limit_store[key]) >= 10:
            return False
        self.rate_limit_store[key].append(now)
        return True
    
    def validate_access(
        self,
        resource: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Validate access to resource.
        
        Args:
            resource: Resource identifier
            user_id: User identifier
            
        Returns:
            True if access is allowed
        """
        if not user_id:
            return False
        return True


class PerformanceMonitor:
    """
    Performance monitoring utilities.
    
    Provides utilities for monitoring and measuring
    performance of command operations.
    
    Features:
    - Execution time measurement
    - Memory usage monitoring
    - Performance metrics collection
    - Performance reporting
    """
    
    def __init__(self) -> None:
        """Initialize performance monitor."""
        self.metrics = {}
        self.timers = {}
    
    def start_timer(
        self,
        operation: str
    ) -> None:
        """
        Start timer for operation.
        
        Args:
            operation: Operation name
        """
        self.timers[operation] = time.time()
    
    def stop_timer(
        self,
        operation: str
    ) -> float:
        """
        Stop timer for operation.
        
        Args:
            operation: Operation name
            
        Returns:
            Execution time in seconds
        """
        if operation not in self.timers:
            return 0.0
        start_time = self.timers.pop(operation)
        execution_time = time.time() - start_time
        self.record_metric(f"{operation}_time", execution_time)
        return execution_time
    
    def record_metric(
        self,
        metric_name: str,
        value: float
    ) -> None:
        """
        Record performance metric.
        
        Args:
            metric_name: Name of metric
            value: Metric value
        """
        if metric_name not in self.metrics:
            self.metrics[metric_name] = []
        self.metrics[metric_name].append(value)
    
    def get_metrics(
        self,
        operation: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get performance metrics.
        
        Args:
            operation: Operation name (optional)
            
        Returns:
            Performance metrics dictionary
        """
        if operation:
            operation_metrics = {}
            for metric_name, values in self.metrics.items():
                if metric_name.startswith(operation):
                    operation_metrics[metric_name] = {
                        "count": len(values),
                        "min": min(values) if values else 0,
                        "max": max(values) if values else 0,
                        "avg": sum(values) / len(values) if values else 0
                    }
            return operation_metrics
        else:
            all_metrics = {}
            for metric_name, values in self.metrics.items():
                all_metrics[metric_name] = {
                    "count": len(values),
                    "min": min(values) if values else 0,
                    "max": max(values) if values else 0,
                    "avg": sum(values) / len(values) if values else 0
                }
            return all_metrics
    
    def reset_metrics(self) -> None:
        """Reset all performance metrics."""
        self.metrics.clear()
        self.timers.clear()


def create_chunk_query(
    metadata_filter: Optional[Dict[str, Any]] = None,
    search_text: Optional[str] = None,
    embedding: Optional[List[float]] = None
) -> ChunkQuery:
    """
    Create ChunkQuery from parameters.
    
    Args:
        metadata_filter: Metadata filter dictionary
        search_text: Search text
        embedding: Search embedding vector
        
    Returns:
        ChunkQuery object
        
    Raises:
        CommandValidationError: If parameters are invalid
    """
    try:
        query_data = {}
        if metadata_filter is not None:
            query_data["metadata"] = metadata_filter
        if search_text is not None:
            query_data["search_text"] = search_text
        if embedding is not None:
            query_data["embedding"] = embedding
        return ChunkQuery(**query_data)
    except Exception as e:
        raise CommandValidationError(
            message=f"Failed to create ChunkQuery: {str(e)}"
        )


def validate_uuid_list(
    uuids: List[str]
) -> Tuple[List[str], List[str]]:
    """
    Validate list of UUIDs.
    
    Args:
        uuids: List of UUID strings
        
    Returns:
        Tuple of (valid_uuids, invalid_uuids)
    """
    valid_uuids = []
    invalid_uuids = []
    for uuid_str in uuids:
        try:
            uuid.UUID(uuid_str)
            valid_uuids.append(uuid_str)
        except (ValueError, TypeError):
            invalid_uuids.append(uuid_str)
    return valid_uuids, invalid_uuids


def generate_uuid() -> str:
    """
    Generate new UUID.
    
    Returns:
        New UUID string
    """
    return str(uuid.uuid4())


def hash_content(
    content: str,
    algorithm: str = "md5"
) -> str:
    """
    Hash content string.
    
    Args:
        content: Content to hash
        algorithm: Hashing algorithm
        
    Returns:
        Hash string
    """
    if algorithm == "md5":
        return hashlib.md5(content.encode()).hexdigest()
    elif algorithm == "sha1":
        return hashlib.sha1(content.encode()).hexdigest()
    elif algorithm == "sha256":
        return hashlib.sha256(content.encode()).hexdigest()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")


def format_timestamp(
    timestamp: Optional[datetime] = None
) -> str:
    """
    Format timestamp to ISO string.
    
    Args:
        timestamp: Timestamp to format
        
    Returns:
        ISO formatted timestamp string
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    return timestamp.isoformat()


def parse_timestamp(
    timestamp_str: str
) -> datetime:
    """
    Parse timestamp from ISO string.
    
    Args:
        timestamp_str: ISO formatted timestamp string
        
    Returns:
        Datetime object
        
    Raises:
        ValueError: If timestamp string is invalid
    """
    try:
        return datetime.fromisoformat(timestamp_str)
    except ValueError as e:
        raise ValueError(f"Invalid timestamp format: {timestamp_str}") from e


def batch_process(
    items: List[Any],
    batch_size: int,
    processor_func: Callable[[List[Any]], List[Any]]
) -> List[Any]:
    """
    Process items in batches.
    
    Args:
        items: List of items to process
        batch_size: Size of each batch
        processor_func: Function to process each batch
        
    Returns:
        List of processed results
    """
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_results = processor_func(batch)
        results.extend(batch_results)
    return results


def retry_operation(
    operation_func: Callable,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0
) -> Any:
    """
    Retry operation with exponential backoff.
    
    Args:
        operation_func: Function to retry
        max_retries: Maximum number of retries
        delay: Initial delay between retries
        backoff_factor: Backoff factor for delays
        
    Returns:
        Result of operation
        
    Raises:
        Exception: If all retries fail
    """
    last_exception = None
    current_delay = delay
    for attempt in range(max_retries + 1):
        try:
            return operation_func()
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                time.sleep(current_delay)
                current_delay *= backoff_factor
            else:
                break
    raise last_exception 