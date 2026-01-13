"""
Edge case tests for RPC server.

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
from unittest.mock import Mock, MagicMock, patch

from code_analysis.core.database_driver_pkg.rpc_server import RPCServer
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_protocol import RPCRequest, ErrorCode
from code_analysis.core.database_driver_pkg.exceptions import RPCServerError


@pytest.fixture
def mock_driver():
    """Create mock driver."""
    return Mock()


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
    return RPCServer(mock_driver, request_queue, socket_path)


class TestRPCServerEdgeCases:
    """Test edge cases for RPC server."""

    def test_start_already_running(self, rpc_server):
        """Test starting server that is already running."""
        # Start server in background
        server_thread = threading.Thread(target=rpc_server.start, daemon=True)
        server_thread.start()
        time.sleep(0.1)

        # Try to start again
        with pytest.raises(RPCServerError, match="already running"):
            rpc_server.start()

        rpc_server.stop()
        time.sleep(0.1)

    def test_stop_not_running(self, rpc_server):
        """Test stopping server that is not running."""
        # Should not raise exception
        rpc_server.stop()

    def test_receive_data_empty(self, rpc_server):
        """Test receiving empty data."""
        # Create a mock socket that returns empty data
        mock_sock = Mock()
        mock_sock.recv.return_value = b""
        result = rpc_server._receive_data(mock_sock)
        assert result is None

    def test_receive_data_too_large(self, rpc_server):
        """Test receiving data that is too large."""
        mock_sock = Mock()
        mock_sock.recv.side_effect = [
            struct.pack("!I", 20 * 1024 * 1024),  # 20 MB - too large
        ]
        result = rpc_server._receive_data(mock_sock)
        assert result is None

    def test_receive_data_incomplete_length(self, rpc_server):
        """Test receiving incomplete length prefix."""
        mock_sock = Mock()
        mock_sock.recv.return_value = b"\x00\x00"  # Only 2 bytes instead of 4
        result = rpc_server._receive_data(mock_sock)
        assert result is None

    def test_send_data_error(self, rpc_server):
        """Test sending data with error."""
        mock_sock = Mock()
        mock_sock.sendall.side_effect = Exception("Send error")
        # Should not raise, just log error
        rpc_server._send_data(mock_sock, '{"test": "data"}')

    def test_process_request_handler_exception(self, rpc_server, mock_driver):
        """Test processing request when handler raises exception."""
        mock_driver.insert.side_effect = Exception("Database error")
        request = RPCRequest(
            method="insert",
            params={"table_name": "users", "data": {"name": "John"}},
            request_id="123",
        )
        response = rpc_server._process_request(request)
        assert response.is_error()
        assert response.error.code == ErrorCode.INTERNAL_ERROR

    def test_handle_client_no_data(self, rpc_server):
        """Test handling client with no data."""
        mock_sock = Mock()
        mock_sock.recv.return_value = b""
        # Should return early without error
        rpc_server._handle_client(mock_sock)

    def test_handle_client_invalid_json(self, rpc_server):
        """Test handling client with invalid JSON."""
        mock_sock = Mock()
        # Mock _receive_data to return invalid JSON
        with patch.object(rpc_server, "_receive_data", return_value=b"invalid json"):
            with patch.object(rpc_server, "_send_data") as mock_send:
                rpc_server._handle_client(mock_sock)
                # Should send error response
                assert mock_send.called

    def test_handle_client_queue_error(self, rpc_server, request_queue):
        """Test handling client when queue is full."""
        # Fill queue
        for i in range(100):
            request_queue.enqueue(f"req_{i}", {"data": i})

        mock_sock = Mock()
        request_data = json.dumps({
            "jsonrpc": "2.0",
            "method": "insert",
            "params": {"table_name": "users", "data": {"name": "John"}},
        }).encode("utf-8")

        with patch.object(rpc_server, "_receive_data", return_value=request_data):
            with patch.object(rpc_server, "_send_data") as mock_send:
                rpc_server._handle_client(mock_sock)
                # Should send error response
                assert mock_send.called
