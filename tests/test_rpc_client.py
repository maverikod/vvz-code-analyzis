"""
Tests for RPC client.

Tests RPC client functionality including connection, request/response handling,
connection pooling, retry logic, and error handling.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import socket
import struct
import threading
import time
from pathlib import Path

import pytest

from code_analysis.core.database_client.exceptions import (
    ConnectionError,
    RPCResponseError,
    TimeoutError,
)
from code_analysis.core.database_client.rpc_client import RPCClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_client.protocol import RPCResponse
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer


class TestRPCClient:
    """Test RPC client functionality."""

    @pytest.fixture
    def rpc_server(self, tmp_path):
        """Create RPC server for testing."""
        db_path = tmp_path / "test.db"
        socket_path = str(tmp_path / "test.sock")

        # Create table first
        driver = create_driver("sqlite", {"path": str(db_path)})
        schema = {
            "name": "test_table",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)
        driver.disconnect()

        # Start RPC server
        request_queue = RequestQueue()
        driver = create_driver("sqlite", {"path": str(db_path)})
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)  # Wait for server to start

        yield server, socket_path

        # Cleanup
        server.stop()
        driver.disconnect()

    def test_connect(self, tmp_path):
        """Test RPC client connection."""
        socket_path = str(tmp_path / "test.sock")

        # Create socket file (simulate server)
        Path(socket_path).touch()

        client = RPCClient(socket_path)
        client.connect()
        assert client.is_connected()
        client.disconnect()

    def test_disconnect(self, tmp_path):
        """Test RPC client disconnection."""
        socket_path = str(tmp_path / "test.sock")
        Path(socket_path).touch()

        client = RPCClient(socket_path)
        client.connect()
        client.disconnect()
        assert not client.is_connected()

    def test_call_success(self, rpc_server):
        """Test successful RPC call."""
        _, socket_path = rpc_server

        client = RPCClient(socket_path)
        client.connect()

        try:
            response = client.call(
                "select",
                {
                    "table_name": "test_table",
                    "where": None,
                    "columns": None,
                    "limit": None,
                    "offset": None,
                    "order_by": None,
                },
            )
            assert response.is_success()
            assert response.result is not None
        finally:
            client.disconnect()

    def test_call_with_error(self, rpc_server):
        """Test RPC call with error response."""
        _, socket_path = rpc_server

        client = RPCClient(socket_path)
        client.connect()

        try:
            # Call non-existent method
            with pytest.raises(RPCResponseError) as exc_info:
                client.call("nonexistent_method", {})
            assert exc_info.value.error_code is not None
        finally:
            client.disconnect()

    def test_connection_error(self):
        """Test connection error handling."""
        socket_path = "/nonexistent/socket.sock"

        client = RPCClient(socket_path)
        with pytest.raises(ConnectionError):
            client.call("test_method", {})

    def test_timeout(self, tmp_path):
        """Test timeout handling."""
        socket_path = str(tmp_path / "test.sock")

        # Create a slow server that doesn't respond
        def slow_server():
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.bind(socket_path)
                sock.listen(1)
                conn, _ = sock.accept()
                # Don't respond, just wait
                time.sleep(10)
                conn.close()
            finally:
                sock.close()

        server_thread = threading.Thread(target=slow_server, daemon=True)
        server_thread.start()
        time.sleep(0.1)

        client = RPCClient(socket_path, timeout=0.5)
        client.connect()

        try:
            with pytest.raises(TimeoutError):
                client.call("test_method", {})
        finally:
            client.disconnect()

    def test_retry_logic(self, tmp_path):
        """Test retry logic on connection failures."""
        socket_path = str(tmp_path / "test.sock")

        # Server that fails first time, then succeeds
        attempt_count = [0]

        def flaky_server():
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.bind(socket_path)
                sock.listen(1)
                while True:
                    conn, _ = sock.accept()
                    attempt_count[0] += 1
                    if attempt_count[0] < 2:
                        # Close connection immediately (simulate failure)
                        conn.close()
                    else:
                        # Process request normally
                        try:
                            # Read request
                            length_data = conn.recv(4)
                            if len(length_data) == 4:
                                length = struct.unpack("!I", length_data)[0]
                                data = b""
                                while len(data) < length:
                                    chunk = conn.recv(length - len(data))
                                    if not chunk:
                                        break
                                    data += chunk

                                # Send success response
                                response = RPCResponse(
                                    result={"success": True}, request_id="test"
                                )
                                response_json = json.dumps(response.to_dict())
                                response_bytes = response_json.encode("utf-8")
                                conn.sendall(struct.pack("!I", len(response_bytes)))
                                conn.sendall(response_bytes)
                        finally:
                            conn.close()
            finally:
                sock.close()

        server_thread = threading.Thread(target=flaky_server, daemon=True)
        server_thread.start()
        time.sleep(0.2)

        client = RPCClient(socket_path, max_retries=3, retry_delay=0.1)
        client.connect()

        try:
            response = client.call("test_method", {})
            assert response.is_success()
            assert attempt_count[0] >= 2  # Should have retried
        finally:
            client.disconnect()

    def test_health_check(self, rpc_server):
        """Test health check."""
        _, socket_path = rpc_server

        client = RPCClient(socket_path)
        assert client.health_check()  # Socket exists

        client.connect()
        assert client.health_check()
        client.disconnect()

    def test_health_check_no_socket(self):
        """Test health check when socket doesn't exist."""
        socket_path = "/nonexistent/socket.sock"
        client = RPCClient(socket_path)
        assert not client.health_check()

    def test_connection_pooling(self, rpc_server):
        """Test connection pooling."""
        _, socket_path = rpc_server

        client = RPCClient(socket_path, pool_size=3)
        client.connect()

        try:
            # Make multiple concurrent calls
            import concurrent.futures

            def make_call():
                return client.call(
                    "select",
                    {
                        "table_name": "test_table",
                        "where": None,
                        "columns": None,
                        "limit": None,
                        "offset": None,
                        "order_by": None,
                    },
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(make_call) for _ in range(10)]
                results = [f.result() for f in futures]

            # All calls should succeed
            assert all(r.is_success() for r in results)
        finally:
            client.disconnect()

    def test_insert_select_operations(self, rpc_server):
        """Test insert and select operations through RPC client."""
        _, socket_path = rpc_server

        client = RPCClient(socket_path)
        client.connect()

        try:
            # Insert row
            insert_response = client.call(
                "insert",
                {"table_name": "test_table", "data": {"name": "Test User"}},
            )
            assert insert_response.is_success()
            row_id = insert_response.result.get("data", {}).get("row_id")
            assert row_id is not None

            # Select rows
            select_response = client.call(
                "select",
                {
                    "table_name": "test_table",
                    "where": None,
                    "columns": None,
                    "limit": None,
                    "offset": None,
                    "order_by": None,
                },
            )
            assert select_response.is_success()
            rows = select_response.result.get("data", {}).get("data", [])
            assert len(rows) == 1
            assert rows[0]["name"] == "Test User"
        finally:
            client.disconnect()
