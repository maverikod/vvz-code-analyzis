"""
Base result classes for RPC database operations.

Provides abstract base classes and concrete implementations for different
types of operation results (success, error, data).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .rpc_protocol import ErrorCode, RPCError


class BaseResult(ABC):
    """Abstract base class for all RPC results.

    All result classes must implement:
    - to_dict() - convert to dictionary for serialization
    - from_dict() - create from dictionary (class method)
    - is_success() - check if result is successful
    - is_error() - check if result is error
    """

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization.

        Returns:
            Dictionary representation of result
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaseResult:
        """Create result from dictionary.

        Args:
            data: Dictionary with result data

        Returns:
            Result instance
        """
        raise NotImplementedError

    @abstractmethod
    def is_success(self) -> bool:
        """Check if result is successful.

        Returns:
            True if result is successful, False otherwise
        """
        raise NotImplementedError

    @abstractmethod
    def is_error(self) -> bool:
        """Check if result is error.

        Returns:
            True if result is error, False otherwise
        """
        raise NotImplementedError


@dataclass
class SuccessResult(BaseResult):
    """Result for successful operations."""

    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {"success": True}
        if self.data is not None:
            result["data"] = self.data
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SuccessResult:
        """Create from dictionary."""
        return cls(data=data.get("data"))

    def is_success(self) -> bool:
        """Check if result is successful."""
        return True

    def is_error(self) -> bool:
        """Check if result is error."""
        return False


@dataclass
class ErrorResult(BaseResult):
    """Result for error operations."""

    error_code: ErrorCode
    description: str
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {
            "success": False,
            "error_code": self.error_code.value,
            "description": self.description,
        }
        if self.details is not None:
            result["details"] = self.details
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ErrorResult:
        """Create from dictionary."""
        error_code = ErrorCode(data.get("error_code", ErrorCode.INTERNAL_ERROR.value))
        description = data.get("description", "Unknown error")
        details = data.get("details")
        return cls(error_code=error_code, description=description, details=details)

    def is_success(self) -> bool:
        """Check if result is successful."""
        return False

    def is_error(self) -> bool:
        """Check if result is error."""
        return True

    def to_rpc_error(self) -> RPCError:
        """Convert to RPCError."""
        return RPCError(
            code=self.error_code,
            message=self.description,
            data=self.details,
        )


@dataclass
class DataResult(BaseResult):
    """Result for operations returning data."""

    data: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {"success": True, "data": self.data}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DataResult:
        """Create from dictionary."""
        result_data = data.get("data", [])
        if not isinstance(result_data, list):
            result_data = []
        return cls(data=result_data)

    def is_success(self) -> bool:
        """Check if result is successful."""
        return True

    def is_error(self) -> bool:
        """Check if result is error."""
        return False
