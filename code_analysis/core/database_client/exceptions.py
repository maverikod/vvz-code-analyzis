"""
Exceptions for database client operations.

Defines custom exceptions for client-side errors including connection errors,
RPC errors, timeout errors, and validation errors.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


class DatabaseClientError(Exception):
    """Base exception for database client errors."""

    pass


class RPCClientError(DatabaseClientError):
    """Exception for RPC client errors."""

    pass


class ConnectionError(DatabaseClientError):
    """Exception for connection errors."""

    pass


class TimeoutError(DatabaseClientError):
    """Exception for timeout errors."""

    pass


class ValidationError(DatabaseClientError):
    """Exception for validation errors."""

    pass


class RPCResponseError(DatabaseClientError):
    """Exception for RPC response errors."""

    def __init__(
        self,
        message: str,
        error_code: int | None = None,
        error_data: dict | None = None,
    ):
        """Initialize RPC response error.

        Args:
            message: Error message
            error_code: Optional error code
            error_data: Optional error data
        """
        super().__init__(message)
        self.error_code = error_code
        self.error_data = error_data
