"""
Base result class for vector store commands.

This module provides a simplified base result class that directly uses the mcp_proxy_adapter
framework without intermediate adapters. Result classes should inherit from this class
to get vector store specific functionality while maintaining framework compatibility.

Features:
- Direct integration with mcp_proxy_adapter framework
- Standard result formatting
- Metadata support
- Performance metrics
- Validation capabilities

Architecture:
- Inherits from mcp_proxy_adapter.commands.result.SuccessResult
- Used by all command result classes
- Provides standard formatting and validation

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

from typing import Dict, Any, Optional
from mcp_proxy_adapter.commands.result import SuccessResult

class BaseCommandResult(SuccessResult):
    """
    Base class for all command results.
    
    Provides standard formatting and validation for command results
    with support for metadata and performance information.
    
    This class is designed to work directly with the mcp_proxy_adapter framework
    while providing vector store specific functionality.
    """
    
    def __init__(
        self,
        data: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize command result.
        
        Args:
            data: Result data
            message: Result message
            metadata: Additional metadata
        """
        # Prepare data with metadata
        result_data = data or {}
        if metadata:
            result_data["metadata"] = metadata
            
        super().__init__(data=result_data, message=message)
        self.metadata: Optional[Dict[str, Any]] = metadata
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert result to dictionary for serialization.
        
        Returns:
            Dictionary with result data
        """
        result = super().to_dict()
        
        # Add metadata at top level if present
        if self.metadata:
            result["metadata"] = self.metadata
            
        return result
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {"type": "object", "additionalProperties": True},
                "message": {"type": "string"},
                "metadata": {"type": "object", "additionalProperties": True}
            },
            "required": ["success"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseCommandResult':
        """
        Create result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            Result instance
        """
        # Extract metadata from top level or data level
        metadata = data.get("metadata")
        if not metadata and "data" in data:
            metadata = data["data"].get("metadata")
            
        return cls(
            data=data.get("data"),
            message=data.get("message"),
            metadata=metadata
        ) 