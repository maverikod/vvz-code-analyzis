"""
Integration tests for database client with real running server.

Tests RPC communication through real server, all client methods, connection pooling,
and retry logic.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import threading
import time
from pathlib import Path

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer


class TestDatabaseClientIntegrationRealServer:
    """Test database client with real running server."""

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

        yield server, socket_path

        # Cleanup
        server.stop()
        driver.disconnect()

    def test_client_all_methods_through_real_server(self, rpc_server):
        """Test all client methods through real server."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Test insert
            row_id = client.insert("test_table", {"name": "Test", "value": 42})
            assert row_id > 0

            # Test select
            rows = client.select("test_table")
            assert len(rows) >= 1

            # Test update
            affected = client.update(
                "test_table", where={"id": row_id}, data={"value": 100}
            )
            assert affected == 1

            # Test select with where
            rows = client.select("test_table", where={"id": row_id})
            assert len(rows) == 1
            assert rows[0]["value"] == 100

            # Test get_table_info
            info = client.get_table_info("test_table")
            assert len(info) > 0

            # Test transactions
            transaction_id = client.begin_transaction()
            assert transaction_id is not None

            client.insert("test_table", {"name": "Trans", "value": 1})
            result = client.commit_transaction(transaction_id)
            assert result is True

            # Test delete
            affected = client.delete("test_table", where={"id": row_id})
            assert affected == 1
        finally:
            client.disconnect()

    def test_client_connection_pooling_real_server(self, rpc_server):
        """Test connection pooling with real server."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path, pool_size=5)
        client.connect()

        try:
            import concurrent.futures

            def make_request(i):
                return client.insert("test_table", {"name": f"Test_{i}", "value": i})

            # Make 20 concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(make_request, i) for i in range(20)]
                results = [f.result() for f in futures]

            # All requests should succeed
            assert all(r > 0 for r in results)

            # Verify data was inserted
            rows = client.select("test_table")
            assert len(rows) >= 20
        finally:
            client.disconnect()

    def test_client_retry_logic_real_server(self, rpc_server):
        """Test retry logic with real server."""
        _, socket_path = rpc_server

        # Create client with retry settings
        client = DatabaseClient(
            socket_path, max_retries=3, retry_delay=0.1, timeout=5.0
        )
        client.connect()

        try:
            # Normal operation should work
            row_id = client.insert("test_table", {"name": "RetryTest", "value": 99})
            assert row_id > 0

            # Verify operation succeeded
            rows = client.select("test_table", where={"id": row_id})
            assert len(rows) == 1
        finally:
            client.disconnect()

    def test_client_error_handling_real_server(self, rpc_server):
        """Test error handling with real server."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            from code_analysis.core.database_client.exceptions import RPCResponseError

            # Try to insert into non-existent table
            with pytest.raises(RPCResponseError):
                client.insert("nonexistent_table", {"data": "test"})

            # Try to select from non-existent table
            with pytest.raises(RPCResponseError):
                client.select("nonexistent_table")

            # Try to update non-existent row
            affected = client.update(
                "test_table", where={"id": 99999}, data={"value": 1}
            )
            # Should return 0 affected rows, not raise error
            assert affected == 0
        finally:
            client.disconnect()

    def test_client_health_check_real_server(self, rpc_server):
        """Test health check with real server."""
        _, socket_path = rpc_server

        client = DatabaseClient(socket_path)
        assert not client.is_connected()

        client.connect()
        assert client.is_connected()
        assert client.health_check()

        client.disconnect()
        assert not client.is_connected()
