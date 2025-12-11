"""
Implementation of utility classes for index operations.

This file implements the utility methods for index operations
including value normalization, hash generation, and validation.

Features:
- Value normalization for consistent indexing
- Array hash generation for exact matching
- Range bucket calculation for numeric fields
- Data validation utilities
- Field extraction for indexing

Architecture:
- Stateless utility methods
- Consistent with index storage format
- Supports all data types used in indexing

Author: Vasiliy Zdanovskiy <vasilyvz@gmail.com>
Created: 2024-01-15
Updated: 2024-01-15
"""

import hashlib
import json
from typing import Dict, List, Any, Optional, Union, Set
from datetime import datetime
from enum import Enum

from .base import (
    IndexUtils as BaseIndexUtils,
    IndexType
)
from vector_store.exceptions import IndexValidationError as ValidationError


class IndexUtils(BaseIndexUtils):
    """
    Implementation of utility class for index operations.
    
    Provides static methods for common index operations
    like value normalization, hash generation, and validation.
    
    Features:
    - Value normalization for consistent indexing
    - Array hash generation for exact matching
    - Range bucket calculation for numeric fields
    - Data validation utilities
    - Field extraction for indexing
    
    Architecture:
    - Stateless utility methods
    - Consistent with index storage format
    - Supports all data types used in indexing
    """
    
    # Fields that should not be indexed
    EXCLUDED_FIELDS: Set[str] = {
        'embedding', 'text', 'body', 'created_at', 'updated_at'
    }
    """Fields that should not be indexed."""
    
    # Supported data types for indexing
    SUPPORTED_TYPES: Set[type] = {
        str, int, float, bool, list, tuple, dict
    }
    """Supported data types for indexing."""
    
    # Numeric types for range indexing
    NUMERIC_TYPES: Set[type] = {int, float}
    """Numeric types that support range indexing."""
    
    # String types for prefix indexing
    STRING_TYPES: Set[type] = {str}
    """String types that support prefix indexing."""
    
    # Array types for array indexing
    ARRAY_TYPES: Set[type] = {list, tuple}
    """Array types that support array indexing."""
    
    @staticmethod
    def generate_array_hash(array: List[Any]) -> str:
        """
        Generate hash for exact array matching.
        
        Creates a consistent hash for arrays regardless of element order
        by sorting elements before hashing.
        
        Args:
            array: Array to generate hash for
            
        Returns:
            MD5 hash of sorted array elements
            
        Raises:
            ValidationError: If array is not a valid list or tuple
            
        Performance:
            Time complexity: O(n log n) for sorting
            Space complexity: O(n) for temporary storage
            
        Example:
            >>> IndexUtils.generate_array_hash(["a", "b", "c"])
            'hash_value_1'
            >>> IndexUtils.generate_array_hash(["c", "b", "a"])
            'hash_value_1'  # Same hash for different order
        """
        if not isinstance(array, (list, tuple)):
            raise ValidationError(f"Expected list or tuple, got {type(array)}")
        
        if not array:
            return hashlib.md5(b"[]").hexdigest()
        
        # Convert all elements to strings and sort
        try:
            sorted_elements = sorted([str(item).lower() for item in array])
            array_string = ','.join(sorted_elements)
            return hashlib.md5(array_string.encode('utf-8')).hexdigest()
        except Exception as e:
            raise ValidationError(f"Failed to generate array hash: {e}")
    
    @staticmethod
    def normalize_value(value: Any) -> str:
        """
        Normalize value for indexing.
        
        Converts values to consistent string representation
        for reliable indexing and searching.
        
        Args:
            value: Value to normalize
            
        Returns:
            Normalized string representation
            
        Raises:
            ValidationError: If value cannot be normalized
            
        Performance:
            Time complexity: O(1) for most types
            Space complexity: O(1) for most types
            
        Example:
            >>> IndexUtils.normalize_value("Hello World")
            'hello world'
            >>> IndexUtils.normalize_value(123)
            '123'
            >>> IndexUtils.normalize_value(["a", "b"])
            'hash_value_for_array'
        """
        if value is None:
            return "null"
        
        try:
            if isinstance(value, (list, tuple)):
                return IndexUtils.generate_array_hash(value)
            elif isinstance(value, dict):
                # Sort dictionary items for consistent hashing
                sorted_items = sorted(value.items())
                dict_string = json.dumps(sorted_items, sort_keys=True)
                return hashlib.md5(dict_string.encode('utf-8')).hexdigest()
            elif isinstance(value, datetime):
                return value.isoformat()
            elif isinstance(value, Enum):
                return str(value.value).lower()
            elif isinstance(value, bool):
                return str(value).lower()
            else:
                return str(value).lower()
        except Exception as e:
            raise ValidationError(f"Failed to normalize value {value}: {e}")
    
    @staticmethod
    def get_range_bucket(value: Union[int, float], bucket_size: int = 100) -> str:
        """
        Get range bucket for numeric values.
        
        Divides numeric values into buckets for efficient range queries.
        
        Args:
            value: Numeric value to bucket
            bucket_size: Size of each bucket
            
        Returns:
            String representation of the bucket range
            
        Raises:
            ValidationError: If value is not numeric or bucket_size is invalid
            
        Performance:
            Time complexity: O(1)
            Space complexity: O(1)
            
        Example:
            >>> IndexUtils.get_range_bucket(150, 100)
            '100-199'
            >>> IndexUtils.get_range_bucket(250, 100)
            '200-299'
        """
        if not isinstance(value, (int, float)):
            raise ValidationError(f"Expected numeric value, got {type(value)}")
        
        if bucket_size <= 0:
            raise ValidationError(f"Bucket size must be positive, got {bucket_size}")
        
        try:
            bucket_start = int(value // bucket_size) * bucket_size
            bucket_end = bucket_start + bucket_size - 1
            return f"{bucket_start}-{bucket_end}"
        except Exception as e:
            raise ValidationError(f"Failed to calculate range bucket: {e}")
    
    @staticmethod
    def validate_chunk_data(chunk_data: Dict[str, Any]) -> bool:
        """
        Validate chunk data for indexing.
        
        Checks if chunk data is valid for indexing operations.
        
        Args:
            chunk_data: Chunk data to validate
            
        Returns:
            True if data is valid, False otherwise
            
        Raises:
            ValidationError: If data validation fails
            
        Performance:
            Time complexity: O(n) where n is number of fields
            Space complexity: O(1)
        """
        if not isinstance(chunk_data, dict):
            raise ValidationError(f"Expected dictionary, got {type(chunk_data)}")
        
        if not chunk_data:
            raise ValidationError("Chunk data cannot be empty")
        
        # Check for required fields
        if 'uuid' not in chunk_data:
            raise ValidationError("Chunk data must contain 'uuid' field")
        
        # Validate field types
        for field_name, field_value in chunk_data.items():
            if field_value is not None:
                if not IndexUtils._is_supported_type(field_value):
                    raise ValidationError(
                        f"Unsupported type {type(field_value)} for field {field_name}"
                    )
        
        return True
    
    @staticmethod
    def extract_indexable_fields(chunk_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract fields that should be indexed.
        
        Filters out fields that should not be indexed and
        returns only the indexable fields.
        
        Args:
            chunk_data: Chunk data to extract fields from
            
        Returns:
            Dictionary of indexable fields
            
        Performance:
            Time complexity: O(n) where n is number of fields
            Space complexity: O(n) for filtered fields
            
        Example:
            >>> data = {"uuid": "123", "source_id": "456", "embedding": [1,2,3]}
            >>> IndexUtils.extract_indexable_fields(data)
            {"source_id": "456"}
        """
        if not isinstance(chunk_data, dict):
            return {}
        
        indexable_fields = {}
        
        for field_name, field_value in chunk_data.items():
            # Skip excluded fields
            if field_name in IndexUtils.EXCLUDED_FIELDS:
                continue
            
            # Skip None values
            if field_value is None:
                continue
            
            # Skip unsupported types
            if not IndexUtils._is_supported_type(field_value):
                continue
            
            indexable_fields[field_name] = field_value
        
        return indexable_fields
    
    @staticmethod
    def _is_supported_type(value: Any) -> bool:
        """
        Check if value type is supported for indexing.
        
        Args:
            value: Value to check
            
        Returns:
            True if type is supported, False otherwise
        """
        value_type = type(value)
        
        # Direct type check
        if value_type in IndexUtils.SUPPORTED_TYPES:
            return True
        
        # Check for Enum types
        if isinstance(value, Enum):
            return True
        
        # Check for datetime types
        if isinstance(value, datetime):
            return True
        
        return False
    
    @staticmethod
    def get_field_index_type(field_name: str, field_value: Any) -> IndexType:
        """
        Determine the appropriate index type for a field.
        
        Args:
            field_name: Name of the field
            field_value: Value of the field
            
        Returns:
            Appropriate IndexType for the field
            
        Performance:
            Time complexity: O(1)
            Space complexity: O(1)
        """
        if field_value is None:
            return IndexType.SCALAR
        
        value_type = type(field_value)
        
        # Array types
        if value_type in IndexUtils.ARRAY_TYPES:
            return IndexType.ARRAY
        
        # Numeric types for range indexing
        if value_type in IndexUtils.NUMERIC_TYPES:
            return IndexType.RANGE
        
        # String types for prefix indexing
        if value_type in IndexUtils.STRING_TYPES:
            return IndexType.PREFIX
        
        # Default to scalar
        return IndexType.SCALAR
    
    @staticmethod
    def validate_search_criteria(criteria: Dict[str, Any]) -> bool:
        """
        Validate search criteria for index operations.
        
        Args:
            criteria: Search criteria to validate
            
        Returns:
            True if criteria is valid, False otherwise
            
        Raises:
            ValidationError: If criteria validation fails
        """
        if not isinstance(criteria, dict):
            raise ValidationError(f"Expected dictionary, got {type(criteria)}")
        
        if not criteria:
            raise ValidationError("Search criteria cannot be empty")
        
        for field_name, condition in criteria.items():
            if not isinstance(field_name, str):
                raise ValidationError(f"Field name must be string, got {type(field_name)}")
            
            if field_name.strip() == "":
                raise ValidationError("Field name cannot be empty")
            
            # Validate condition structure
            if isinstance(condition, dict):
                # Complex condition with operators
                for operator, value in condition.items():
                    if not isinstance(operator, str):
                        raise ValidationError(f"Operator must be string, got {type(operator)}")
                    
                    if operator.startswith('$'):
                        # MongoDB-style operators
                        if operator not in ['$in', '$eq', '$ne', '$gt', '$gte', '$lt', '$lte']:
                            raise ValidationError(f"Unsupported operator: {operator}")
                    else:
                        raise ValidationError(f"Invalid operator format: {operator}")
        
        return True
    
    @staticmethod
    def extract_search_operators(condition: Any) -> Dict[str, Any]:
        """
        Extract search operators from a condition.
        
        Args:
            condition: Search condition to extract operators from
            
        Returns:
            Dictionary of operators and their values
        """
        operators = {}
        
        if isinstance(condition, dict):
            for key, value in condition.items():
                if key.startswith('$'):
                    operators[key] = value
        else:
            # Simple equality condition
            operators['$eq'] = condition
        
        return operators
    
    @staticmethod
    def is_range_operator(operator: str) -> bool:
        """
        Check if operator is a range operator.
        
        Args:
            operator: Operator to check
            
        Returns:
            True if operator is a range operator, False otherwise
        """
        range_operators = {'$gt', '$gte', '$lt', '$lte'}
        return operator in range_operators
    
    @staticmethod
    def is_array_operator(operator: str) -> bool:
        """
        Check if operator is an array operator.
        
        Args:
            operator: Operator to check
            
        Returns:
            True if operator is an array operator, False otherwise
        """
        array_operators = {'$in', '$all'}
        return operator in array_operators
    
    @staticmethod
    def get_index_key_prefix(field_name: str, index_type: IndexType) -> str:
        """
        Get the key prefix for an index type.
        
        Args:
            field_name: Name of the field
            index_type: Type of index
            
        Returns:
            Key prefix for the index type
        """
        if index_type == IndexType.SCALAR:
            return f"field_index:{field_name}"
        elif index_type == IndexType.ARRAY:
            return f"array_element_index:{field_name}"
        elif index_type == IndexType.RANGE:
            return f"range_index:{field_name}"
        elif index_type == IndexType.PREFIX:
            return f"prefix_index:{field_name}"
        else:
            return f"index:{field_name}"
    
    @staticmethod
    def calculate_index_size(field_value: Any) -> int:
        """
        Calculate approximate size of index entry.
        
        Args:
            field_value: Value to calculate size for
            
        Returns:
            Approximate size in bytes
        """
        try:
            normalized = IndexUtils.normalize_value(field_value)
            return len(normalized.encode('utf-8'))
        except Exception:
            return 0
    
    @staticmethod
    def estimate_memory_usage(indexed_fields: Dict[str, Any]) -> int:
        """
        Estimate memory usage for indexed fields.
        
        Args:
            indexed_fields: Dictionary of indexed fields
            
        Returns:
            Estimated memory usage in bytes
        """
        total_size = 0
        
        for field_name, field_value in indexed_fields.items():
            # Base size for field name
            total_size += len(field_name.encode('utf-8'))
            
            # Size for normalized value
            total_size += IndexUtils.calculate_index_size(field_value)
            
            # Overhead for Redis structures (approximate)
            total_size += 100
        
        return total_size
