"""
Utilities for vector store command validation.

This module provides validator classes for command operations,
including ChunkQuery and SemanticChunk validation.

Features:
- Command parameter validation
- Data validation utilities

Architecture:
- Standalone validator classes
- Integration with chunk_metadata_adapter
- Comprehensive error handling

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
import uuid
import datetime
from typing import Dict, List, Any, Tuple
from chunk_metadata_adapter import SemanticChunk, ChunkQuery
from chunk_metadata_adapter.query_validator import QueryValidator
from chunk_metadata_adapter.security_validator import SecurityValidator
from chunk_metadata_adapter.ast_optimizer import ASTOptimizer
from vector_store.exceptions import ValidationError, InvalidParamsError

logger = logging.getLogger("vector_store.utils.command")


class ChunkQueryValidator:
    """
    Validator for ChunkQuery objects.
    
    Provides comprehensive validation for ChunkQuery objects including
    syntax validation, security checks, and complexity analysis.
    
    Features:
    - Query syntax validation
    - Security validation
    - Complexity analysis
    - Performance optimization suggestions
    """
    
    def __init__(self) -> None:
        """Initialize ChunkQuery validator."""
        self.query_validator: QueryValidator = QueryValidator()
        """Query validator from chunk_metadata_adapter."""
        
        self.security_validator: SecurityValidator = SecurityValidator()
        """Security validator from chunk_metadata_adapter."""
        
        self.ast_optimizer: ASTOptimizer = ASTOptimizer()
        """AST optimizer for query optimization."""
    
    def validate_query(
        self,
        chunk_query: ChunkQuery
    ) -> Tuple[bool, List[str]]:
        """
        Validate ChunkQuery object.
        
        Args:
            chunk_query: ChunkQuery to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            # Validate query using chunk_metadata_adapter validator
            validation_result = self.query_validator.validate(chunk_query)
            if not validation_result.is_valid:
                errors.extend(validation_result.errors)
        except Exception as e:
            errors.append(f"Query validation failed: {str(e)}")
        
        return len(errors) == 0, errors
    
    def validate_security(
        self,
        chunk_query: ChunkQuery
    ) -> Tuple[bool, List[str]]:
        """
        Validate ChunkQuery security.
        
        Args:
            chunk_query: ChunkQuery to validate
            
        Returns:
            Tuple of (is_safe, list_of_warnings)
        """
        warnings = []
        
        try:
            # Validate security using chunk_metadata_adapter validator
            security_result = self.security_validator.validate(chunk_query)
            if not security_result.is_safe:
                warnings.extend(security_result.warnings)
        except Exception as e:
            warnings.append(f"Security validation failed: {str(e)}")
        
        return len(warnings) == 0, warnings
    
    def analyze_complexity(
        self,
        chunk_query: ChunkQuery
    ) -> Dict[str, Any]:
        """
        Analyze ChunkQuery complexity.
        
        Args:
            chunk_query: ChunkQuery to analyze
            
        Returns:
            Complexity analysis dictionary
        """
        analysis = {
            "complexity_score": 0,
            "filter_count": 0,
            "nested_levels": 0,
            "estimated_performance": "good"
        }
        
        try:
            # Analyze query complexity
            if hasattr(chunk_query, 'metadata') and chunk_query.metadata:
                analysis["filter_count"] = len(chunk_query.metadata)
                analysis["complexity_score"] = analysis["filter_count"] * 10
            
            # Estimate performance based on complexity
            if analysis["complexity_score"] > 100:
                analysis["estimated_performance"] = "poor"
            elif analysis["complexity_score"] > 50:
                analysis["estimated_performance"] = "fair"
            
        except Exception as e:
            logger.warning(f"Complexity analysis failed: {str(e)}")
        
        return analysis
    
    def optimize_query(
        self,
        chunk_query: ChunkQuery
    ) -> ChunkQuery:
        """
        Optimize ChunkQuery for performance.
        
        Args:
            chunk_query: ChunkQuery to optimize
            
        Returns:
            Optimized ChunkQuery
        """
        try:
            # Use AST optimizer if available
            if hasattr(self.ast_optimizer, 'optimize'):
                return self.ast_optimizer.optimize(chunk_query)
        except Exception as e:
            logger.warning(f"Query optimization failed: {str(e)}")
        
        return chunk_query


