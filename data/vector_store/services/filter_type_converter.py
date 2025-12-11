"""
Filter Type Converter utility.

Converts filter types in metadata filters to ensure compatibility
with Redis operations and type checking based on SemanticChunk schema.

Features:
- Type conversion for filter values
- Support for various data types
- Field-specific conversion rules based on SemanticChunk schema
- Handles operators like $eq, $in, $range, etc.

Architecture:
- Standalone utility class
- Used by RedisMetadataFilterService

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Created: 2025-01-13
Updated: 2025-01-13
"""

from typing import Any, Dict


class FilterTypeConverter:
    """
    Converts filter types to proper Python types based on SemanticChunk schema.
    
    Handles type conversion for ChunkQuery fields to ensure proper comparison
    during metadata filtering operations.
    """

    @staticmethod
    def convert_filter_types(filter_dict: dict) -> dict:
        """
        Converts types in filter according to SemanticChunk field schema.

        Args:
            filter_dict: Raw filter dictionary from ChunkQuery

        Returns:
            Filter dictionary with proper types for comparison

        Raises:
            ValueError: If type conversion fails for any field
        """
        if not filter_dict:
            return {}
        
        converted = {}
        for field_name, value in filter_dict.items():
            if value is None:
                continue
            
            try:
                converted_value = FilterTypeConverter._convert_single_value(value, field_name)
                converted[field_name] = converted_value
            except Exception as e:
                raise ValueError(f"Failed to convert field '{field_name}': {e}")
        
        return converted

    @staticmethod
    def _convert_value(value, field_name: str):
        """
        Convert a single value based on field name.

        Args:
            value: Value to convert
            field_name: Name of the field from SemanticChunk

        Returns:
            Converted value with proper type

        Raises:
            ValueError: If conversion fails
        """
        return FilterTypeConverter._convert_single_value(value, field_name)

    @staticmethod
    def _convert_single_value(value, field_name: str):
        """
        Convert a single value based on field name.

        Args:
            value: Value to convert
            field_name: Name of the field

        Returns:
            Converted value with proper type

        Raises:
            ValueError: If conversion fails
        """
        if value is None:
            return None
        
        # Handle different field types based on SemanticChunk schema
        if field_name in ['uuid', 'source_id', 'task_id', 'subtask_id', 'unit_id', 'block_id']:
            # UUID fields - ensure string format
            return str(value) if value else None
        
        elif field_name in ['language', 'type', 'role', 'status', 'block_type']:
            # Enum fields - keep as string
            return str(value) if value else None
        
        elif field_name in ['created_at', 'updated_at', 'deleted_at']:
            # Timestamp fields - ensure string format
            return str(value) if value else None
        
        elif field_name in ['ordinal', 'start', 'end', 'source_lines_start', 'source_lines_end']:
            # Integer fields
            try:
                return int(value) if value is not None else None
            except (ValueError, TypeError):
                raise ValueError(f"Field '{field_name}' must be an integer")
        
        elif field_name in ['coverage', 'cohesion', 'boundary_prev', 'boundary_next', 'quality_score']:
            # Float fields
            try:
                return float(value) if value is not None else None
            except (ValueError, TypeError):
                raise ValueError(f"Field '{field_name}' must be a float")
        
        elif field_name in ['is_deleted', 'is_public']:
            # Boolean fields
            if isinstance(value, bool):
                return value
            elif isinstance(value, str):
                return value.lower() in ['true', '1', 'yes', 'on']
            elif isinstance(value, (int, float)):
                return bool(value)
            else:
                return False
        
        elif field_name in ['tags', 'links']:
            # List fields - handle both string and list inputs
            if isinstance(value, str):
                # Split comma-separated string
                return [item.strip() for item in value.split(',') if item.strip()]
            elif isinstance(value, (list, tuple)):
                return [str(item) for item in value if item is not None]
            else:
                return [str(value)] if value is not None else []
        
        elif field_name == 'embedding':
            # Vector field - keep as list
            if isinstance(value, (list, tuple)):
                return [float(item) for item in value]
            else:
                raise ValueError(f"Field '{field_name}' must be a list of numbers")
        
        else:
            # Default: string fields
            return str(value) if value is not None else None
