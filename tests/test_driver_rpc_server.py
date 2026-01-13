"""
Tests for database driver RPC server.

Tests RPC server functionality with BaseRequest and BaseResult classes.

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

from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    UpdateRequest,
)
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_protocol import RPCRequest
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer


class TestDriverRPCServer:
    """Test database driver RPC server with Request/Result classes."""

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

    def test_insert_with_request_class(self, tmp_path):
        """Test insert operation using InsertRequest class."""
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
        time.sleep(0.2)

        try:
            # Send insert request
            request = {
                "jsonrpc": "2.0",
                "method": "insert",
                "params": {
                    "table_name": "test_table",
                    "data": {"name": "Test User"},
                },
                "id": "test_1",
            }

            response = self._send_rpc_request(socket_path, request)

            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            assert response["result"]["success"] is True
            assert "row_id" in response["result"]["data"]
            assert response["result"]["data"]["row_id"] > 0
        finally:
            server.stop()
            driver.disconnect()
            time.sleep(0.1)

    def test_select_with_request_class(self, tmp_path):
        """Test select operation using SelectRequest class."""
        db_path = tmp_path / "test.db"
        socket_path = str(tmp_path / "test.sock")

        # Create table and insert data
        driver = create_driver("sqlite", {"path": str(db_path)})
        schema = {
            "name": "test_table",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)
        driver.insert("test_table", {"name": "User 1"})
        driver.insert("test_table", {"name": "User 2"})
        driver.disconnect()

        # Start RPC server
        request_queue = RequestQueue()
        driver = create_driver("sqlite", {"path": str(db_path)})
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)

        try:
            # Send select request
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
                "id": "test_2",
            }

            response = self._send_rpc_request(socket_path, request)

            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            assert response["result"]["success"] is True
            assert "data" in response["result"]
            assert len(response["result"]["data"]) == 2
        finally:
            server.stop()
            driver.disconnect()
            time.sleep(0.1)

    def test_update_with_request_class(self, tmp_path):
        """Test update operation using UpdateRequest class."""
        db_path = tmp_path / "test.db"
        socket_path = str(tmp_path / "test.sock")

        # Create table and insert data
        driver = create_driver("sqlite", {"path": str(db_path)})
        schema = {
            "name": "test_table",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)
        driver.insert("test_table", {"name": "Old Name"})
        driver.disconnect()

        # Start RPC server
        request_queue = RequestQueue()
        driver = create_driver("sqlite", {"path": str(db_path)})
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)

        try:
            # Send update request
            request = {
                "jsonrpc": "2.0",
                "method": "update",
                "params": {
                    "table_name": "test_table",
                    "where": {"name": "Old Name"},
                    "data": {"name": "New Name"},
                },
                "id": "test_3",
            }

            response = self._send_rpc_request(socket_path, request)

            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            assert response["result"]["success"] is True
            assert "affected_rows" in response["result"]["data"]
            assert response["result"]["data"]["affected_rows"] == 1
        finally:
            server.stop()
            driver.disconnect()
            time.sleep(0.1)

    def test_delete_with_request_class(self, tmp_path):
        """Test delete operation using DeleteRequest class."""
        db_path = tmp_path / "test.db"
        socket_path = str(tmp_path / "test.sock")

        # Create table and insert data
        driver = create_driver("sqlite", {"path": str(db_path)})
        schema = {
            "name": "test_table",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)
        driver.insert("test_table", {"name": "To Delete"})
        driver.disconnect()

        # Start RPC server
        request_queue = RequestQueue()
        driver = create_driver("sqlite", {"path": str(db_path)})
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)

        try:
            # Send delete request
            request = {
                "jsonrpc": "2.0",
                "method": "delete",
                "params": {
                    "table_name": "test_table",
                    "where": {"name": "To Delete"},
                },
                "id": "test_4",
            }

            response = self._send_rpc_request(socket_path, request)

            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            assert response["result"]["success"] is True
            assert "affected_rows" in response["result"]["data"]
            assert response["result"]["data"]["affected_rows"] == 1
        finally:
            server.stop()
            driver.disconnect()
            time.sleep(0.1)

    def test_invalid_request_validation(self, tmp_path):
        """Test that invalid requests return ErrorResult."""
        db_path = tmp_path / "test.db"
        socket_path = str(tmp_path / "test.sock")

        # Start RPC server
        request_queue = RequestQueue()
        driver = create_driver("sqlite", {"path": str(db_path)})
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)

        try:
            # Send invalid insert request (missing data)
            request = {
                "jsonrpc": "2.0",
                "method": "insert",
                "params": {
                    "table_name": "test_table",
                    # Missing "data" field
                },
                "id": "test_5",
            }

            response = self._send_rpc_request(socket_path, request)

            assert response["jsonrpc"] == "2.0"
            assert "error" in response
            assert response["error"]["code"] > 0
        finally:
            server.stop()
            driver.disconnect()
            time.sleep(0.1)

    def test_all_rpc_methods(self, tmp_path):
        """Test all RPC methods work correctly."""
        db_path = tmp_path / "test.db"
        socket_path = str(tmp_path / "test.sock")

        # Start RPC server
        request_queue = RequestQueue()
        driver = create_driver("sqlite", {"path": str(db_path)})
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)

        try:
            # Test create_table
            request = {
                "jsonrpc": "2.0",
                "method": "create_table",
                "params": {
                    "schema": {
                        "name": "users",
                        "columns": [
                            {"name": "id", "type": "INTEGER", "primary_key": True},
                            {"name": "name", "type": "TEXT"},
                        ],
                    }
                },
                "id": "test_create",
            }
            response = self._send_rpc_request(socket_path, request)
            assert response["jsonrpc"] == "2.0"
            assert "result" in response

            # Test get_table_info
            request = {
                "jsonrpc": "2.0",
                "method": "get_table_info",
                "params": {"table_name": "users"},
                "id": "test_info",
            }
            response = self._send_rpc_request(socket_path, request)
            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            assert "data" in response["result"]

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
            assert "transaction_id" in response["result"]["data"]

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
            time.sleep(0.1)
