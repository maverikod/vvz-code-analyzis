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
from pathlib import Path
from typing import Optional

from .drivers.base import BaseDatabaseDriver
from .exceptions import RPCServerError
from .request import DeleteRequest, InsertRequest, SelectRequest, UpdateRequest
from .request_queue import RequestPriority, RequestQueue
from .result import BaseResult, ErrorResult
from .rpc_handlers import RPCHandlers
from .rpc_protocol import ErrorCode, RPCError, RPCRequest, RPCResponse
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
    ):
        """Initialize RPC server.

        Args:
            driver: Database driver instance
            request_queue: Request queue for managing requests
            socket_path: Path to Unix socket file
        """
        self.driver = driver
        self.request_queue = request_queue
        self.socket_path = socket_path
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self._lock = threading.Lock()
        self.handlers = RPCHandlers(driver)

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
            self.server_socket.settimeout(1.0)  # Allow periodic checks

            self.running = True
            logger.info(f"RPC server started on socket: {self.socket_path}")

            # Start request processing thread
            processing_thread = threading.Thread(
                target=self._process_requests, daemon=True
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
                import uuid

                rpc_request.request_id = str(uuid.uuid4())

            # Add request to queue
            try:
                self.request_queue.enqueue(
                    rpc_request.request_id,
                    rpc_request,
                    priority=RequestPriority.NORMAL,
                )
            except Exception as e:
                error_response = RPCResponse(
                    error=RPCError(
                        code=ErrorCode.INTERNAL_ERROR,
                        message=f"Failed to enqueue request: {e}",
                    ),
                    request_id=rpc_request.request_id,
                )
                self._send_data(client_sock, serialize_response(error_response))
                return

            # Wait for response (processed by _process_requests)
            # For now, process synchronously
            response = self._process_request(rpc_request)

            # Send response
            self._send_data(client_sock, serialize_response(response))
        except Exception as e:
            logger.error(f"Error handling client: {e}", exc_info=True)
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _process_requests(self) -> None:
        """Process requests from queue (background thread).

        **Current Implementation**: This method runs in a background thread but
        currently only performs periodic checks. Requests are processed synchronously
        in _handle_client() method for simplicity and immediate response.

        **Future Enhancement**: This thread is reserved for future asynchronous
        request processing implementation where requests would be dequeued here
        and processed asynchronously, allowing better handling of long-running
        operations and improved concurrency.

        Note: The thread is kept alive to maintain the architecture for future
        enhancements without requiring major refactoring.
        """
        while self.running:
            try:
                # Periodic check - requests are currently processed synchronously
                # in _handle_client() for immediate response
                # Future: This is where async request processing would be implemented
                import time

                time.sleep(0.1)  # Small sleep to avoid busy waiting
            except Exception as e:
                logger.error(f"Error in request processing thread: {e}", exc_info=True)

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
                    "begin_transaction": self.handlers.handle_begin_transaction,
                    "commit_transaction": self.handlers.handle_commit_transaction,
                    "rollback_transaction": self.handlers.handle_rollback_transaction,
                    "get_table_info": self.handlers.handle_get_table_info,
                    "sync_schema": self.handlers.handle_sync_schema,
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
                    return RPCResponse(
                        error=rpc_error,
                        request_id=request.request_id,
                    )
                else:
                    # Convert SuccessResult or DataResult to result dict
                    result_dict = result.to_dict()
                    return RPCResponse(result=result_dict, request_id=request.request_id)
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
            logger.error(f"Error processing request: {e}", exc_info=True)
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
            if length > 10 * 1024 * 1024:  # 10 MB limit
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
