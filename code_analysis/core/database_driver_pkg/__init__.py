"""
Database driver package for RPC-based database operations.

RPC server, request queue, drivers, serialization. Contract (protocol, request/result
types) lives in code_analysis.core.database_client.protocol.

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
from .request_queue import RequestPriority, RequestQueue
from .rpc_server import RPCServer
from .runner import run_database_driver

__all__ = [
    "BaseDatabaseDriver",
    "SQLiteDriver",
    "create_driver",
    "RPCServer",
    "RequestQueue",
    "RequestPriority",
    "run_database_driver",
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
