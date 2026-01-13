"""
Database client package.

Provides client library for communicating with database driver process via RPC.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .client import DatabaseClient
from .exceptions import (
    ConnectionError,
    DatabaseClientError,
    RPCClientError,
    RPCResponseError,
    TimeoutError,
    ValidationError,
)
from .result import Result
from .rpc_client import RPCClient

__all__ = [
    "DatabaseClient",
    "RPCClient",
    "Result",
    "DatabaseClientError",
    "RPCClientError",
    "ConnectionError",
    "TimeoutError",
    "ValidationError",
    "RPCResponseError",
]