class SemanticChunkValidator:
    """
    Validator for SemanticChunk objects.
    
    Provides comprehensive validation for SemanticChunk objects including
    data validation, schema compliance, and content validation.
    
    Features:
    - Data type validation
    - Schema compliance checking
    - Content validation
    - UUID validation
    - Metadata validation
    """
    
    def __init__(self) -> None:
        """Initialize SemanticChunk validator."""
        self.required_fields: List[str] = ["text", "uuid"]
        """Required fields for SemanticChunk."""
        
        self.optional_fields: List[str] = ["metadata", "embedding", "source_id"]
        """Optional fields for SemanticChunk."""
    
    def validate_chunk(
        self,
        chunk: SemanticChunk
    ) -> Tuple[bool, List[str]]:
        """
        Validate SemanticChunk object.
        
        Args:
            chunk: SemanticChunk to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Validate required fields
        for field in self.required_fields:
            if not hasattr(chunk, field) or getattr(chunk, field) is None:
                errors.append(f"Missing required field: {field}")
        
        # Validate text content
        if hasattr(chunk, 'text') and chunk.text:
            text_valid, text_errors = self.validate_text(chunk.text)
            if not text_valid:
                errors.extend(text_errors)
        
        # Validate UUID
        if hasattr(chunk, 'uuid') and chunk.uuid:
            if not self.validate_uuid(chunk.uuid):
                errors.append("Invalid UUID format")
        
        # Validate metadata
        if hasattr(chunk, 'metadata') and chunk.metadata:
            metadata_valid, metadata_errors = self.validate_metadata(chunk.metadata)
            if not metadata_valid:
                errors.extend(metadata_errors)
        
        return len(errors) == 0, errors
    
    def validate_uuid(
        self,
        uuid_str: str
    ) -> bool:
        """
        Validate UUID format.
        
        Args:
            uuid_str: UUID string to validate
            
        Returns:
            True if UUID is valid
        """
        try:
            uuid.UUID(uuid_str)
            return True
        except (ValueError, TypeError):
            return False
    
    def validate_text(
        self,
        text: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate text content.
        
        Args:
            text: Text to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        if not isinstance(text, str):
            errors.append("Text must be a string")
            return False, errors
        
        if not text.strip():
            errors.append("Text cannot be empty")
        
        if len(text) > 1000000:  # 1MB limit
            errors.append("Text too long (max 1MB)")
        
        return len(errors) == 0, errors
    
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
        
        # Check for forbidden keys
        forbidden_keys = ["__class__", "__dict__", "__module__"]
        for key in forbidden_keys:
            if key in metadata:
                errors.append(f"Forbidden metadata key: {key}")
        
        # Validate metadata values
        for key, value in metadata.items():
            if not isinstance(key, str):
                errors.append(f"Metadata key must be string: {key}")
                continue
            
            if not self._is_valid_metadata_value(value):
                errors.append(f"Invalid metadata value type for key '{key}': {type(value)}")
        
        return len(errors) == 0, errors
    
    def _is_valid_metadata_value(self, value: Any) -> bool:
        """Check if metadata value is of valid type."""
        valid_types = (str, int, float, bool, list, dict)
        return isinstance(value, valid_types)


class DataProcessor:
    """
    Processor for data operations.
    
    Provides utilities for processing chunks and converting between formats.
    
    Features:
    - Batch processing
    - Data conversion
    - Validation
    """
    
    def __init__(self) -> None:
        """Initialize data processor."""
        self.validator = SemanticChunkValidator()
        """SemanticChunk validator."""
    
    def process_chunks_batch(
        self,
        chunks_data: List[Dict[str, Any]]
    ) -> List[SemanticChunk]:
        """
        Process batch of chunk data.
        
        Args:
            chunks_data: List of chunk data dictionaries
            
        Returns:
            List of SemanticChunk objects
            
        Raises:
            ValidationError: If batch processing fails
        """
        processed_chunks = []
        
        for chunk_data in chunks_data:
            try:
                chunk = SemanticChunk.validate_and_fill(chunk_data)
                if chunk:
                    processed_chunks.append(chunk)
                else:
                    logger.warning(f"Invalid chunk data: {chunk_data}")
            except Exception as e:
                logger.error(f"Error processing chunk: {str(e)}")
        
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
        """
        chunk = SemanticChunk.validate_and_fill(chunk_data)
        if not chunk:
            raise ValidationError(f"Failed to create SemanticChunk from data: {chunk_data}")
        return chunk
    
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
        return chunk.model_dump()
    
    def validate_batch(
        self,
        chunks_data: List[Dict[str, Any]]
    ) -> Tuple[bool, List[str]]:
        """
        Validate batch of chunk data.
        
        Args:
            chunks_data: List of chunk data dictionaries
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        for i, chunk_data in enumerate(chunks_data):
            try:
                chunk = SemanticChunk.validate_and_fill(chunk_data)
                if not chunk:
                    errors.append(f"Chunk {i}: Invalid chunk data")
            except Exception as e:
                errors.append(f"Chunk {i}: {str(e)}")
        
        return len(errors) == 0, errors


class MetadataProcessor:
    """
    Processor for metadata operations.
    
    Provides utilities for metadata validation, transformation, and filtering.
    
    Features:
    - Metadata validation
    - Transformation
    - Filtering
    - Merging
    """
    
    def __init__(self) -> None:
        """Initialize metadata processor."""
        self.validator = SemanticChunkValidator()
        """SemanticChunk validator."""
    
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
        return self.validator.validate_metadata(metadata)
    
    def transform_metadata(
        self,
        metadata: Dict[str, Any],
        transformations: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Transform metadata using provided transformations.
        
        Args:
            metadata: Original metadata
            transformations: Transformation rules
            
        Returns:
            Transformed metadata
        """
        transformed = metadata.copy()
        
        for key, transformation in transformations.items():
            if key in transformed:
                if callable(transformation):
                    transformed[key] = transformation(transformed[key])
                else:
                    transformed[key] = transformation
        
        return transformed
    
    def filter_metadata(
        self,
        metadata: Dict[str, Any],
        allowed_keys: List[str]
    ) -> Dict[str, Any]:
        """
        Filter metadata to include only allowed keys.
        
        Args:
            metadata: Original metadata
            allowed_keys: List of allowed keys
            
        Returns:
            Filtered metadata
        """
        return {key: value for key, value in metadata.items() if key in allowed_keys}
    
    def merge_metadata(
        self,
        metadata1: Dict[str, Any],
        metadata2: Dict[str, Any],
        overwrite: bool = True
    ) -> Dict[str, Any]:
        """
        Merge two metadata dictionaries.
        
        Args:
            metadata1: First metadata dictionary
            metadata2: Second metadata dictionary
            overwrite: Whether to overwrite existing keys
            
        Returns:
            Merged metadata
        """
        merged = metadata1.copy()
        
        for key, value in metadata2.items():
            if key not in merged or overwrite:
                merged[key] = value
        
        return merged


