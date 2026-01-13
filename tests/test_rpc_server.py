"""
Tests for RPC server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import socket
import struct
import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock

from code_analysis.core.database_driver_pkg.rpc_server import RPCServer
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_protocol import (
    RPCRequest,
    RPCResponse,
    ErrorCode,
)
from code_analysis.core.database_driver_pkg.drivers.base import BaseDatabaseDriver


@pytest.fixture
def mock_driver(tmp_path):
    """Create mock driver."""
    driver = Mock(spec=BaseDatabaseDriver)
    return driver


@pytest.fixture
def request_queue():
    """Create request queue."""
    return RequestQueue(max_size=100)


@pytest.fixture
def socket_path(tmp_path):
    """Create temporary socket path."""
    return str(tmp_path / "test.sock")


@pytest.fixture
def rpc_server(mock_driver, request_queue, socket_path):
    """Create RPC server instance."""
    server = RPCServer(mock_driver, request_queue, socket_path)
    return server


class TestRPCServerBasic:
    """Test basic RPC server functionality."""

    def test_create_server(self, rpc_server, mock_driver, request_queue, socket_path):
        """Test creating RPC server."""
        assert rpc_server.driver == mock_driver
        assert rpc_server.request_queue == request_queue
        assert rpc_server.socket_path == socket_path
        assert not rpc_server.running

    def test_start_stop(self, rpc_server):
        """Test starting and stopping server."""
        # Start server in background thread
        server_thread = threading.Thread(target=rpc_server.start, daemon=True)
        server_thread.start()

        # Wait for server to start
        time.sleep(0.1)
        assert rpc_server.running

        # Stop server
        rpc_server.stop()
        time.sleep(0.1)
        assert not rpc_server.running

    def test_process_request_unknown_method(self, rpc_server):
        """Test processing unknown method."""
        request = RPCRequest(method="unknown_method", params={}, request_id="123")
        response = rpc_server._process_request(request)
        assert response.is_error()
        assert response.error.code == ErrorCode.INVALID_REQUEST


class TestRPCServerTableOperations:
    """Test RPC server table operations."""

    def test_process_create_table(self, rpc_server, mock_driver):
        """Test processing create_table request."""
        mock_driver.create_table.return_value = True
        request = RPCRequest(
            method="create_table",
            params={"schema": {"name": "users", "columns": []}},
            request_id="123",
        )
        response = rpc_server._process_request(request)
        assert response.is_success()
        assert response.result == {"success": True}

    def test_process_insert(self, rpc_server, mock_driver):
        """Test processing insert request."""
        mock_driver.insert.return_value = 456
        request = RPCRequest(
            method="insert",
            params={"table_name": "users", "data": {"name": "John"}},
            request_id="123",
        )
        response = rpc_server._process_request(request)
        assert response.is_success()
        assert response.result == {"row_id": 456}

    def test_process_select(self, rpc_server, mock_driver):
        """Test processing select request."""
        mock_driver.select.return_value = [{"id": 1, "name": "John"}]
        request = RPCRequest(
            method="select",
            params={"table_name": "users", "where": {"id": 1}},
            request_id="123",
        )
        response = rpc_server._process_request(request)
        assert response.is_success()
        assert "data" in response.result


class TestRPCServerSocketCommunication:
    """Test RPC server socket communication."""

    def _send_rpc_request(self, sock_path: str, request: dict) -> dict:
        """Helper to send RPC request and get response."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(sock_path)
            # Serialize request
            data = json.dumps(request).encode("utf-8")
            # Send length prefix
            sock.sendall(struct.pack("!I", len(data)))
            # Send data
            sock.sendall(data)

            # Receive response
            length_data = sock.recv(4)
            length = struct.unpack("!I", length_data)[0]
            response_data = b""
            while len(response_data) < length:
                chunk = sock.recv(length - len(response_data))
                if not chunk:
                    break
                response_data += chunk

            return json.loads(response_data.decode("utf-8"))
        finally:
            sock.close()

    def test_handle_client_request(self, mock_driver, request_queue, socket_path):
        """Test handling client request via socket."""
        mock_driver.insert.return_value = 789
        server = RPCServer(mock_driver, request_queue, socket_path)

        # Start server in background
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()

        # Wait for server to start
        time.sleep(0.2)

        try:
            # Send request
            request = {
                "jsonrpc": "2.0",
                "method": "insert",
                "params": {"table_name": "users", "data": {"name": "Test"}},
                "id": "test_123",
            }

            response = self._send_rpc_request(socket_path, request)

            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            assert response["result"]["row_id"] == 789
            assert response["id"] == "test_123"
        finally:
            server.stop()
            time.sleep(0.1)

    def test_handle_invalid_request(self, mock_driver, request_queue, socket_path):
        """Test handling invalid request."""
        server = RPCServer(mock_driver, request_queue, socket_path)
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)

        try:
            # Send invalid JSON
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(socket_path)
            invalid_data = b"invalid json"
            sock.sendall(struct.pack("!I", len(invalid_data)))
            sock.sendall(invalid_data)

            # Should receive error response
            length_data = sock.recv(4)
            length = struct.unpack("!I", length_data)[0]
            response_data = sock.recv(length)
            response = json.loads(response_data.decode("utf-8"))

            assert "error" in response
            sock.close()
        finally:
            server.stop()
            time.sleep(0.1)
