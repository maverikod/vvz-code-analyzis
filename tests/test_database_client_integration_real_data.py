"""
Integration tests for database client on real data from test_data.

Tests client operations on real database schemas and data from test_data projects.

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
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


class TestDatabaseClientIntegrationRealData:
    """Test database client on real data from test_data/."""

    @pytest.fixture
    def rpc_server_with_real_data(self, tmp_path):
        """Create RPC server with real data setup."""
        db_path = tmp_path / "real_data_test.db"
        socket_path = str(tmp_path / "test.sock")

        # Create driver and tables
        driver = create_driver("sqlite", {"path": str(db_path)})

        # Create projects table (real schema)
        schema = {
            "name": "projects",
            "columns": [
                {"name": "id", "type": "TEXT", "primary_key": True},
                {"name": "root_path", "type": "TEXT", "not_null": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        driver.create_table(schema)

        # Create files table (real schema)
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
        time.sleep(0.3)  # Wait for server to start

        yield server, socket_path, db_path

        # Cleanup
        server.stop()
        driver.disconnect()

    def _check_test_data_available(self):
        """Check if test data is available."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        projectid_file = VAST_SRV_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in vast_srv")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

    def test_client_operations_on_real_projects(self, rpc_server_with_real_data):
        """Test client operations on real projects."""
        self._check_test_data_available()

        _, socket_path, _ = rpc_server_with_real_data

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Load real project info
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            # Insert real project
            # Note: insert returns row_id, but for TEXT primary key it may be different
            # For now, just verify the operation succeeds
            try:
                client.insert(
                    "projects",
                    {
                        "id": project_id,
                        "root_path": str(project_info.root_path),
                        "name": VAST_SRV_DIR.name,
                    },
                )
            except Exception:
                # If project already exists, that's okay for this test
                pass

            # Select project
            rows = client.select("projects", where={"id": project_id})
            assert len(rows) >= 1
            assert rows[0]["id"] == project_id
        finally:
            client.disconnect()

    def test_client_operations_on_real_files(self, rpc_server_with_real_data):
        """Test client operations on real files from test_data."""
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
            for file_path in test_files:
                client.insert(
                    "files",
                    {
                        "path": str(file_path),
                        "project_id": project_id,
                        "lines": len(file_path.read_text().splitlines()),
                    },
                )

            # Select files for project
            rows = client.select("files", where={"project_id": project_id})
            assert len(rows) >= len(test_files)

            # Update file
            if rows:
                file_id = rows[0]["id"]
                affected = client.update(
                    "files",
                    where={"id": file_id},
                    data={"lines": 999},
                )
                assert affected == 1

                # Verify update
                updated_rows = client.select("files", where={"id": file_id})
                assert len(updated_rows) == 1
                assert updated_rows[0]["lines"] == 999
        finally:
            client.disconnect()

    def test_client_transactions_on_real_data(self, rpc_server_with_real_data):
        """Test client transactions on real data."""
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
            try:
                client.insert(
                    "projects",
                    {
                        "id": f"{project_id}_trans",
                        "root_path": str(project_info.root_path),
                        "name": f"{VAST_SRV_DIR.name}_trans",
                    },
                )
            except Exception:
                # If already exists, that's okay
                pass

            # Commit transaction
            result = client.commit_transaction(transaction_id)
            assert result is True

            # Verify data was committed
            rows = client.select("projects", where={"id": f"{project_id}_trans"})
            assert len(rows) >= 1
        finally:
            client.disconnect()

    def test_client_all_operations_workflow_real_data(self, rpc_server_with_real_data):
        """Test complete workflow with all client operations on real data."""
        self._check_test_data_available()

        _, socket_path, _ = rpc_server_with_real_data

        client = DatabaseClient(socket_path)
        client.connect()

        try:
            # Load real project info
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            # Create new table
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
            assert len(rows) >= 2

            # Update
            affected = client.update(
                "workflow_table", where={"id": row_id1}, data={"value": 15}
            )
            assert affected == 1

            # Select with where
            rows = client.select("workflow_table", where={"value": 15})
            assert len(rows) >= 1
            assert rows[0]["name"] == "Item1"

            # Delete
            affected = client.delete("workflow_table", where={"id": row_id2})
            assert affected == 1

            # Get table info
            info = client.get_table_info("workflow_table")
            assert len(info) > 0

            # Drop table
            assert client.drop_table("workflow_table") is True
        finally:
            client.disconnect()