class SecurityUtils:
    """
    Security utilities for input validation and sanitization.
    
    Provides utilities for security validation and input sanitization.
    
    Features:
    - Input sanitization
    - Security validation
    - Rate limiting
    - Access control
    """
    
    def __init__(self) -> None:
        """Initialize security utils."""
        self.rate_limit_cache = {}
        """Rate limit cache."""
    
    def sanitize_input(
        self,
        input_str: str
    ) -> str:
        """
        Sanitize input string.
        
        Args:
            input_str: Input string to sanitize
            
        Returns:
            Sanitized string
        """
        if not isinstance(input_str, str):
            return str(input_str)
        
        # Basic sanitization - remove potentially dangerous characters
        sanitized = input_str.replace("<script>", "").replace("</script>", "")
        sanitized = sanitized.replace("javascript:", "")
        
        return sanitized.strip()
    
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
        
        # Check for potentially dangerous patterns
        dangerous_patterns = [
            "script", "javascript", "eval(", "exec(", "import os"
        ]
        
        query_lower = query.lower()
        for pattern in dangerous_patterns:
            if pattern in query_lower:
                warnings.append(f"Potentially dangerous pattern detected: {pattern}")
        
        return len(warnings) == 0, warnings
    
    def check_rate_limit(
        self,
        user_id: str,
        operation: str,
        limit: int = 100
    ) -> bool:
        """
        Check rate limit for user operation.
        
        Args:
            user_id: User identifier
            operation: Operation type
            limit: Rate limit
            
        Returns:
            True if within rate limit
        """
        import time
        
        key = f"{user_id}:{operation}"
        current_time = time.time()
        
        if key not in self.rate_limit_cache:
            self.rate_limit_cache[key] = []
        
        # Remove old entries (older than 1 minute)
        self.rate_limit_cache[key] = [
            t for t in self.rate_limit_cache[key] 
            if current_time - t < 60
        ]
        
        # Check if limit exceeded
        if len(self.rate_limit_cache[key]) >= limit:
            return False
        
        # Add current request
        self.rate_limit_cache[key].append(current_time)
        return True
    
    def validate_access(
        self,
        user_id: str,
        resource: str
    ) -> bool:
        """
        Validate user access to resource.
        
        Args:
            user_id: User identifier
            resource: Resource identifier
            
        Returns:
            True if access allowed
        """
        # Placeholder implementation - always allow access
        return True


