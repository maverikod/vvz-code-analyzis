"""
Tests for database driver process.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import os
import signal
import subprocess
import time
import socket
import struct
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from code_analysis.core.database_driver_pkg.runner import run_database_driver
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer


class TestDriverProcess:
    """Test driver process functionality."""

    def test_create_driver_via_factory(self, tmp_path):
        """Test creating driver via factory."""
        db_path = tmp_path / "test.db"
        config = {"path": str(db_path)}
        driver = create_driver("sqlite", config)
        assert driver is not None
        assert driver.conn is not None
        driver.disconnect()

    def test_driver_process_initialization(self, tmp_path):
        """Test driver process initialization components."""
        db_path = tmp_path / "test.db"
        socket_path = str(tmp_path / "test.sock")

        # Create components
        request_queue = RequestQueue(max_size=100)
        driver = create_driver("sqlite", {"path": str(db_path)})
        rpc_server = RPCServer(driver, request_queue, socket_path)

        assert request_queue is not None
        assert driver is not None
        assert rpc_server is not None

        # Cleanup
        driver.disconnect()

    def test_request_queue_integration(self, tmp_path):
        """Test request queue with driver."""
        db_path = tmp_path / "test.db"
        driver = create_driver("sqlite", {"path": str(db_path)})

        # Create table
        schema = {
            "name": "test_table",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)

        # Insert data
        row_id = driver.insert("test_table", {"name": "Test"})
        assert row_id > 0

        # Select data
        rows = driver.select("test_table")
        assert len(rows) == 1
        assert rows[0]["name"] == "Test"

        driver.disconnect()

    def test_rpc_server_with_driver(self, tmp_path):
        """Test RPC server with real driver."""
        db_path = tmp_path / "test.db"
        socket_path = str(tmp_path / "test.sock")

        request_queue = RequestQueue()
        driver = create_driver("sqlite", {"path": str(db_path)})
        server = RPCServer(driver, request_queue, socket_path)

        # Start server in background
        server_thread = None
        try:
            server_thread = __import__("threading").Thread(
                target=server.start, daemon=True
            )
            server_thread.start()
            time.sleep(0.2)

            # Test that server is running
            assert server.running

            # Send test request via socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(socket_path)

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
                "id": "test_1",
            }

            data = json.dumps(request).encode("utf-8")
            sock.sendall(struct.pack("!I", len(data)))
            sock.sendall(data)

            # Receive response
            length_data = sock.recv(4)
            length = struct.unpack("!I", length_data)[0]
            response_data = sock.recv(length)
            response = json.loads(response_data.decode("utf-8"))

            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            assert response["result"]["success"] is True
            sock.close()
        finally:
            server.stop()
            driver.disconnect()
            time.sleep(0.1)


class TestDriverProcessErrorHandling:
    """Test error handling in driver process."""

    def test_driver_connection_error(self):
        """Test driver connection error handling."""
        with pytest.raises(Exception):  # DriverConnectionError
            create_driver("sqlite", {})  # Missing path

    def test_driver_not_found_error(self):
        """Test driver not found error."""
        from code_analysis.core.database_driver_pkg.exceptions import (
            DriverNotFoundError,
        )

        with pytest.raises(DriverNotFoundError):
            create_driver("unknown_driver", {})

    def test_request_queue_full(self):
        """Test request queue full error."""
        from code_analysis.core.database_driver_pkg.exceptions import (
            RequestQueueFullError,
        )

        queue = RequestQueue(max_size=2)
        queue.enqueue("req1", {"data": 1})
        queue.enqueue("req2", {"data": 2})

        with pytest.raises(RequestQueueFullError):
            queue.enqueue("req3", {"data": 3})


class TestDriverProcessTransactions:
    """Test transactions in driver process."""

    def test_transaction_operations(self, tmp_path):
        """Test transaction begin, commit, rollback."""
        db_path = tmp_path / "test.db"
        driver = create_driver("sqlite", {"path": str(db_path)})

        # Create table
        schema = {
            "name": "test_table",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)

        # Begin transaction
        transaction_id = driver.begin_transaction()
        assert transaction_id is not None

        # Commit transaction
        result = driver.commit_transaction(transaction_id)
        assert result is True

        # Test rollback
        transaction_id = driver.begin_transaction()
        result = driver.rollback_transaction(transaction_id)
        assert result is True

        driver.disconnect()
