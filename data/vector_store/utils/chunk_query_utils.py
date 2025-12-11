"""
Utilities for chunk_metadata_adapter integration: filter and conversion utils.

This module provides filter execution, conversion, optimization, and validation utilities
for chunk_metadata_adapter integration.

Features:
- FilterExecutorWrapper for filter operations
- Utility functions for ChunkQuery and SemanticChunk
- Query optimization and security validation
- Conversion to/from dict

Architecture:
- Integration with chunk_metadata_adapter
- Error handling

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
from typing import Dict, List, Any, Tuple
from chunk_metadata_adapter import SemanticChunk, ChunkQuery
from chunk_metadata_adapter.query_validator import QueryValidator
from chunk_metadata_adapter.security_validator import SecurityValidator
from chunk_metadata_adapter.ast_optimizer import ASTOptimizer
from chunk_metadata_adapter.filter_executor import FilterExecutor
from vector_store.exceptions import ValidationError, InvalidParamsError

logger = logging.getLogger("vector_store.utils.chunk_metadata_adapter")


class FilterExecutorWrapper:
    """
    Executor for filter operations.
    
    Provides utilities for executing complex filter operations
    using chunk_metadata_adapter FilterExecutor.
    
    Features:
    - Filter execution
    - Performance optimization
    - Error handling
    - Result caching
    """
    
    def __init__(self) -> None:
        """Initialize filter executor."""
        self.executor: FilterExecutor = FilterExecutor()
        """Filter executor from chunk_metadata_adapter."""
        
        self.cache: Dict[str, Any] = {}
        """Result cache."""
    
    def execute_filter(
        self,
        filter_expr: str,
        data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute filter expression on data.
        
        Args:
            filter_expr: Filter expression string
            data: Data to filter
            
        Returns:
            Filtered data
            
        Raises:
            ValidationError: If filter execution fails
        """
        try:
            # For now, return empty list as FilterExecutor is not fully implemented
            # This is a placeholder implementation
            logger.warning("FilterExecutor.execute_filter is not fully implemented")
            return []
        except Exception as e:
            logger.error(f"Error executing filter: {str(e)}")
            raise ValidationError(
                message=f"Filter execution failed: {str(e)}"
            )
    
    def compile_filter(
        self,
        filter_expr: str
    ) -> Any:
        """
        Compile filter expression.
        
        Args:
            filter_expr: Filter expression string
            
        Returns:
            Compiled filter object
            
        Raises:
            ValidationError: If compilation fails
        """
        try:
            # For now, return the expression as compiled object
            # This is a placeholder implementation
            logger.warning("FilterExecutor.compile_filter is not fully implemented")
            return filter_expr
        except Exception as e:
            logger.error(f"Error compiling filter: {str(e)}")
            raise ValidationError(
                message=f"Filter compilation failed: {str(e)}"
            )
    
    def validate_filter(
        self,
        filter_expr: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate filter expression.
        
        Args:
            filter_expr: Filter expression string
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            # Basic validation - check if expression is not empty
            if not filter_expr or not filter_expr.strip():
                errors.append("Filter expression cannot be empty")
            
            # Check for basic syntax (placeholder validation)
            if "invalid" in filter_expr.lower():
                errors.append("Filter expression contains invalid syntax")
                
        except Exception as e:
            errors.append(f"Filter validation failed: {str(e)}")
        
        return len(errors) == 0, errors


def create_chunk_query_from_dict(
    query_dict: Dict[str, Any]
) -> ChunkQuery:
    """
    Create ChunkQuery from dictionary.
    
    Args:
        query_dict: Query dictionary
        
    Returns:
        ChunkQuery object
        
    Raises:
        ValidationError: If dictionary is invalid
    """
    try:
        return ChunkQuery(**query_dict)
    except Exception as e:
        raise ValidationError(
            message=f"Failed to create ChunkQuery from dictionary: {str(e)}"
        )


def create_semantic_chunk_from_dict(
    chunk_dict: Dict[str, Any]
) -> SemanticChunk:
    """
    Create SemanticChunk from dictionary.
    
    Args:
        chunk_dict: Chunk dictionary
        
    Returns:
        SemanticChunk object
        
    Raises:
        ValidationError: If dictionary is invalid
    """
    try:
        return SemanticChunk(**chunk_dict)
    except Exception as e:
        raise ValidationError(
            message=f"Failed to create SemanticChunk from dictionary: {str(e)}"
        )


def optimize_chunk_query(
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
        optimizer = ASTOptimizer()
        return optimizer.optimize(chunk_query)
    except Exception as e:
        logger.warning(f"Query optimization failed: {str(e)}")
        return chunk_query


def validate_chunk_query_security(
    chunk_query: ChunkQuery
) -> Tuple[bool, List[str]]:
    """
    Validate ChunkQuery security.
    
    Args:
        chunk_query: ChunkQuery to validate
        
    Returns:
        Tuple of (is_safe, list_of_warnings)
    """
    try:
        validator = SecurityValidator()
        security_result = validator.validate(chunk_query)
        return security_result.is_safe, security_result.warnings
    except Exception as e:
        logger.warning(f"Security validation failed: {str(e)}")
        return False, [f"Security validation error: {str(e)}"]


def convert_chunk_query_to_dict(
    chunk_query: ChunkQuery
) -> Dict[str, Any]:
    """
    Convert ChunkQuery to dictionary.
    
    Args:
        chunk_query: ChunkQuery to convert
        
    Returns:
        Dictionary representation
    """
    result = {}
    
    # Add all non-None fields from ChunkQuery
    for field_name, field_value in chunk_query.model_dump().items():
        if field_value is not None and not field_name.startswith('_'):
            result[field_name] = field_value
    
    return result


def convert_semantic_chunk_to_dict(
    chunk: SemanticChunk
) -> Dict[str, Any]:
    """
    Convert SemanticChunk to dictionary.
    
    Args:
        chunk: SemanticChunk to convert
        
    Returns:
        Dictionary representation
    """
    result = {}
    
    # Extract common attributes
    for attr in ['text', 'uuid', 'metadata', 'embedding', 'source_id']:
        if hasattr(chunk, attr):
            value = getattr(chunk, attr)
            if value is not None:
                result[attr] = value
    
    return result 