"""
Integration tests for database driver with real running server.

Tests RPC communication through real server, all RPC methods, concurrent requests,
and error scenarios.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path

import pytest

from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_protocol import RPCRequest
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer
from code_analysis.core.database_driver_pkg.runner import run_database_driver


class TestDriverIntegrationRealServer:
    """Test database driver with real running server."""

    def _send_rpc_request(self, sock_path: str, request: dict) -> dict:
        """Helper to send RPC request and get response.

        Args:
            sock_path: Path to Unix socket
            request: RPC request dictionary

        Returns:
            Response dictionary
        """
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
            if len(length_data) != 4:
                raise ValueError("Invalid response length")
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

    def test_rpc_server_all_methods(self, tmp_path):
        """Test all RPC methods through real server."""
        db_path = tmp_path / "test.db"
        socket_path = str(tmp_path / "test.sock")

        # Create table first
        driver = create_driver("sqlite", {"path": str(db_path)})
        schema = {
            "name": "test_table",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
                {"name": "value", "type": "INTEGER"},
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
        time.sleep(0.3)  # Wait for server to start

        try:
            # Test insert
            request = {
                "jsonrpc": "2.0",
                "method": "insert",
                "params": {
                    "table_name": "test_table",
                    "data": {"name": "Test", "value": 42},
                },
                "id": "test_insert",
            }
            response = self._send_rpc_request(socket_path, request)
            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            assert "row_id" in response["result"].get("data", {})

            # Test select
            request = {
                "jsonrpc": "2.0",
                "method": "select",
                "params": {
                    "table_name": "test_table",
                    "where": None,
                    "columns": None,
                    "limit": None,
                    "offset": None,
                    "order_by": None,
                },
                "id": "test_select",
            }
            response = self._send_rpc_request(socket_path, request)
            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            assert "data" in response["result"]

            # Test update
            request = {
                "jsonrpc": "2.0",
                "method": "update",
                "params": {
                    "table_name": "test_table",
                    "where": {"name": "Test"},
                    "data": {"value": 100},
                },
                "id": "test_update",
            }
            response = self._send_rpc_request(socket_path, request)
            assert response["jsonrpc"] == "2.0"
            assert "result" in response

            # Test get_table_info
            request = {
                "jsonrpc": "2.0",
                "method": "get_table_info",
                "params": {"table_name": "test_table"},
                "id": "test_info",
            }
            response = self._send_rpc_request(socket_path, request)
            assert response["jsonrpc"] == "2.0"
            assert "result" in response

            # Test begin_transaction
            request = {
                "jsonrpc": "2.0",
                "method": "begin_transaction",
                "params": {},
                "id": "test_begin",
            }
            response = self._send_rpc_request(socket_path, request)
            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            transaction_id = response["result"]["data"]["transaction_id"]

            # Test commit_transaction
            request = {
                "jsonrpc": "2.0",
                "method": "commit_transaction",
                "params": {"transaction_id": transaction_id},
                "id": "test_commit",
            }
            response = self._send_rpc_request(socket_path, request)
            assert response["jsonrpc"] == "2.0"
            assert "result" in response
        finally:
            server.stop()
            driver.disconnect()

    def test_rpc_server_concurrent_requests(self, tmp_path):
        """Test concurrent requests through real server."""
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
        time.sleep(0.3)

        try:
            import concurrent.futures

            def make_request(i):
                request = {
                    "jsonrpc": "2.0",
                    "method": "insert",
                    "params": {
                        "table_name": "test_table",
                        "data": {"name": f"Test_{i}"},
                    },
                    "id": f"req_{i}",
                }
                return self._send_rpc_request(socket_path, request)

            # Make 20 concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(make_request, i) for i in range(20)]
                results = [f.result() for f in futures]

            # All requests should succeed
            assert all("result" in r for r in results)
            assert all("error" not in r for r in results)

            # Verify data was inserted
            request = {
                "jsonrpc": "2.0",
                "method": "select",
                "params": {
                    "table_name": "test_table",
                    "where": None,
                    "columns": None,
                    "limit": None,
                    "offset": None,
                    "order_by": None,
                },
                "id": "test_count",
            }
            response = self._send_rpc_request(socket_path, request)
            rows = response["result"].get("data", {}).get("data", [])
            assert len(rows) == 20
        finally:
            server.stop()
            driver.disconnect()

    def test_rpc_server_error_scenarios(self, tmp_path):
        """Test error scenarios with real server."""
        db_path = tmp_path / "test.db"
        socket_path = str(tmp_path / "test.sock")

        # Start RPC server
        request_queue = RequestQueue()
        driver = create_driver("sqlite", {"path": str(db_path)})
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        try:
            # Test invalid method
            request = {
                "jsonrpc": "2.0",
                "method": "nonexistent_method",
                "params": {},
                "id": "test_invalid",
            }
            response = self._send_rpc_request(socket_path, request)
            assert response["jsonrpc"] == "2.0"
            assert "error" in response
            assert response["error"]["code"] != 0

            # Test invalid request format
            request = {"invalid": "request"}
            response = self._send_rpc_request(socket_path, request)
            assert "error" in response

            # Test insert into non-existent table
            request = {
                "jsonrpc": "2.0",
                "method": "insert",
                "params": {
                    "table_name": "nonexistent_table",
                    "data": {"name": "Test"},
                },
                "id": "test_error",
            }
            response = self._send_rpc_request(socket_path, request)
            assert response["jsonrpc"] == "2.0"
            assert "error" in response
        finally:
            server.stop()
            driver.disconnect()