class PerformanceMonitor:
    """
    Performance monitoring utilities.
    
    Provides utilities for monitoring and measuring performance.
    
    Features:
    - Timer utilities
    - Metrics collection
    - Performance analysis
    """
    
    def __init__(self) -> None:
        """Initialize performance monitor."""
        self.metrics = {}
        """Metrics storage."""
        self.timers = {}
        """Active timers."""
    
    def start_timer(
        self,
        operation: str
    ) -> None:
        """
        Start timer for operation.
        
        Args:
            operation: Operation name
        """
        import time
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
            Elapsed time in seconds
        """
        import time
        
        if operation not in self.timers:
            return 0.0
        
        elapsed = time.time() - self.timers[operation]
        del self.timers[operation]
        
        self.record_metric(operation, "duration", elapsed)
        return elapsed
    
    def record_metric(
        self,
        operation: str,
        metric_name: str,
        value: float
    ) -> None:
        """
        Record metric for operation.
        
        Args:
            operation: Operation name
            metric_name: Metric name
            value: Metric value
        """
        if operation not in self.metrics:
            self.metrics[operation] = {}
        
        if metric_name not in self.metrics[operation]:
            self.metrics[operation][metric_name] = []
        
        self.metrics[operation][metric_name].append(value)
    
    def get_metrics(
        self,
        operation: str = None
    ) -> Dict[str, Any]:
        """
        Get metrics for operation or all operations.
        
        Args:
            operation: Operation name (None for all)
            
        Returns:
            Metrics dictionary
        """
        if operation:
            return self.metrics.get(operation, {})
        return self.metrics.copy()
    
    def reset_metrics(
        self,
        operation: str = None
    ) -> None:
        """
        Reset metrics for operation or all operations.
        
        Args:
            operation: Operation name (None for all)
        """
        if operation:
            if operation in self.metrics:
                del self.metrics[operation]
        else:
            self.metrics.clear()


# Utility functions
def create_chunk_query(
    metadata: Dict[str, Any] = None,
    search_text: str = None,
    embedding: List[float] = None,
    limit: int = 10,
    offset: int = 0
) -> ChunkQuery:
    """
    Create ChunkQuery with common parameters.
    
    Args:
        metadata: Metadata filter
        search_text: Search text
        embedding: Embedding vector
        limit: Result limit
        offset: Result offset
        
    Returns:
        ChunkQuery object
    """
    query_data = {}
    
    if metadata:
        query_data["metadata"] = metadata
    if search_text:
        query_data["search_text"] = search_text
    if embedding:
        query_data["embedding"] = embedding
    if limit:
        query_data["limit"] = limit
    if offset:
        query_data["offset"] = offset
    
    return ChunkQuery(**query_data)


def validate_uuid_list(
    uuid_list: List[str]
) -> Tuple[bool, List[str]]:
    """
    Validate list of UUIDs.
    
    Args:
        uuid_list: List of UUID strings
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    for i, uuid_str in enumerate(uuid_list):
        try:
            uuid.UUID(uuid_str)
        except (ValueError, TypeError):
            errors.append(f"Invalid UUID at index {i}: {uuid_str}")
    
    return len(errors) == 0, errors


def generate_uuid() -> str:
    """
    Generate new UUID.
    
    Returns:
        UUID string
    """
    return str(uuid.uuid4())


def hash_content(
    content: str,
    algorithm: str = "sha256"
) -> str:
    """
    Hash content using specified algorithm.
    
    Args:
        content: Content to hash
        algorithm: Hash algorithm
        
    Returns:
        Hash string
    """
    import hashlib
    
    if algorithm == "sha256":
        return hashlib.sha256(content.encode()).hexdigest()
    elif algorithm == "md5":
        return hashlib.md5(content.encode()).hexdigest()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")


def format_timestamp(
    timestamp: str = None
) -> str:
    """
    Format timestamp to ISO format.
    
    Args:
        timestamp: Timestamp string (None for current time)
        
    Returns:
        Formatted timestamp
    """
    import datetime
    
    if timestamp is None:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    try:
        # Try to parse and reformat
        dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt.isoformat()
    except ValueError:
        return timestamp


def parse_timestamp(
    timestamp: str
) -> datetime.datetime:
    """
    Parse timestamp string.
    
    Args:
        timestamp: Timestamp string
        
    Returns:
        Datetime object
    """
    import datetime
    
    try:
        return datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError(f"Invalid timestamp format: {timestamp}")


def batch_process(
    items: List[Any],
    batch_size: int = 100,
    processor: callable = None
) -> List[Any]:
    """
    Process items in batches.
    
    Args:
        items: List of items to process
        batch_size: Batch size
        processor: Processing function
        
    Returns:
        Processed items
    """
    if processor is None:
        return items
    
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_results = processor(batch)
        results.extend(batch_results)
    
    return results


def retry_operation(
    operation: callable,
    max_retries: int = 3,
    delay: float = 1.0
) -> Any:
    """
    Retry operation with exponential backoff.
    
    Args:
        operation: Operation to retry
        max_retries: Maximum number of retries
        delay: Initial delay in seconds
        
    Returns:
        Operation result
    """
    import time
    
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return operation()
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                time.sleep(delay * (2 ** attempt))
    
    raise last_exception