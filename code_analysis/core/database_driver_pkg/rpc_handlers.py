"""
RPC method handlers for database driver operations.

Facade class that combines all handler mixins.
Handles individual RPC method calls by delegating to driver.
Uses BaseRequest and BaseResult classes for type safety and validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from .drivers.base import BaseDatabaseDriver
from .rpc_handlers_ast_cst_query import _RPCHandlersASTCSTQueryMixin
from .rpc_handlers_ast_modify import _RPCHandlersASTModifyMixin
from .rpc_handlers_base import _RPCHandlersBaseMixin
from .rpc_handlers_cst_modify import _RPCHandlersCSTModifyMixin
from .rpc_handlers_schema import _RPCHandlersSchemaMixin


class RPCHandlers(
    _RPCHandlersBaseMixin,
    _RPCHandlersSchemaMixin,
    _RPCHandlersASTCSTQueryMixin,
    _RPCHandlersASTModifyMixin,
    _RPCHandlersCSTModifyMixin,
):
    """RPC method handlers for database operations.

    Facade class that combines all handler mixins.
    All handlers use BaseRequest and BaseResult classes for type safety
    and proper validation.
    """

    def __init__(self, driver: BaseDatabaseDriver):
        """Initialize RPC handlers.

        Args:
            driver: Database driver instance
        """
        self.driver = driver
