"""
Result object class for client-side database operations.

Provides a unified Result type for AST/CST operations and other client operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Generic, Optional, TypeVar

from .protocol import ErrorCode

T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    """Result object for client-side operations.

    Provides a unified way to represent operation results with success/error states
    and optional data. Used for AST/CST operations and other client operations.

    Attributes:
        success: Whether the operation was successful
        data: Optional data returned by the operation
        error_code: Optional error code if operation failed
        error_description: Optional error description if operation failed
        error_details: Optional additional error details

    Examples:
        >>> result = Result.create_success(data={"node_id": "123"})
        >>> if result.is_success():
        ...     print(result.data)
        >>> result = Result.error(
        ...     error_code=ErrorCode.NOT_FOUND,
        ...     description="Node not found"
        ... )
    """

    success: bool
    data: Optional[T] = None
    error_code: Optional[ErrorCode] = None
    error_description: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

    @classmethod
    def create_success(cls, data: Optional[T] = None) -> Result[T]:
        """Create a successful result.

        Args:
            data: Optional data to return

        Returns:
            Result instance with success=True
        """
        return cls(success=True, data=data)

    @classmethod
    def error(
        cls,
        error_code: ErrorCode,
        description: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Result[T]:
        """Create an error result.

        Args:
            error_code: Error code
            description: Error description
            details: Optional additional error details

        Returns:
            Result instance with success=False
        """
        return cls(
            success=False,
            error_code=error_code,
            error_description=description,
            error_details=details,
        )

    def is_success(self) -> bool:
        """Check if result is successful.

        Returns:
            True if result is successful, False otherwise
        """
        return self.success

    def is_error(self) -> bool:
        """Check if result is error.

        Returns:
            True if result is error, False otherwise
        """
        return not self.success

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization.

        Returns:
            Dictionary representation of result
        """
        result: Dict[str, Any] = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error_code is not None:
            result["error_code"] = self.error_code.value
        if self.error_description is not None:
            result["error_description"] = self.error_description
        if self.error_details is not None:
            result["error_details"] = self.error_details
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Result[Any]:
        """Create result from dictionary.

        Args:
            data: Dictionary with result data

        Returns:
            Result instance
        """
        success = data.get("success", False)
        result_data = data.get("data")
        error_code_value = data.get("error_code")
        error_code = (
            ErrorCode(error_code_value) if error_code_value is not None else None
        )
        error_description = data.get("error_description")
        error_details = data.get("error_details")
        return cls(
            success=success,
            data=result_data,
            error_code=error_code,
            error_description=error_description,
            error_details=error_details,
        )
