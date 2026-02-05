"""
Protocol and wire types for database RPC.

Contract (RPC protocol, request/response types) lives here; database_driver_pkg
implements the server and imports from this package.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .rpc_protocol import ErrorCode, RPCError, RPCRequest, RPCResponse
from .request import (
    BaseRequest,
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    TableOperationRequest,
    TransactionRequest,
    UpdateRequest,
)
from .wire_result import BaseResult, DataResult, ErrorResult, SuccessResult

__all__ = [
    "ErrorCode",
    "RPCError",
    "RPCRequest",
    "RPCResponse",
    "BaseRequest",
    "TableOperationRequest",
    "InsertRequest",
    "SelectRequest",
    "UpdateRequest",
    "DeleteRequest",
    "TransactionRequest",
    "BaseResult",
    "SuccessResult",
    "ErrorResult",
    "DataResult",
]
