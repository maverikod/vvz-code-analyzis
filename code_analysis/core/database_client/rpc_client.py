"""
RPC client for database driver communication.

Handles connection to driver process via Unix socket, sends requests,
receives responses, and manages connection pooling and retry logic.

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
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Dict, Optional

from .protocol import RPCRequest, RPCResponse
from .exceptions import (
    ConnectionError,
    RPCClientError,
    RPCResponseError,
    TimeoutError,
)

logger = logging.getLogger(__name__)


class RPCClient:
    """RPC client for database driver communication.

    Handles connection to driver process via Unix socket, sends requests,
    receives responses, and manages connection pooling and retry logic.
    """

    def __init__(
        self,
        socket_path: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 0.1,
        pool_size: int = 5,
    ):
        """Initialize RPC client.

        Args:
            socket_path: Path to Unix socket file
            timeout: Request timeout in seconds (default: 30.0)
            max_retries: Maximum number of retry attempts (default: 3)
            retry_delay: Delay between retries in seconds (default: 0.1)
            pool_size: Connection pool size (default: 5)
        """
        self.socket_path = socket_path
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.pool_size = pool_size
        self._connection_pool: Queue[socket.socket] = Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._closed = False
        self._connected = False

    def connect(self) -> None:
        """Connect to RPC server.

        Pre-creates connections in the pool for better performance.

        Raises:
            ConnectionError: If client is closed or no connection could be created.
        """
        if self._closed:
            raise ConnectionError("RPC client is closed")

        # Pre-create connections in pool
        created = 0
        for _ in range(self.pool_size):
            try:
                sock = self._create_connection()
                self._connection_pool.put(sock)
                created += 1
            except Exception as e:
                logger.warning(f"Failed to pre-create connection: {e}")
        if created == 0:
            raise ConnectionError(f"Cannot connect to RPC server at {self.socket_path}")
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect from RPC server and close all connections."""
        with self._lock:
            if self._closed:
                return

            self._closed = True
            self._connected = False

            # Close all connections in pool
            while not self._connection_pool.empty():
                try:
                    sock = self._connection_pool.get_nowait()
                    try:
                        sock.close()
                    except Exception:
                        pass
                except Empty:
                    break

    def is_connected(self) -> bool:
        """Check if client is connected (connect() was called and disconnect() not yet).

        Returns:
            True if connected, False otherwise
        """
        return self._connected and not self._closed

    def call(
        self,
        method: str,
        params: Dict[str, Any],
        request_id: Optional[str] = None,
    ) -> RPCResponse:
        """Call RPC method.

        Args:
            method: RPC method name
            params: Method parameters
            request_id: Optional request ID (generated if not provided)

        Returns:
            RPC response

        Raises:
            RPCClientError: If RPC call fails
            TimeoutError: If request times out
            ConnectionError: If connection fails
        """
        if self._closed:
            raise ConnectionError("RPC client is closed")

        if not request_id:
            request_id = str(uuid.uuid4())

        request = RPCRequest(method=method, params=params, request_id=request_id)
        tid = (params or {}).get("transaction_id") if isinstance(params, dict) else None
        logger.info(
            "[CHAIN] rpc_client call method=%s tid=%s request_id=%s",
            method,
            (tid[:8] + "…") if tid and len(str(tid)) > 8 else tid,
            request_id[:8] + "…" if request_id and len(request_id) > 8 else request_id,
        )

        # Retry logic
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                out = self._send_request(request)
                logger.info("[CHAIN] rpc_client call method=%s success", method)
                return out
            except (ConnectionError, TimeoutError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    logger.debug(
                        f"Retrying RPC call (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                else:
                    raise
            except Exception as e:
                # Non-retryable errors
                logger.warning("[CHAIN] rpc_client call method=%s error: %s", method, e)
                raise RPCClientError(f"RPC call failed: {e}") from e

        # Should not reach here, but just in case
        if last_error:
            raise last_error
        raise RPCClientError("RPC call failed for unknown reason")

    def _send_request(self, request: RPCRequest) -> RPCResponse:
        """Send RPC request and receive response.

        Args:
            request: RPC request

        Returns:
            RPC response

        Raises:
            ConnectionError: If connection fails
            TimeoutError: If request times out
            RPCResponseError: If response contains error
        """
        sock: Optional[socket.socket] = None
        try:
            # Get connection from pool or create new one
            try:
                sock = self._connection_pool.get(timeout=1.0)
            except Empty:
                sock = self._create_connection()

            # Set timeout
            sock.settimeout(self.timeout)

            # Send request
            request_dict = request.to_dict()
            request_json = json.dumps(request_dict)
            self._send_data(sock, request_json)

            # Receive response
            response_data = self._receive_data(sock)
            if not response_data:
                raise ConnectionError("Failed to receive response")

            # Parse response
            response_dict = json.loads(response_data.decode("utf-8"))
            response = RPCResponse.from_dict(response_dict)

            # Don't return connection to pool - server closes it after each request
            # Server architecture: one request per connection, then close
            # So we always create new connection for each request
            sock = None  # Will be closed in finally

            # Check for errors in response
            if response.is_error() and response.error:
                raise RPCResponseError(
                    message=response.error.message,
                    error_code=response.error.code.value,
                    error_data=response.error.data,
                )

            return response

        except socket.timeout:
            raise TimeoutError(f"Request timed out after {self.timeout} seconds")
        except socket.error as e:
            raise ConnectionError(f"Socket error: {e}") from e
        except json.JSONDecodeError as e:
            raise RPCClientError(f"Failed to parse response: {e}") from e
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def _create_connection(self) -> socket.socket:
        """Create new connection to RPC server.

        Returns:
            Socket connection

        Raises:
            ConnectionError: If connection fails
        """
        try:
            if not Path(self.socket_path).exists():
                raise ConnectionError(f"Socket file does not exist: {self.socket_path}")

            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self.socket_path)
            return sock
        except socket.error as e:
            raise ConnectionError(f"Failed to connect to socket: {e}") from e

    def _send_data(self, sock: socket.socket, data: str) -> None:
        """Send data to socket.

        Args:
            sock: Socket connection
            data: Data to send (string)

        Raises:
            ConnectionError: If send fails
        """
        try:
            data_bytes = data.encode("utf-8")
            length = len(data_bytes)
            # Send length prefix (4 bytes, big-endian)
            sock.sendall(struct.pack("!I", length))
            # Send data
            sock.sendall(data_bytes)
        except socket.error as e:
            raise ConnectionError(f"Failed to send data: {e}") from e

    def _receive_data(self, sock: socket.socket) -> Optional[bytes]:
        """Receive data from socket.

        Args:
            sock: Socket connection

        Returns:
            Received data or None if error

        Raises:
            ConnectionError: If receive fails
        """
        try:
            # Read length prefix (4 bytes)
            length_data = sock.recv(4)
            if len(length_data) != 4:
                raise ConnectionError("Failed to receive length prefix")

            length = struct.unpack("!I", length_data)[0]
            if length > 10 * 1024 * 1024:  # 10 MB limit
                raise ConnectionError(f"Response too large: {length} bytes")

            # Read data
            data = b""
            while len(data) < length:
                chunk = sock.recv(length - len(data))
                if not chunk:
                    raise ConnectionError("Connection closed while receiving data")
                data += chunk

            return data
        except socket.error as e:
            raise ConnectionError(f"Failed to receive data: {e}") from e

    def health_check(self) -> bool:
        """Check if RPC server is healthy.

        Returns:
            True if server is healthy, False otherwise
        """
        if not self.is_connected():
            return False

        try:
            # Try a simple call (if server supports health check method)
            # For now, just check if socket exists and is accessible
            return Path(self.socket_path).exists()
        except Exception:
            return False
