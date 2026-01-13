"""
Database driver package for RPC-based database operations.

This package provides RPC infrastructure for database driver processes,
including request/result classes, protocol definitions, serialization utilities,
driver implementations, RPC server, and request queue.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .driver_factory import create_driver
from .drivers.base import BaseDatabaseDriver
from .drivers.sqlite import SQLiteDriver
from .exceptions import (
    DriverConnectionError,
    DriverError,
    DriverNotFoundError,
    DriverOperationError,
    RequestQueueError,
    RequestQueueFullError,
    RequestTimeoutError,
    RPCServerError,
    TransactionError,
)
from .request import (
    BaseRequest,
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    TableOperationRequest,
    TransactionRequest,
    UpdateRequest,
)
from .request_queue import RequestPriority, RequestQueue
from .result import (
    BaseResult,
    DataResult,
    ErrorResult,
    SuccessResult,
)
from .rpc_protocol import (
    ErrorCode,
    RPCError,
    RPCRequest,
    RPCResponse,
)
from .rpc_server import RPCServer
from .runner import run_database_driver

__all__ = [
    # Protocol
    "ErrorCode",
    "RPCError",
    "RPCRequest",
    "RPCResponse",
    # Requests
    "BaseRequest",
    "TableOperationRequest",
    "InsertRequest",
    "SelectRequest",
    "UpdateRequest",
    "DeleteRequest",
    "TransactionRequest",
    # Results
    "BaseResult",
    "SuccessResult",
    "ErrorResult",
    "DataResult",
    # Drivers
    "BaseDatabaseDriver",
    "SQLiteDriver",
    "create_driver",
    # RPC Server
    "RPCServer",
    # Request Queue
    "RequestQueue",
    "RequestPriority",
    # Runner
    "run_database_driver",
    # Exceptions
    "DriverError",
    "DriverConnectionError",
    "DriverOperationError",
    "DriverNotFoundError",
    "RequestQueueError",
    "RequestQueueFullError",
    "RequestTimeoutError",
    "RPCServerError",
    "TransactionError",
]
