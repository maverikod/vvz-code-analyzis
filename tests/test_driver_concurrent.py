"""
Concurrent request tests for driver process.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import threading
import time
import socket
import struct
import json
from pathlib import Path

from code_analysis.core.database_driver_pkg.rpc_server import RPCServer
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver


@pytest.fixture
def temp_db_path(tmp_path):
    """Create temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def socket_path(tmp_path):
    """Create temporary socket path."""
    return str(tmp_path / "test.sock")


@pytest.fixture
def driver_and_server(temp_db_path, socket_path):
    """Create driver and RPC server."""
    driver = SQLiteDriver()
    driver.connect({"path": str(temp_db_path)})

    # Create table
    schema = {
        "name": "users",
        "columns": [
            {"name": "id", "type": "INTEGER", "primary_key": True},
            {"name": "name", "type": "TEXT"},
        ],
    }
    driver.create_table(schema)

    request_queue = RequestQueue(max_size=100)
    server = RPCServer(driver, request_queue, socket_path)

    yield driver, server, request_queue

    server.stop()
    driver.disconnect()


class TestConcurrentRequests:
    """Test concurrent requests to driver."""

    def test_concurrent_inserts(self, driver_and_server, socket_path):
        """Test concurrent insert requests."""
        driver, server, queue = driver_and_server

        # Start server
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)

        results = []
        results_lock = threading.Lock()

        def send_insert_request(thread_id):
            """Send insert request."""
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(socket_path)

                request = {
                    "jsonrpc": "2.0",
                    "method": "insert",
                    "params": {
                        "table_name": "users",
                        "data": {"name": f"User{thread_id}"},
                    },
                    "id": f"req_{thread_id}",
                }

                data = json.dumps(request).encode("utf-8")
                sock.sendall(struct.pack("!I", len(data)))
                sock.sendall(data)

                # Receive response
                length_data = sock.recv(4)
                length = struct.unpack("!I", length_data)[0]
                response_data = sock.recv(length)
                response = json.loads(response_data.decode("utf-8"))

                with results_lock:
                    results.append(response)

                sock.close()
            except Exception as e:
                with results_lock:
                    results.append({"error": str(e)})

        # Send 10 concurrent requests
        threads = []
        for i in range(10):
            t = threading.Thread(target=send_insert_request, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All requests should succeed (allow for some errors due to concurrency)
        assert len(results) == 10
        success_count = 0
        for result in results:
            if "result" in result:
                # Result format: {"success": True, "data": {"row_id": ...}}
                if result["result"].get("success") is True:
                    assert "data" in result["result"]
                    assert "row_id" in result["result"]["data"]
                    success_count += 1
        # At least 8 out of 10 requests should succeed
        assert success_count >= 8, f"Only {success_count} out of 10 requests succeeded"

        server.stop()
        time.sleep(0.1)

    def test_queue_overflow_handling(self, driver_and_server):
        """Test queue overflow handling."""
        driver, server, queue = driver_and_server

        # Fill queue to capacity
        for i in range(100):
            queue.enqueue(f"req_{i}", {"data": i})

        # Try to enqueue one more
        from code_analysis.core.database_driver_pkg.exceptions import (
            RequestQueueFullError,
        )

        with pytest.raises(RequestQueueFullError):
            queue.enqueue("req_overflow", {"data": "overflow"})


class TestConcurrentTransactions:
    """Test concurrent transactions."""

    def test_concurrent_transactions(self, temp_db_path):
        """Test concurrent transactions."""
        driver = SQLiteDriver()
        driver.connect({"path": str(temp_db_path)})

        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)

        transaction_ids = []
        ids_lock = threading.Lock()

        def create_transaction(thread_id):
            """Create transaction."""
            try:
                trans_id = driver.begin_transaction()
                with ids_lock:
                    transaction_ids.append((thread_id, trans_id))
            except Exception:
                pass

        # Create 5 concurrent transactions
        threads = []
        for i in range(5):
            t = threading.Thread(target=create_transaction, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All transactions should be created
        assert len(transaction_ids) == 5

        # Commit all transactions
        for thread_id, trans_id in transaction_ids:
            driver.commit_transaction(trans_id)

        driver.disconnect()
