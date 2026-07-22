"""
Database client support package (stage 2: driver-direct architecture).

The RPC transport (DatabaseClient, RPCClient, InProcessRpcClient, the wire
protocol) was deleted once every caller was repointed to hand commands a
connected driver directly (see
:mod:`code_analysis.core.database_driver_pkg.drivers.postgres`, constructed via
:func:`code_analysis.core.database_client.factory.create_database_client_from_config_path`).
This package now holds only pieces still used by driver-direct code:
exception types some callers still catch by name, retry classification
helpers, atomic file-data batch builders, and shared object/mapper dataclasses.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .exceptions import (
    ConnectionError,
    DatabaseClientError,
    RPCClientError,
    RPCResponseError,
    TimeoutError,
    ValidationError,
)

__all__ = [
    "DatabaseClientError",
    "RPCClientError",
    "ConnectionError",
    "TimeoutError",
    "ValidationError",
    "RPCResponseError",
]
