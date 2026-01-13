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
from typing import Any, Dict, Optional

from .drivers.base import BaseDatabaseDriver
from .exceptions import RPCServerError
from .request_queue import RequestPriority, RequestQueue
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
                request_dict = json.loads(request_data)
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
        """Process requests from queue (background thread)."""
        while self.running:
            try:
                queued_request = self.request_queue.dequeue()
                if queued_request:
                    # Process request
                    # Note: Currently requests are processed synchronously in _handle_client
                    # This background thread could be used for async processing in the future
                    pass
            except Exception as e:
                logger.error(f"Error processing request: {e}", exc_info=True)

    def _process_request(self, request: RPCRequest) -> RPCResponse:
        """Process RPC request and return response.

        Args:
            request: RPC request

        Returns:
            RPC response
        """
        try:
            method = request.method
            params = request.params

            # Route to appropriate handler
            if method == "create_table":
                result = self._handle_create_table(params)
            elif method == "drop_table":
                result = self._handle_drop_table(params)
            elif method == "insert":
                result = self._handle_insert(params)
            elif method == "update":
                result = self._handle_update(params)
            elif method == "delete":
                result = self._handle_delete(params)
            elif method == "select":
                result = self._handle_select(params)
            elif method == "execute":
                result = self._handle_execute(params)
            elif method == "begin_transaction":
                result = self._handle_begin_transaction(params)
            elif method == "commit_transaction":
                result = self._handle_commit_transaction(params)
            elif method == "rollback_transaction":
                result = self._handle_rollback_transaction(params)
            elif method == "get_table_info":
                result = self._handle_get_table_info(params)
            elif method == "sync_schema":
                result = self._handle_sync_schema(params)
            else:
                return RPCResponse(
                    error=RPCError(
                        code=ErrorCode.INVALID_REQUEST,
                        message=f"Unknown method: {method}",
                    ),
                    request_id=request.request_id,
                )

            return RPCResponse(result=result, request_id=request.request_id)
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            return RPCResponse(
                error=RPCError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=str(e),
                ),
                request_id=request.request_id,
            )

    def _handle_create_table(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle create_table RPC method."""
        schema = params.get("schema")
        if not schema:
            raise ValueError("schema parameter is required")
        success = self.driver.create_table(schema)
        return {"success": success}

    def _handle_drop_table(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle drop_table RPC method."""
        table_name = params.get("table_name")
        if not table_name:
            raise ValueError("table_name parameter is required")
        success = self.driver.drop_table(table_name)
        return {"success": success}

    def _handle_insert(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle insert RPC method."""
        table_name = params.get("table_name")
        data = params.get("data")
        if not table_name or not data:
            raise ValueError("table_name and data parameters are required")
        row_id = self.driver.insert(table_name, data)
        return {"row_id": row_id}

    def _handle_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle update RPC method."""
        table_name = params.get("table_name")
        where = params.get("where")
        data = params.get("data")
        if not table_name or not where or not data:
            raise ValueError("table_name, where, and data parameters are required")
        affected_rows = self.driver.update(table_name, where, data)
        return {"affected_rows": affected_rows}

    def _handle_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle delete RPC method."""
        table_name = params.get("table_name")
        where = params.get("where")
        if not table_name or not where:
            raise ValueError("table_name and where parameters are required")
        affected_rows = self.driver.delete(table_name, where)
        return {"affected_rows": affected_rows}

    def _handle_select(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle select RPC method."""
        table_name = params.get("table_name")
        if not table_name:
            raise ValueError("table_name parameter is required")
        where = params.get("where")
        columns = params.get("columns")
        limit = params.get("limit")
        offset = params.get("offset")
        order_by = params.get("order_by")
        rows = self.driver.select(table_name, where, columns, limit, offset, order_by)
        return {"data": rows}

    def _handle_execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle execute RPC method."""
        sql = params.get("sql")
        if not sql:
            raise ValueError("sql parameter is required")
        params_tuple = params.get("params")
        result = self.driver.execute(sql, params_tuple)
        return result

    def _handle_begin_transaction(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle begin_transaction RPC method."""
        transaction_id = self.driver.begin_transaction()
        return {"transaction_id": transaction_id}

    def _handle_commit_transaction(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle commit_transaction RPC method."""
        transaction_id = params.get("transaction_id")
        if not transaction_id:
            raise ValueError("transaction_id parameter is required")
        success = self.driver.commit_transaction(transaction_id)
        return {"success": success}

    def _handle_rollback_transaction(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle rollback_transaction RPC method."""
        transaction_id = params.get("transaction_id")
        if not transaction_id:
            raise ValueError("transaction_id parameter is required")
        success = self.driver.rollback_transaction(transaction_id)
        return {"success": success}

    def _handle_get_table_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_table_info RPC method."""
        table_name = params.get("table_name")
        if not table_name:
            raise ValueError("table_name parameter is required")
        info = self.driver.get_table_info(table_name)
        return {"info": info}

    def _handle_sync_schema(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle sync_schema RPC method."""
        schema_definition = params.get("schema_definition")
        if not schema_definition:
            raise ValueError("schema_definition parameter is required")
        backup_dir = params.get("backup_dir")
        result = self.driver.sync_schema(schema_definition, backup_dir)
        return result

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
