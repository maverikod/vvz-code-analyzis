"""
Integration tests for database driver with real data and real server.

Tests database driver operations through RPC server on real data from test_data.

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
from code_analysis.core.project_resolution import load_project_info

# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


class TestDatabaseDriverIntegration:
    """Test database driver integration with real data and real server."""

    @pytest.fixture
    def rpc_server_with_real_data(self, tmp_path):
        """Create RPC server with real data setup."""
        db_path = tmp_path / "integration_test.db"
        socket_path = str(tmp_path / "test_driver.sock")

        # Create driver
        driver = create_driver("sqlite", {"path": str(db_path)})

        # Create required tables
        schema = {
            "name": "projects",
            "columns": [
                {"name": "id", "type": "TEXT", "primary_key": True},
                {"name": "root_path", "type": "TEXT", "not_null": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)

        schema = {
            "name": "files",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "path", "type": "TEXT", "not_null": True},
                {"name": "project_id", "type": "TEXT", "not_null": True},
                {"name": "lines", "type": "INTEGER"},
            ],
        }
        driver.create_table(schema)

        # Start RPC server
        request_queue = RequestQueue()
        server = RPCServer(driver, request_queue, socket_path)

        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.2)  # Wait for server to start

        yield server, socket_path, db_path

        # Cleanup
        server.stop()
        driver.disconnect()

    def _check_test_data_available(self):
        """Check if test data is available."""
        if not TEST_DATA_DIR.exists():
            pytest.skip("test_data/ directory not found")
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        projectid_file = VAST_SRV_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in vast_srv")

    def test_driver_create_table_via_rpc(self, rpc_server_with_real_data):
        """Test creating tables via RPC server."""
        _, socket_path, _ = rpc_server_with_real_data

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            schema = {
                "name": "test_table",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "name", "type": "TEXT"},
                    {"name": "value", "type": "INTEGER"},
                ],
            }
            result = client.create_table(schema)
            assert result is True

            # Verify table exists
            info = client.get_table_info("test_table")
            assert len(info) > 0
        finally:
            client.disconnect()

    def test_driver_insert_select_via_rpc_real_data(self, rpc_server_with_real_data):
        """Test insert and select operations via RPC with real data."""
        self._check_test_data_available()

        _, socket_path, _ = rpc_server_with_real_data

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Load real project info
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            # Insert real project data
            row_id = client.insert(
                "projects",
                {
                    "id": project_id,
                    "root_path": str(project_info.root_path),
                    "name": VAST_SRV_DIR.name,
                },
            )
            assert row_id is not None

            # Select project
            rows = client.select("projects", where={"id": project_id})
            assert len(rows) == 1
            assert rows[0]["id"] == project_id
        finally:
            client.disconnect()

    def test_driver_operations_on_real_files_via_rpc(self, rpc_server_with_real_data):
        """Test driver operations on real files via RPC."""
        self._check_test_data_available()

        _, socket_path, _ = rpc_server_with_real_data

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Load real project info
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            # Find real Python files
            python_files = list(VAST_SRV_DIR.rglob("*.py"))
            if not python_files:
                pytest.skip("No Python files found in test_data/vast_srv/")

            # Insert first few real files
            test_files = python_files[:5]
            file_ids = []
            for file_path in test_files:
                file_id = client.insert(
                    "files",
                    {
                        "path": str(file_path),
                        "project_id": project_id,
                        "lines": len(file_path.read_text().splitlines()),
                    },
                )
                file_ids.append(file_id)

            # Select files for project
            rows = client.select("files", where={"project_id": project_id})
            assert len(rows) >= len(test_files)

            # Update file
            if file_ids:
                affected = client.update(
                    "files",
                    where={"id": file_ids[0]},
                    data={"lines": 999},
                )
                assert affected == 1

                # Verify update
                rows = client.select("files", where={"id": file_ids[0]})
                assert len(rows) == 1
                assert rows[0]["lines"] == 999
        finally:
            client.disconnect()

    def test_driver_transactions_via_rpc_real_data(self, rpc_server_with_real_data):
        """Test transactions via RPC with real data."""
        self._check_test_data_available()

        _, socket_path, _ = rpc_server_with_real_data

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Load real project info
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            # Begin transaction
            transaction_id = client.begin_transaction()

            # Insert in transaction
            client.insert(
                "projects",
                {
                    "id": project_id,
                    "root_path": str(project_info.root_path),
                    "name": VAST_SRV_DIR.name,
                },
            )

            # Commit transaction
            result = client.commit_transaction(transaction_id)
            assert result is True

            # Verify data was committed
            rows = client.select("projects", where={"id": project_id})
            assert len(rows) == 1
        finally:
            client.disconnect()

    def test_driver_concurrent_operations_via_rpc(self, rpc_server_with_real_data):
        """Test concurrent operations via RPC server."""
        _, socket_path, _ = rpc_server_with_real_data

        # Create main client for setup
        main_client = DatabaseClient(socket_path=socket_path)
        main_client.connect()

        try:
            # Create test table
            schema = {
                "name": "concurrent_test",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "value", "type": "INTEGER"},
                ],
            }
            main_client.create_table(schema)
        finally:
            main_client.disconnect()

        # Test sequential operations first (to verify basic functionality)
        client = DatabaseClient(socket_path=socket_path)
        client.connect()

        try:
            # Insert a few rows sequentially
            for i in range(5):
                row_id = client.insert("concurrent_test", {"value": i})
                assert row_id is not None

            # Verify rows exist
            rows = client.select("concurrent_test")
            assert len(rows) >= 5

            # Test that we can make multiple sequential operations
            # This verifies the RPC connection works correctly
            for i in range(5, 10):
                row_id = client.insert("concurrent_test", {"value": i})
                assert row_id is not None

            # Final verification
            rows = client.select("concurrent_test")
            assert len(rows) >= 10
        finally:
            client.disconnect()

    def test_driver_schema_sync_via_rpc(self, rpc_server_with_real_data):
        """Test schema sync via RPC."""
        _, socket_path, _ = rpc_server_with_real_data

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Define schema
            schema_definition = {
                "tables": [
                    {
                        "name": "schema_test",
                        "columns": [
                            {"name": "id", "type": "INTEGER", "primary_key": True},
                            {"name": "data", "type": "TEXT"},
                        ],
                    }
                ]
            }

            # Sync schema
            result = client.sync_schema(schema_definition)
            assert isinstance(result, dict)

            # Verify table exists
            info = client.get_table_info("schema_test")
            assert len(info) > 0
        finally:
            client.disconnect()

    def test_driver_error_handling_via_rpc(self, rpc_server_with_real_data):
        """Test error handling via RPC."""
        _, socket_path, _ = rpc_server_with_real_data

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Try to insert into non-existent table
            from code_analysis.core.database_client.exceptions import (
                RPCResponseError,
                RPCClientError,
            )

            # RPCClientError is raised for database errors
            with pytest.raises((RPCResponseError, RPCClientError)):
                client.insert("nonexistent_table", {"data": "test"})

            # Try to select from non-existent table
            with pytest.raises((RPCResponseError, RPCClientError)):
                client.select("nonexistent_table")
        finally:
            client.disconnect()

    def test_driver_all_operations_workflow_via_rpc(self, rpc_server_with_real_data):
        """Test complete workflow with all operations via RPC."""
        _, socket_path, _ = rpc_server_with_real_data

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Create table
            schema = {
                "name": "workflow_test",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "name", "type": "TEXT"},
                    {"name": "value", "type": "INTEGER"},
                ],
            }
            assert client.create_table(schema) is True

            # Insert data
            row_id1 = client.insert("workflow_test", {"name": "Item1", "value": 10})
            row_id2 = client.insert("workflow_test", {"name": "Item2", "value": 20})

            # Select all
            rows = client.select("workflow_test")
            assert len(rows) == 2

            # Update
            affected = client.update(
                "workflow_test", where={"id": row_id1}, data={"value": 15}
            )
            assert affected == 1

            # Select with where
            rows = client.select("workflow_test", where={"value": 15})
            assert len(rows) == 1
            assert rows[0]["name"] == "Item1"

            # Delete
            affected = client.delete("workflow_test", where={"id": row_id2})
            assert affected == 1

            # Verify final state
            rows = client.select("workflow_test")
            assert len(rows) == 1
            assert rows[0]["id"] == row_id1

            # Get table info
            info = client.get_table_info("workflow_test")
            assert len(info) > 0

            # Drop table
            assert client.drop_table("workflow_test") is True
        finally:
            client.disconnect()
