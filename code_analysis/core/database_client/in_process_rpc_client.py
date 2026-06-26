"""
In-process RPC transport: same contract as :class:`RPCClient`, no Unix socket.

Used for PostgreSQL when :class:`~code_analysis.core.database_driver_pkg.rpc_handlers.RPCHandlers`
runs in the same process as the MCP server or a worker.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

from code_analysis.core.database_driver_pkg.rpc_dispatch import process_rpc_request
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers

from .exceptions import ConnectionError, RPCClientError, RPCResponseError
from .protocol import RPCRequest, RPCResponse

logger = logging.getLogger(__name__)


def _short_request_id(request_id: Optional[str]) -> str:
    """Return short request id."""
    if not request_id:
        return "none"
    s = str(request_id)
    return (s[:8] + "…") if len(s) > 8 else s


class InProcessRpcClient:
    """Synchronous RPC dispatch in-process; mirrors :meth:`RPCClient.call` behavior."""

    def __init__(
        self,
        handlers: RPCHandlers,
        *,
        call_lock: Optional[threading.Lock] = None,
    ) -> None:
        """Initialize the instance."""
        self.handlers = handlers
        self._call_lock = call_lock if call_lock is not None else threading.Lock()
        self._closed = False
        self._connected = False

    def connect(self) -> None:
        """Return connect."""
        if self._closed:
            raise ConnectionError("In-process RPC client is closed")
        self._connected = True

    def disconnect(self, *, close_driver: bool = True) -> None:
        """Return disconnect."""
        self._closed = True
        self._connected = False
        if not close_driver:
            return
        try:
            self.handlers.driver.disconnect()
        except Exception:
            logger.debug(
                "InProcessRpcClient disconnect: driver.disconnect failed", exc_info=True
            )

    def is_connected(self) -> bool:
        """Return is connected."""
        return self._connected and not self._closed

    def health_check(self) -> bool:
        """Return health check."""
        return self.is_connected()

    def call(
        self,
        method: str,
        params: Dict[str, Any],
        request_id: Optional[str] = None,
        *,
        priority: int = 0,
    ) -> RPCResponse:
        """Return call."""
        if not request_id:
            request_id = str(uuid.uuid4())
        request = RPCRequest(
            method=method,
            params=params,
            priority=priority,
            request_id=request_id,
        )
        tid = (params or {}).get("transaction_id") if isinstance(params, dict) else None
        logger.debug(
            "[CHAIN] in_process_rpc call method=%s tid=%s request_id=%s",
            method,
            (tid[:8] + "…") if tid and len(str(tid)) > 8 else tid,
            request_id[:8] + "…" if request_id and len(request_id) > 8 else request_id,
        )
        # Critical section: only lifecycle visibility for `_closed`. We hold `_call_lock`
        # just long enough for `disconnect()` and concurrent `call()` to agree on whether
        # a new dispatch may begin. `process_rpc_request` runs without this lock so
        # concurrent PostgreSQL RPCs can proceed and contend on the driver pool instead
        # of FIFO-serializing the whole universal path.
        with self._call_lock:
            if self._closed:
                raise ConnectionError("In-process RPC client is closed")
        t_rpc = time.perf_counter()
        try:
            response = process_rpc_request(self.handlers, request)
        except Exception as e:
            logger.warning("[CHAIN] in_process_rpc call method=%s error: %s", method, e)
            raise RPCClientError(f"RPC call failed: {e}") from e

        elapsed_ms = (time.perf_counter() - t_rpc) * 1000.0
        logger.debug(
            "[SAVE_PATH] in_process_rpc method=%s request_id=%s elapsed_ms=%.1f",
            method,
            _short_request_id(request_id),
            elapsed_ms,
        )
        if response.is_error() and response.error:
            logger.debug(
                "[CHAIN] in_process_rpc _dispatch failure method=%s request_id=%s error_kind=rpc_response_error exc=%s",
                method,
                _short_request_id(request_id),
                response.error.message,
            )
            raise RPCResponseError(
                message=response.error.message,
                error_code=response.error.code.value,
                error_data=response.error.data,
            )
        logger.debug("[CHAIN] in_process_rpc call method=%s success", method)
        return response
