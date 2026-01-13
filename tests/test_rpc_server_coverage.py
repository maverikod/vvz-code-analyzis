"""
Additional tests for RPC server to improve coverage.

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
from unittest.mock import Mock, patch

from code_analysis.core.database_driver_pkg.rpc_server import RPCServer
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_protocol import RPCRequest
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


class TestRPCServerCoverage:
    """Test RPC server for coverage."""

    def test_start_server_error_handling(self, rpc_server, socket_path):
        """Test server start error handling."""
        # Create invalid socket path (directory instead of file)
        invalid_path = str(Path(socket_path).parent)
        rpc_server.socket_path = invalid_path

        with pytest.raises(RPCServerError):
            rpc_server.start()

    def test_server_accept_error(self, rpc_server):
        """Test server accept error handling."""
        # Start server in background
        server_thread = threading.Thread(target=rpc_server.start, daemon=True)
        server_thread.start()
        time.sleep(0.1)

        # Stop server to trigger accept error
        rpc_server.stop()
        time.sleep(0.1)

    def test_receive_data_partial_read(self, rpc_server):
        """Test receiving data with partial reads."""
        mock_sock = Mock()
        mock_sock.recv.side_effect = [
            struct.pack("!I", 10),  # Length
            b"12345",  # First chunk
            b"67890",  # Second chunk
        ]
        result = rpc_server._receive_data(mock_sock)
        assert result == b"1234567890"

    def test_receive_data_connection_closed(self, rpc_server):
        """Test receiving data when connection is closed."""
        mock_sock = Mock()
        mock_sock.recv.return_value = b""  # Connection closed
        result = rpc_server._receive_data(mock_sock)
        assert result is None

    def test_receive_data_exception(self, rpc_server):
        """Test receiving data with exception."""
        mock_sock = Mock()
        mock_sock.recv.side_effect = Exception("Network error")
        result = rpc_server._receive_data(mock_sock)
        assert result is None

    def test_send_data_exception(self, rpc_server):
        """Test sending data with exception."""
        mock_sock = Mock()
        mock_sock.sendall.side_effect = Exception("Send error")
        # Should not raise, just log
        rpc_server._send_data(mock_sock, '{"test": "data"}')
