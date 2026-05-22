"""
Exceptions for database driver package.

Defines custom exceptions for driver process operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Base driver exception hierarchy
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Structured database error information (transient / retry contract)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatabaseErrorInfo:
    """Structured classification of a database error."""

    sqlstate: str | None
    error_kind: str
    retryable: bool
    message: str
    commit_outcome_unknown: bool = False


class TransientDatabaseError(DriverOperationError):
    """Retryable (or structurally described) database operation failure."""

    def __init__(
        self,
        message: str,
        *,
        sqlstate: str | None,
        error_kind: str,
        retryable: bool = True,
        original_error: BaseException | None = None,
        attempts: int | None = None,
        commit_outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate
        self.error_kind = error_kind
        self.retryable = retryable
        self.original_error = original_error
        self.attempts = attempts
        self.commit_outcome_unknown = commit_outcome_unknown

    def to_details(
        self,
        operation_name: str | None = None,
        attempts: int | None = None,
    ) -> dict[str, Any]:
        return {
            "sqlstate": self.sqlstate,
            "error_kind": self.error_kind,
            "retryable": self.retryable,
            "attempts": attempts if attempts is not None else self.attempts,
            "operation_name": operation_name,
            "commit_outcome_unknown": self.commit_outcome_unknown,
        }


def database_error_details(
    exc: BaseException,
    operation_name: str | None = None,
    attempts: int | None = None,
) -> dict[str, Any]:
    """
    Return stable structured error details for logging / RPC.
    For PostgreSQL errors, reuses the shared classifier (lazy import).
    """
    if isinstance(exc, TransientDatabaseError):
        return exc.to_details(operation_name=operation_name, attempts=attempts)

    from code_analysis.core.database_driver_pkg.drivers.postgres_run import (  # noqa: WPS433
        classify_postgres_error,
    )

    candidates: list[BaseException] = [exc]
    cause: BaseException | None = getattr(exc, "__cause__", None)
    if cause is not None:
        candidates.append(cause)
    ctx = getattr(exc, "__context__", None)
    if ctx is not None and ctx not in candidates:
        candidates.append(ctx)

    for cand in candidates:
        info = classify_postgres_error(cand)
        if info.sqlstate is not None or info.error_kind != "non_postgres":
            return {
                "sqlstate": info.sqlstate,
                "error_kind": info.error_kind,
                "retryable": bool(info.retryable and not info.commit_outcome_unknown),
                "message": info.message,
                "commit_outcome_unknown": info.commit_outcome_unknown,
                "operation_name": operation_name,
                "attempts": attempts,
            }
    return {
        "sqlstate": None,
        "error_kind": "driver_error",
        "retryable": False,
        "message": str(exc),
        "commit_outcome_unknown": False,
        "operation_name": operation_name,
        "attempts": attempts,
    }
