"""
RPC protocol definitions for database driver communication.

Defines JSON-RPC 2.0 based protocol with error codes and message formats.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, Optional


class ErrorCode(IntEnum):
    """RPC error codes."""

    SUCCESS = 0
    INVALID_REQUEST = 1
    DATABASE_ERROR = 2
    NOT_FOUND = 3
    VALIDATION_ERROR = 4
    PERMISSION_DENIED = 5
    TIMEOUT = 6
    INTERNAL_ERROR = 7
    TRANSACTION_ERROR = 8
    SCHEMA_ERROR = 9
    CONNECTION_ERROR = 10


@dataclass
class RPCError:
    """RPC error representation."""

    code: ErrorCode
    message: str
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for serialization."""
        result: Dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.data is not None:
            result["data"] = self.data
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RPCError:
        """Create error from dictionary."""
        code = ErrorCode(data.get("code", ErrorCode.INTERNAL_ERROR.value))
        message = data.get("message", "Unknown error")
        error_data = data.get("data")
        return cls(code=code, message=message, data=error_data)


@dataclass
class RPCRequest:
    """RPC request message."""

    method: str
    params: Dict[str, Any]
    request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert request to dictionary for serialization."""
        result: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": self.method,
            "params": self.params,
        }
        if self.request_id is not None:
            result["id"] = self.request_id
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RPCRequest:
        """Create request from dictionary."""
        method = data.get("method", "")
        params = data.get("params", {})
        request_id = data.get("id")
        return cls(method=method, params=params, request_id=request_id)


@dataclass
class RPCResponse:
    """RPC response message."""

    result: Optional[Dict[str, Any]] = None
    error: Optional[RPCError] = None
    request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary for serialization."""
        result: Dict[str, Any] = {"jsonrpc": "2.0"}
        if self.error is not None:
            result["error"] = self.error.to_dict()
        elif self.result is not None:
            result["result"] = self.result
        else:
            result["result"] = None
        if self.request_id is not None:
            result["id"] = self.request_id
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RPCResponse:
        """Create response from dictionary."""
        request_id = data.get("id")
        error_data = data.get("error")
        error = RPCError.from_dict(error_data) if error_data else None
        result_data = data.get("result")
        return cls(result=result_data, error=error, request_id=request_id)

    def is_success(self) -> bool:
        """Check if response is successful."""
        return self.error is None

    def is_error(self) -> bool:
        """Check if response is error."""
        return self.error is not None
