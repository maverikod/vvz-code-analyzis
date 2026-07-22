"""
Database driver package (stage 2: driver-direct architecture).

Holds the PostgreSQL driver, its domain free functions, and driver-level
exceptions. The RPC transport (server, request queue, wire serialization,
handler mixins) was deleted once every caller was repointed to hand commands
a connected driver directly instead of going through it -- there was never a
real out-of-process boundary for PostgreSQL (see
:mod:`code_analysis.core.database_client.factory`).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .driver_factory import create_driver
from .drivers.base import BaseDatabaseDriver
from .exceptions import (
    DriverConnectionError,
    DriverError,
    DriverNotFoundError,
    DriverOperationError,
    TransactionError,
)

__all__ = [
    "BaseDatabaseDriver",
    "create_driver",
    "DriverError",
    "DriverConnectionError",
    "DriverOperationError",
    "DriverNotFoundError",
    "TransactionError",
]
