"""
RPC server for database driver process.

Handles RPC requests via Unix socket, processes them through driver,
and returns responses.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import socket
import struct
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional

from ..constants import (
    DEFAULT_RPC_WORKER_POOL_SIZE,
    DEFAULT_REQUEST_TIMEOUT,
    RPC_MAX_REQUEST_SIZE,
    RPC_PROCESSING_LOOP_INTERVAL,
    RPC_SERVER_SOCKET_TIMEOUT,
)

from code_analysis.core.database_client.protocol import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    UpdateRequest,
    BaseResult,
    DataResult,
    ErrorResult,
    SuccessResult,
    ErrorCode,
    RPCError,
    RPCRequest,
    RPCResponse,
)
from .drivers.base import BaseDatabaseDriver
from .exceptions import RPCServerError
from .request_queue import RequestPriority, RequestQueue
from .rpc_handlers import RPCHandlers
from .serialization import serialize_response

logger = logging.getLogger(__name__)


class RPCServer:
    """RPC server for database driver process.

    Handles RPC requests via Unix socket, processes them through driver,
    and returns responses.
    """

    def __init__(
        self,
        driver: BaseDatabaseDriver,
        request_queue: RequestQueue,
        socket_path: str,
        worker_pool_size: int = DEFAULT_RPC_WORKER_POOL_SIZE,
    ):
        """Initialize RPC server.

        Args:
            driver: Database driver instance
            request_queue: Request queue for managing requests
            socket_path: Path to Unix socket file
            worker_pool_size: Size of worker thread pool for processing requests
        """
        self.driver = driver
        self.request_queue = request_queue
        self.socket_path = socket_path
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self._lock = threading.Lock()
        self.handlers = RPCHandlers(driver)
        self.worker_pool_size = worker_pool_size
        self.worker_pool: Optional[ThreadPoolExecutor] = None
        # Map request_id -> (client_sock, condition, response)
        self._pending_responses: Dict[
            str, tuple[socket.socket, threading.Condition, Optional[RPCResponse]]
        ] = {}
        self._responses_lock = threading.Lock()

    def start(self) -> None:
        """Start RPC server."""
        if self.running:
            raise RPCServerError("RPC server is already running")

        try:
            socket_file = Path(self.socket_path)
            # Remove existing socket file if it exists
            if socket_file.exists():
                socket_file.unlink()

            # Create Unix socket
            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(self.socket_path)
            self.server_socket.listen(5)
            self.server_socket.settimeout(
                RPC_SERVER_SOCKET_TIMEOUT
            )  # Allow periodic checks

            self.running = True
            logger.info(f"RPC server started on socket: {self.socket_path}")

            # Start worker pool for async request processing
            self.worker_pool = ThreadPoolExecutor(
                max_workers=self.worker_pool_size, thread_name_prefix="RPCWorker"
            )
            logger.info(f"RPC worker pool started (size: {self.worker_pool_size})")

            # Start request processing thread
            processing_thread = threading.Thread(
                target=self._process_requests_loop, daemon=True, name="RPCProcessor"
            )
            processing_thread.start()

            # Start server loop
            while self.running:
                try:
                    client_sock, _ = self.server_socket.accept()
                    # Handle client in separate thread
                    thread = threading.Thread(
                        target=self._handle_client, args=(client_sock,), daemon=True
                    )
                    thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}", exc_info=True)
        except Exception as e:
            self.running = False
            raise RPCServerError(f"Failed to start RPC server: {e}") from e

    def stop(self) -> None:
        """Stop RPC server."""
        with self._lock:
            if not self.running:
                return

            self.running = False
            logger.info("Stopping RPC server...")

            # Shutdown worker pool
            if self.worker_pool:
                self.worker_pool.shutdown(wait=True)
                logger.info("RPC worker pool stopped")

            # Close all pending client connections
            with self._responses_lock:
                for request_id, (client_sock, _, _) in list(
                    self._pending_responses.items()
                ):
                    try:
                        client_sock.close()
                    except Exception:
                        pass
                self._pending_responses.clear()

            if self.server_socket:
                try:
                    self.server_socket.close()
                except Exception:
                    pass

            # Remove socket file
            socket_file = Path(self.socket_path)
            if socket_file.exists():
                try:
                    socket_file.unlink()
                except Exception:
                    pass

            logger.info("RPC server stopped")

    def _handle_client(self, client_sock: socket.socket) -> None:
        """Handle client connection.

        Args:
            client_sock: Client socket connection
        """
        try:
            # Receive request
            request_data = self._receive_data(client_sock)
            if not request_data:
                return

            # Parse RPC request
            try:
                request_dict = json.loads(request_data.decode("utf-8"))
                rpc_request = RPCRequest.from_dict(request_dict)
            except Exception as e:
                # Send error response
                error_response = RPCResponse(
                    error=RPCError(
                        code=ErrorCode.INVALID_REQUEST,
                        message=f"Invalid request format: {e}",
                    ),
                    request_id=None,
                )
                self._send_data(client_sock, serialize_response(error_response))
                return

            # Generate request ID if not provided
            if not rpc_request.request_id:
                rpc_request.request_id = str(uuid.uuid4())

            # Register pending response
            condition = threading.Condition(self._responses_lock)
            with self._responses_lock:
                self._pending_responses[rpc_request.request_id] = (
                    client_sock,
                    condition,
                    None,
                )

            # Add request to queue for async processing
            try:
                self.request_queue.enqueue(
                    rpc_request.request_id,
                    rpc_request,
                    priority=RequestPriority.NORMAL,
                )
                logger.debug(
                    f"Request {rpc_request.request_id} enqueued for async processing"
                )
            except Exception as e:
                # Remove from pending and send error immediately
                with self._responses_lock:
                    if rpc_request.request_id in self._pending_responses:
                        del self._pending_responses[rpc_request.request_id]
                error_response = RPCResponse(
                    error=RPCError(
                        code=ErrorCode.INTERNAL_ERROR,
                        message=f"Failed to enqueue request: {e}",
                    ),
                    request_id=rpc_request.request_id,
                )
                self._send_data(client_sock, serialize_response(error_response))
                return

            # Wait for response to be processed asynchronously
            response = None
            with condition:
                if condition.wait(timeout=DEFAULT_REQUEST_TIMEOUT):
                    # Got notification, response should be ready
                    # Get response while holding condition lock (which is _responses_lock)
                    pending_entry = self._pending_responses.get(rpc_request.request_id)
                    if pending_entry:
                        response = pending_entry[2]
                else:
                    # Timeout - check if response arrived anyway
                    pending_entry = self._pending_responses.get(rpc_request.request_id)
                    if pending_entry:
                        response = pending_entry[2]

            # Remove from pending (condition lock already released)
            with self._responses_lock:
                if rpc_request.request_id in self._pending_responses:
                    del self._pending_responses[rpc_request.request_id]

            # Send response if available
            if response:
                self._send_data(client_sock, serialize_response(response))
            else:
                # Timeout or error
                timeout_response = RPCResponse(
                    error=RPCError(
                        code=ErrorCode.INTERNAL_ERROR,
                        message="Request processing timeout",
                    ),
                    request_id=rpc_request.request_id,
                )
                self._send_data(client_sock, serialize_response(timeout_response))
        except Exception as e:
            logger.error(f"Error handling client: {e}", exc_info=True)
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _process_requests_loop(self) -> None:
        """Background loop to process requests from queue asynchronously."""
        logger.info("RPC request processing loop started")
        while self.running:
            try:
                # Get next request from queue
                queued_request = self.request_queue.dequeue()
                if queued_request is None:
                    # No requests available, sleep briefly
                    time.sleep(RPC_PROCESSING_LOOP_INTERVAL)
                    continue

                # Process request in worker pool
                if self.worker_pool:
                    logger.debug(
                        f"Submitting request {queued_request.request_id} to worker pool"
                    )
                    self.worker_pool.submit(
                        self._process_request_async,
                        queued_request.request_id,
                        queued_request.request,
                    )
            except Exception as e:
                logger.error(f"Error in request processing loop: {e}", exc_info=True)
                time.sleep(RPC_PROCESSING_LOOP_INTERVAL * 10)  # Wait before retrying

        logger.info("RPC request processing loop stopped")

    def _process_request_async(self, request_id: str, request: RPCRequest) -> None:
        """Process request asynchronously and send response to client.

        Args:
            request_id: Request ID
            request: RPC request to process
        """
        try:
            logger.debug(f"Processing request {request_id} asynchronously")
            # Process request
            response = self._process_request(request)
            logger.debug(f"Request {request_id} processed, sending response")

            # Send response to waiting client
            with self._responses_lock:
                if request_id in self._pending_responses:
                    client_sock, condition, _ = self._pending_responses[request_id]
                    self._pending_responses[request_id] = (
                        client_sock,
                        condition,
                        response,
                    )
                    # Notify waiting client
                    # Note: condition uses self._responses_lock, so we're already holding it
                    condition.notify()
        except Exception as e:
            logger.error(f"Error processing request {request_id}: {e}", exc_info=True)
            # Send error response
            error_response = RPCResponse(
                error=RPCError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Request processing error: {e}",
                ),
                request_id=request_id,
            )
            with self._responses_lock:
                if request_id in self._pending_responses:
                    client_sock, condition, _ = self._pending_responses[request_id]
                    self._pending_responses[request_id] = (
                        client_sock,
                        condition,
                        error_response,
                    )
                    # Notify waiting client
                    # Note: condition uses self._responses_lock, so we're already holding it
                    condition.notify()

    def _process_request(self, request: RPCRequest) -> RPCResponse:
        """Process RPC request and return response.

        Converts params to appropriate Request classes and converts
        Result classes to dictionaries for RPC response.

        Args:
            request: RPC request

        Returns:
            RPC response
        """
        try:
            method = request.method
            params = request.params
            tid = params.get("transaction_id") if isinstance(params, dict) else None
            logger.info(
                "[CHAIN] rpc_server _process_request method=%s tid=%s",
                method,
                (str(tid)[:8] + "…") if tid and len(str(tid)) > 8 else tid,
            )

            # Variable to hold result (can be SuccessResult, DataResult, or ErrorResult)
            result: SuccessResult | DataResult | ErrorResult

            # Convert params to Request classes for methods that use them
            if method == "insert":
                try:
                    insert_request = InsertRequest.from_dict(params)
                    result = self.handlers.handle_insert(insert_request)
                except Exception as e:
                    logger.error(f"Error creating InsertRequest: {e}", exc_info=True)
                    result = ErrorResult(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        description=f"Invalid insert request: {e}",
                    )
            elif method == "update":
                try:
                    update_request = UpdateRequest.from_dict(params)
                    result = self.handlers.handle_update(update_request)
                except Exception as e:
                    logger.error(f"Error creating UpdateRequest: {e}", exc_info=True)
                    result = ErrorResult(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        description=f"Invalid update request: {e}",
                    )
            elif method == "delete":
                try:
                    delete_request = DeleteRequest.from_dict(params)
                    result = self.handlers.handle_delete(delete_request)
                except Exception as e:
                    logger.error(f"Error creating DeleteRequest: {e}", exc_info=True)
                    result = ErrorResult(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        description=f"Invalid delete request: {e}",
                    )
            elif method == "select":
                try:
                    select_request = SelectRequest.from_dict(params)
                    result = self.handlers.handle_select(select_request)
                except Exception as e:
                    logger.error(f"Error creating SelectRequest: {e}", exc_info=True)
                    result = ErrorResult(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        description=f"Invalid select request: {e}",
                    )
            else:
                # Route to appropriate handler for methods that don't use Request classes
                handler_map = {
                    "create_table": self.handlers.handle_create_table,
                    "drop_table": self.handlers.handle_drop_table,
                    "execute": self.handlers.handle_execute,
                    "execute_batch": self.handlers.handle_execute_batch,
                    "begin_transaction": self.handlers.handle_begin_transaction,
                    "commit_transaction": self.handlers.handle_commit_transaction,
                    "rollback_transaction": self.handlers.handle_rollback_transaction,
                    "get_table_info": self.handlers.handle_get_table_info,
                    "sync_schema": self.handlers.handle_sync_schema,
                    "query_ast": self.handlers.handle_query_ast,
                    "query_cst": self.handlers.handle_query_cst,
                    "modify_ast": self.handlers.handle_modify_ast,
                    "modify_cst": self.handlers.handle_modify_cst,
                    "index_file": self.handlers.handle_index_file,
                }

                handler = handler_map.get(method)
                if not handler:
                    return RPCResponse(
                        error=RPCError(
                            code=ErrorCode.INVALID_REQUEST,
                            message=f"Unknown method: {method}",
                        ),
                        request_id=request.request_id,
                    )

                result = handler(params)

            # Convert BaseResult to dictionary for RPC response
            if isinstance(result, BaseResult):
                if result.is_error() and isinstance(result, ErrorResult):
                    # Convert ErrorResult to RPCError
                    rpc_error = result.to_rpc_error()
                    logger.warning(
                        "[CHAIN] rpc_server _process_request method=%s handler_error=%s",
                        method,
                        getattr(rpc_error, "message", rpc_error),
                    )
                    return RPCResponse(
                        error=rpc_error,
                        request_id=request.request_id,
                    )
                else:
                    # Convert SuccessResult or DataResult to result dict
                    result_dict = result.to_dict()
                    return RPCResponse(
                        result=result_dict, request_id=request.request_id
                    )
            else:
                # Fallback for unexpected result type
                logger.error(f"Unexpected result type: {type(result)}")
                return RPCResponse(
                    error=RPCError(
                        code=ErrorCode.INTERNAL_ERROR,
                        message="Unexpected result type from handler",
                    ),
                    request_id=request.request_id,
                )
        except Exception as e:
            logger.error(
                "[CHAIN] rpc_server _process_request method=%s exception: %s",
                method,
                e,
                exc_info=True,
            )
            return RPCResponse(
                error=RPCError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=str(e),
                ),
                request_id=request.request_id,
            )

    def _receive_data(self, sock: socket.socket) -> Optional[bytes]:
        """Receive data from socket.

        Args:
            sock: Socket connection

        Returns:
            Received data or None if error
        """
        try:
            # Read length prefix (4 bytes)
            length_data = sock.recv(4)
            if len(length_data) != 4:
                return None

            length = struct.unpack("!I", length_data)[0]
            if length > RPC_MAX_REQUEST_SIZE:
                return None

            # Read data
            data = b""
            while len(data) < length:
                chunk = sock.recv(length - len(data))
                if not chunk:
                    return None
                data += chunk

            return data
        except Exception:
            return None

    def _send_data(self, sock: socket.socket, data: str) -> None:
        """Send data to socket.

        Args:
            sock: Socket connection
            data: Data to send (string)
        """
        try:
            data_bytes = data.encode("utf-8")
            length = len(data_bytes)
            # Send length prefix
            sock.sendall(struct.pack("!I", length))
            # Send data
            sock.sendall(data_bytes)
        except Exception as e:
            logger.error(f"Error sending data: {e}", exc_info=True)
