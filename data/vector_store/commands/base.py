"""
Base command class for vector store commands.

This module provides a simplified base class that directly uses the mcp_proxy_adapter
framework without intermediate adapters. Commands should inherit from this class
to get vector store specific functionality while maintaining framework compatibility.

Features:
- Direct integration with mcp_proxy_adapter framework
- Vector store service integration
- Standardized error handling
- Support for async operations
- Result formatting and validation

Architecture:
- Inherits from mcp_proxy_adapter Command
- Uses VectorStoreService for operations
- Provides standard result formatting
- Uses framework's built-in validation and error handling

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
import time
from abc import abstractmethod
from typing import Dict, List, Any, Type, Optional
from mcp_proxy_adapter.commands.base import Command
from vector_store.exceptions import ValidationError, InvalidParamsError, CommandError
from vector_store.services.vector_store_service import VectorStoreService
from vector_store.utils.performance_monitor import PerformanceMonitor
from mcp_proxy_adapter.commands.result import ErrorResult
import time

logger = logging.getLogger("vector_store.commands.base")

class BaseVectorStoreCommand(Command):
    """
    Base class for all vector store commands.
    
    Provides common functionality for all commands including validation,
    error handling, and integration with vector store services.
    
    This class is designed to work directly with the mcp_proxy_adapter framework
    while providing vector store specific functionality.
    """
    
    def __init__(self, vector_store_service: VectorStoreService) -> None:
        """
        Initialize command with vector store service.
        
        Args:
            vector_store_service: Service for vector store operations
            
        Raises:
            ValueError: If vector_store_service is None
        """
        if not vector_store_service:
            raise ValueError("vector_store_service is required")
        self.vector_store_service: VectorStoreService = vector_store_service
        self.logger: logging.Logger = logger
        self._start_time: float = 0.0
        
        # Initialize performance monitor
        self.performance_monitor = PerformanceMonitor({
            "enable_monitoring": True,
            "enable_logging": True,
            "enable_recommendations": True,
            "slow_query_threshold": 1.0,
            "very_slow_query_threshold": 5.0,
            "critical_query_threshold": 10.0,
            "max_complexity_score": 0.8,
            "max_depth_threshold": 5,
            "max_conditions_threshold": 20
        })
    
    def _start_execution(self) -> None:
        """
        Start command execution timing.
        
        Should be called at the beginning of execute method.
        """
        self._start_time = time.time()
    
    @abstractmethod
    async def execute(self, **params: Any):
        """
        Execute command with parameters.
        
        Args:
            **params: Command parameters
            
        Returns:
            Command result
        """
        pass
    
    def validate_required_params(
        self,
        params: Dict[str, Any],
        required_params: List[str]
    ) -> None:
        """
        Validate that all required parameters are present.
        
        Args:
            params: Parameters to validate
            required_params: List of required parameter names
            
        Raises:
            InvalidParamsError: If required parameters are missing
        """
        missing_params = [p for p in required_params if p not in params or params[p] is None]
        if missing_params:
            raise InvalidParamsError(
                f"Missing required parameters: {', '.join(missing_params)}"
            )
    
    def validate_param_type(
        self,
        param_name: str,
        param_value: Any,
        expected_type: Type,
        allow_none: bool = False
    ) -> None:
        """
        Validate parameter type.
        
        Args:
            param_name: Name of the parameter
            param_value: Value to validate
            expected_type: Expected type
            allow_none: Whether None values are allowed
            
        Raises:
            InvalidParamsError: If parameter type is invalid
        """
        if param_value is None and allow_none:
            return
        if not isinstance(param_value, expected_type):
            raise InvalidParamsError(
                f"Parameter '{param_name}' must be of type {expected_type.__name__}"
            )
    
    def _log_command_execution(
        self,
        command_name: str,
        params: Dict[str, Any],
        result: Any,
        execution_time: float
    ) -> None:
        """
        Log successful command execution.
        
        Args:
            command_name: Name of the executed command
            params: Command parameters
            result: Command result
            execution_time: Execution time in seconds
        """
        self.logger.info(
            f"Command '{command_name}' executed successfully in {execution_time:.3f}s"
        )
        
        # Monitor performance if metadata_filter is present
        if "metadata_filter" in params:
            self._monitor_performance(params["metadata_filter"], execution_time, command_name)
    
    def _monitor_performance(
        self,
        metadata_filter: Dict[str, Any],
        execution_time: float,
        command_name: str
    ) -> None:
        """
        Monitor command performance and analyze complexity.
        
        Args:
            metadata_filter: Metadata filter used in command
            execution_time: Execution time in seconds
            command_name: Name of the executed command
        """
        try:
            # Analyze complexity
            complexity_result = self.performance_monitor.analyze_complexity(metadata_filter)
            
            # Monitor performance
            self.performance_monitor.monitor_performance(
                metadata_filter=metadata_filter,
                execution_time=execution_time,
                complexity_result=complexity_result,
                context={
                    "command_name": command_name,
                    "user_id": getattr(self, 'user_id', None)
                }
            )
        except Exception as e:
            self.logger.warning(f"Performance monitoring failed: {e}")
    
    def _log_command_error(
        self,
        command_name: str,
        params: Dict[str, Any],
        error: Exception,
        execution_time: float
    ) -> None:
        """
        Log command execution error.
        
        Args:
            command_name: Name of the executed command
            params: Command parameters
            error: Exception that occurred
            execution_time: Execution time in seconds
        """
        self.logger.error(
            f"Command '{command_name}' failed after {execution_time:.3f}s: {error}"
        )
    
    def _handle_execution_error(
        self,
        error: Exception,
        command_name: str,
        params: Dict[str, Any]
    ) -> Any:
        """
        Handle command execution errors.
        
        Args:
            error: Exception that occurred
            command_name: Name of the command
            params: Command parameters
            
        Returns:
            ErrorResult with error details
        """
        execution_time = time.time() - self._start_time
        
        if isinstance(error, (ValidationError, InvalidParamsError)):
            self._log_command_error(command_name, params, error, execution_time)
            return ErrorResult(
                code="validation_error",
                message=str(error),
                details={"error_type": type(error).__name__}
            )
        elif isinstance(error, CommandError):
            self._log_command_error(command_name, params, error, execution_time)
            return ErrorResult(
                code="command_error",
                message=str(error),
                details={"error_type": type(error).__name__}
            )
        else:
            self._log_command_error(command_name, params, error, execution_time)
            return ErrorResult(
                code="unexpected_error",
                message="An unexpected error occurred",
                details={"error_type": type(error).__name__, "error": str(error)}
            )

    @classmethod
    def get_error_schema(cls, error_codes: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get JSON schema for error responses.
        
        This base method provides a standard error schema structure that can be
        customized by subclasses with specific error codes.
        
        Args:
            error_codes: Optional list of specific error codes for this command.
                        If None, uses generic error codes.
        
        Returns:
            JSON schema for errors with standard structure
        """
        if error_codes is None:
            error_codes = ["invalid_params", "validation_error", "command_error", "unexpected_error"]
        
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "const": False},
                "error": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "enum": error_codes
                        },
                        "message": {"type": "string"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "details": {"type": "object"},
                                "field": {"type": "string"},
                                "chunk_index": {"type": "integer"},
                                "required_methods": {"type": "array", "items": {"type": "string"}}
                            },
                            "additionalProperties": True
                        }
                    },
                    "required": ["code", "message"]
                }
            },
            "required": ["success", "error"]
        }

    @classmethod
    def get_metadata(cls, error_codes: Optional[List[Dict[str, str]]] = None, examples: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get complete command metadata for help system.
        
        This base method provides a standard metadata structure that can be
        customized by subclasses with specific error codes and examples.
        
        Args:
            error_codes: Optional list of error code descriptions.
                        Each dict should have: {"code": "...", "description": "...", "when": "..."}
            examples: Optional dictionary with success and error examples.
        
        Returns:
            Dictionary with command metadata including name, description, schemas, and examples
        """
        # Default error codes if not provided
        if error_codes is None:
            error_codes = [
                {"code": "invalid_params", "description": "Invalid parameters provided", "when": "When parameters are invalid"},
                {"code": "validation_error", "description": "Validation failed", "when": "When data validation fails"},
                {"code": "command_error", "description": "Command execution failed", "when": "When command operation fails"},
                {"code": "unexpected_error", "description": "Unexpected error occurred", "when": "When an unexpected error occurs"}
            ]
        
        # Default examples if not provided
        if examples is None:
            examples = {
                "success": {
                    "success": True,
                    "data": {"message": "Operation completed successfully"}
                },
                "error": {
                    "success": False,
                    "error": {
                        "code": "validation_error",
                        "message": "Validation failed",
                        "data": {"details": {"field": "example_field"}}
                    }
                }
            }
        
        return {
            "name": getattr(cls, 'name', cls.__name__),
            "description": cls.__doc__ or f"{cls.__name__} command",
            "params": cls.get_schema() if hasattr(cls, 'get_schema') else {},
            "result_schema": cls.get_result_schema() if hasattr(cls, 'get_result_schema') else {},
            "error_schema": cls.get_error_schema(),
            "error_codes": error_codes,
            "examples": examples
        }
