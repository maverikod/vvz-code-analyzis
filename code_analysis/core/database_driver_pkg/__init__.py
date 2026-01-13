"""
Database driver package for RPC-based database operations.

This package provides RPC infrastructure for database driver processes,
including request/result classes, protocol definitions, and serialization utilities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .rpc_protocol import (
    ErrorCode,
    RPCError,
    RPCRequest,
    RPCResponse,
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
from .result import (
    BaseResult,
    DataResult,
    ErrorResult,
    SuccessResult,
)

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
]
