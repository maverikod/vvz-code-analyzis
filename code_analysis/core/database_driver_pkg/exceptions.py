"""
Exceptions for database driver package.

Defines custom exceptions for driver process operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


class DriverError(Exception):
    """Base exception for driver errors."""

    pass


class DriverConnectionError(DriverError):
    """Raised when driver connection fails."""

    pass


class DriverOperationError(DriverError):
    """Raised when driver operation fails."""

    pass


class RequestQueueError(DriverError):
    """Raised when request queue operation fails."""

    pass


class RequestQueueFullError(RequestQueueError):
    """Raised when request queue is full."""

    pass


class RequestTimeoutError(RequestQueueError):
    """Raised when request times out."""

    pass


class RPCServerError(DriverError):
    """Raised when RPC server operation fails."""

    pass


class DriverNotFoundError(DriverError):
    """Raised when driver type is not found."""

    pass


class TransactionError(DriverError):
    """Raised when transaction operation fails."""

    pass
