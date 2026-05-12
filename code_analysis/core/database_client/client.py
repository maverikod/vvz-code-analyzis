"""
Database client base class.

Provides object-oriented API for database operations via RPC client.
Converts high-level operations to RPC calls.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .client_api_ast_cst import _ClientAPIASTCSTMixin
from .client_api_attributes import _ClientAPIAttributesMixin
from .client_api_classes_functions import _ClientAPIClassesFunctionsMixin
from .client_api_comprehensive_analysis import (
    _ClientAPIComprehensiveAnalysisMixin,
)
from .client_api_duplicates_stats import _ClientAPIDuplicatesStatsMixin
from .client_api_files import _ClientAPIFilesMixin
from .client_api_issues_usages import _ClientAPIIssuesUsagesMixin
from .client_api_methods_imports import _ClientAPIMethodsImportsMixin
from .client_api_projects import _ClientAPIProjectsMixin
from .client_api_search import _ClientAPISearchMixin
from .client_helpers import _ClientHelpersMixin
from .client_operations import _ClientOperationsMixin
from .client_schema import _ClientSchemaMixin
from .client_transactions import _ClientTransactionsMixin
from .rpc_client import RPCClient


class DatabaseClient(
    _ClientHelpersMixin,
    _ClientOperationsMixin,
    _ClientSchemaMixin,
    _ClientTransactionsMixin,
    _ClientAPIProjectsMixin,
    _ClientAPISearchMixin,
    _ClientAPIFilesMixin,
    _ClientAPIComprehensiveAnalysisMixin,
    _ClientAPIAttributesMixin,
    _ClientAPIASTCSTMixin,
    _ClientAPIClassesFunctionsMixin,
    _ClientAPIMethodsImportsMixin,
    _ClientAPIIssuesUsagesMixin,
    _ClientAPIDuplicatesStatsMixin,
):
    """Database client for RPC-based database operations.

    Provides high-level API for database operations by converting
    them to RPC calls through RPCClient.
    """

    def __init__(
        self,
        socket_path: Optional[str] = None,
        *,
        rpc_client: Optional[Any] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 0.1,
        pool_size: int = 5,
        driver_type: Optional[str] = None,
    ):
        """Initialize database client.

        Args:
            socket_path: Path to Unix socket file (mutually exclusive with ``rpc_client``).
            rpc_client: Pluggable transport with the same contract as :class:`RPCClient`
                (e.g. :class:`~code_analysis.core.database_client.in_process_rpc_client.InProcessRpcClient`).
            timeout: Request timeout in seconds (default: 30.0)
            max_retries: Maximum number of retry attempts (default: 3)
            retry_delay: Delay between retries in seconds (default: 0.1)
            pool_size: Connection pool size (default: 5)
            driver_type: Value from ``code_analysis.database.driver.type`` (e.g. ``postgres``,
                ``sqlite_proxy``). Used for portable SQL such as full-text search; if omitted,
                SQLite-style paths are assumed.
        """
        if (socket_path is not None) == (rpc_client is not None):
            raise ValueError("Provide exactly one of socket_path or rpc_client")
        self._driver_type = driver_type
        #: Merged driver dict ``{type, config}`` from server config (set by factory when applicable).
        self.driver_config: Optional[Dict[str, Any]] = None
        if rpc_client is not None:
            self.rpc_client = rpc_client
        else:
            self.rpc_client = RPCClient(
                socket_path=socket_path,  # type: ignore[arg-type]
                timeout=timeout,
                max_retries=max_retries,
                retry_delay=retry_delay,
                pool_size=pool_size,
            )

    def connect(self) -> None:
        """Connect to database driver via RPC."""
        self.rpc_client.connect()

    def disconnect(self) -> None:
        """Disconnect from database driver."""
        self.rpc_client.disconnect()

    def is_connected(self) -> bool:
        """Check if client is connected.

        Returns:
            True if connected, False otherwise
        """
        return self.rpc_client.is_connected()

    def health_check(self) -> bool:
        """Check if database driver is healthy.

        Returns:
            True if driver is healthy, False otherwise
        """
        return self.rpc_client.health_check()
