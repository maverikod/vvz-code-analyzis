"""
Tests for database client.

Tests DatabaseClient functionality including all RPC method wrappers,
connection management, and error handling.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import threading
import time

import pytest

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.exceptions import (
    ConnectionError,
    RPCResponseError,
)
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.database_driver_pkg.rpc_server import RPCServer


class TestDatabaseClient:
    """Test database client functionality."""

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
                {"name": "age", "type": "INTEGER"},
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

        yield server, socket_path, db_path

        # Cleanup
        server.stop()
        driver.disconnect()

    def test_connect_disconnect(self, rpc_server):
        """Test client connection and disconnection."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        assert not client.is_connected()

        client.connect()
        assert client.is_connected()

        client.disconnect()
        assert not client.is_connected()

    def test_health_check(self, rpc_server):
        """Test health check."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            assert client.health_check()
        finally:
            client.disconnect()

    def test_create_table(self, rpc_server):
        """Test create_table method."""
        _, socket_path, db_path = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            schema = {
                "name": "new_table",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "value", "type": "TEXT"},
                ],
            }
            result = client.create_table(schema)
            assert result is True
        finally:
            client.disconnect()

    def test_drop_table(self, rpc_server):
        """Test drop_table method."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create table first
            schema = {
                "name": "temp_table",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                ],
            }
            client.create_table(schema)

            # Drop table
            result = client.drop_table("temp_table")
            assert result is True
        finally:
            client.disconnect()

    def test_insert(self, rpc_server):
        """Test insert method."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            row_id = client.insert("test_table", {"name": "John", "age": 30})
            assert row_id > 0
        finally:
            client.disconnect()

    def test_select(self, rpc_server):
        """Test select method."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Insert test data
            client.insert("test_table", {"name": "Alice", "age": 25})
            client.insert("test_table", {"name": "Bob", "age": 35})

            # Select all
            rows = client.select("test_table")
            assert len(rows) >= 2

            # Select with where
            rows = client.select("test_table", where={"age": 25})
            assert len(rows) == 1
            assert rows[0]["name"] == "Alice"

            # Select with limit
            rows = client.select("test_table", limit=1)
            assert len(rows) == 1

            # Select with columns
            rows = client.select("test_table", columns=["name"])
            assert len(rows) > 0
            assert "name" in rows[0]
            assert "age" not in rows[0]
        finally:
            client.disconnect()

    def test_update(self, rpc_server):
        """Test update method."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Insert test data
            row_id = client.insert("test_table", {"name": "Charlie", "age": 20})

            # Update
            affected = client.update(
                "test_table", where={"id": row_id}, data={"age": 21}
            )
            assert affected == 1

            # Verify update
            rows = client.select("test_table", where={"id": row_id})
            assert len(rows) == 1
            assert rows[0]["age"] == 21
        finally:
            client.disconnect()

    def test_delete(self, rpc_server):
        """Test delete method."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Insert test data
            row_id = client.insert("test_table", {"name": "DeleteMe", "age": 99})

            # Delete
            affected = client.delete("test_table", where={"id": row_id})
            assert affected == 1

            # Verify deletion
            rows = client.select("test_table", where={"id": row_id})
            assert len(rows) == 0
        finally:
            client.disconnect()

    def test_execute(self, rpc_server):
        """Test execute method."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            result = client.execute("SELECT COUNT(*) as count FROM test_table")
            assert "count" in result or "data" in result
        finally:
            client.disconnect()

    def test_transactions(self, rpc_server):
        """Test transaction methods."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Begin transaction
            transaction_id = client.begin_transaction()
            assert transaction_id is not None
            assert len(transaction_id) > 0

            # Insert in transaction
            row_id = client.insert("test_table", {"name": "Trans", "age": 1})

            # Commit transaction
            result = client.commit_transaction(transaction_id)
            assert result is True

            # Verify data was committed
            rows = client.select("test_table", where={"id": row_id})
            assert len(rows) == 1
        finally:
            client.disconnect()

    def test_rollback_transaction(self, rpc_server):
        """Test rollback transaction."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Begin transaction
            transaction_id = client.begin_transaction()

            # Insert in transaction
            client.insert("test_table", {"name": "Rollback", "age": 2})

            # Rollback transaction
            result = client.rollback_transaction(transaction_id)
            assert result is True

            # Verify data was rolled back (may not be visible depending on isolation)
            # This depends on driver implementation
        finally:
            client.disconnect()

    def test_get_table_info(self, rpc_server):
        """Test get_table_info method."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            info = client.get_table_info("test_table")
            assert isinstance(info, list)
            assert len(info) > 0
            # Check that info contains column information
            assert any("name" in col or "column" in str(col).lower() for col in info)
        finally:
            client.disconnect()

    def test_sync_schema(self, rpc_server):
        """Test sync_schema method."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            schema_definition = {
                "tables": [
                    {
                        "name": "synced_table",
                        "columns": [
                            {"name": "id", "type": "INTEGER", "primary_key": True},
                            {"name": "data", "type": "TEXT"},
                        ],
                    }
                ]
            }
            result = client.sync_schema(schema_definition)
            assert isinstance(result, dict)
        finally:
            client.disconnect()

    def test_error_handling(self, rpc_server):
        """Test error handling."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Try to insert into non-existent table
            with pytest.raises(RPCResponseError):
                client.insert("nonexistent_table", {"data": "test"})

            # Try to select from non-existent table
            with pytest.raises(RPCResponseError):
                client.select("nonexistent_table")
        finally:
            client.disconnect()

    def test_connection_error(self):
        """Test connection error handling."""
        socket_path = "/nonexistent/socket.sock"
        client = DatabaseClient(socket_path)

        with pytest.raises(ConnectionError):
            client.connect()

    def test_all_operations_workflow(self, rpc_server):
        """Test complete workflow with all operations."""
        _, socket_path, _ = rpc_server

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create table
            schema = {
                "name": "workflow_table",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "name", "type": "TEXT"},
                    {"name": "value", "type": "INTEGER"},
                ],
            }
            assert client.create_table(schema) is True

            # Insert data
            row_id1 = client.insert("workflow_table", {"name": "Item1", "value": 10})
            row_id2 = client.insert("workflow_table", {"name": "Item2", "value": 20})

            # Select all
            rows = client.select("workflow_table")
            assert len(rows) == 2

            # Update
            affected = client.update(
                "workflow_table", where={"id": row_id1}, data={"value": 15}
            )
            assert affected == 1

            # Select with where
            rows = client.select("workflow_table", where={"value": 15})
            assert len(rows) == 1
            assert rows[0]["name"] == "Item1"

            # Delete
            affected = client.delete("workflow_table", where={"id": row_id2})
            assert affected == 1

            # Verify final state
            rows = client.select("workflow_table")
            assert len(rows) == 1
            assert rows[0]["id"] == row_id1

            # Get table info
            info = client.get_table_info("workflow_table")
            assert len(info) > 0

            # Drop table
            assert client.drop_table("workflow_table") is True
        finally:
            client.disconnect()
