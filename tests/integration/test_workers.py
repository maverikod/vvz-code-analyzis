"""
Integration tests for workers with real data and real server.

Tests workers (file_watcher, vectorization) integration with database driver
through RPC server on real data from test_data.

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


class TestWorkersIntegration:
    """Test workers integration with real data and real server."""

    @pytest.fixture
    def rpc_server_with_schema(self, tmp_path):
        """Create RPC server with full schema."""
        db_path = tmp_path / "workers_test.db"
        socket_path = str(tmp_path / "test_workers.sock")

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
                {"name": "deleted", "type": "INTEGER", "default": 0},
            ],
        }
        driver.create_table(schema)

        schema = {
            "name": "vector_chunks",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "file_id", "type": "INTEGER", "not_null": True},
                {"name": "project_id", "type": "TEXT", "not_null": True},
                {"name": "chunk_text", "type": "TEXT"},
                {"name": "vector", "type": "BLOB"},
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

    def test_file_watcher_worker_with_real_data(self, rpc_server_with_schema):
        """Test file watcher worker with real data."""
        self._check_test_data_available()

        _, socket_path, _ = rpc_server_with_schema

        # Create database client
        database = DatabaseClient(socket_path=socket_path)
        database.connect()

        try:
            # Load real project info
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            # Create project in database
            database.insert(
                "projects",
                {
                    "id": project_id,
                    "root_path": str(project_info.root_path),
                    "name": VAST_SRV_DIR.name,
                },
            )

            # Find real Python files
            python_files = list(VAST_SRV_DIR.rglob("*.py"))
            if not python_files:
                pytest.skip("No Python files found in test_data/vast_srv/")

            # Insert first few files
            test_files = python_files[:10]
            for file_path in test_files:
                database.insert(
                    "files",
                    {
                        "path": str(file_path),
                        "project_id": project_id,
                        "lines": len(file_path.read_text().splitlines()),
                        "deleted": 0,
                    },
                )

            # Verify files were inserted
            rows = database.select("files", where={"project_id": project_id})
            assert len(rows) >= len(test_files)

            # Test file watcher operations
            # Get files for project
            project_files = database.select("files", where={"project_id": project_id})
            assert len(project_files) > 0

            # Update file (simulate file change)
            if project_files:
                file_id = project_files[0]["id"]
                affected = database.update(
                    "files",
                    where={"id": file_id},
                    data={"lines": 999},
                )
                assert affected == 1

        finally:
            database.disconnect()

    def test_vectorization_worker_with_real_data(self, rpc_server_with_schema):
        """Test vectorization worker with real data."""
        self._check_test_data_available()

        _, socket_path, _ = rpc_server_with_schema

        # Create database client
        database = DatabaseClient(socket_path=socket_path)
        database.connect()

        try:
            # Load real project info
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            # Create project in database
            database.insert(
                "projects",
                {
                    "id": project_id,
                    "root_path": str(project_info.root_path),
                    "name": VAST_SRV_DIR.name,
                },
            )

            # Find real Python files
            python_files = list(VAST_SRV_DIR.rglob("*.py"))
            if not python_files:
                pytest.skip("No Python files found in test_data/vast_srv/")

            # Insert files
            test_files = python_files[:5]
            file_ids = []
            for file_path in test_files:
                file_id = database.insert(
                    "files",
                    {
                        "path": str(file_path),
                        "project_id": project_id,
                        "lines": len(file_path.read_text().splitlines()),
                        "deleted": 0,
                    },
                )
                file_ids.append(file_id)

            # Test vectorization operations
            # Get files without vectors
            files = database.select("files", where={"project_id": project_id})
            assert len(files) > 0

            # Create mock vector (simulate embedding)
            # Use base64 encoded string instead of bytes for JSON serialization
            import base64

            mock_vector_bytes = bytes([0] * 384)  # 384-dimensional vector
            mock_vector_b64 = base64.b64encode(mock_vector_bytes).decode("utf-8")

            # Insert vector chunks (simulate vectorization)
            for file_id in file_ids[:3]:  # Vectorize first 3 files
                chunk_text = "Test chunk text"
                # Store vector as base64 string for JSON serialization
                database.insert(
                    "vector_chunks",
                    {
                        "file_id": file_id,
                        "project_id": project_id,
                        "chunk_text": chunk_text,
                        "vector": mock_vector_b64,
                    },
                )

            # Verify vector chunks were created
            chunks = database.select("vector_chunks", where={"project_id": project_id})
            assert len(chunks) == 3

        finally:
            database.disconnect()

    def test_workers_concurrent_operations(self, rpc_server_with_schema):
        """Test concurrent operations from multiple workers."""
        _, socket_path, _ = rpc_server_with_schema

        # Create multiple database clients (simulating multiple workers)
        clients = [DatabaseClient(socket_path=socket_path) for _ in range(5)]
        for client in clients:
            client.connect()

        try:
            # Create test table
            schema = {
                "name": "worker_test",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "worker_id", "type": "INTEGER"},
                    {"name": "data", "type": "TEXT"},
                ],
            }
            clients[0].create_table(schema)

            # Concurrent inserts from different workers
            import concurrent.futures

            def worker_insert(worker_id):
                return clients[worker_id].insert(
                    "worker_test", {"worker_id": worker_id, "data": f"data_{worker_id}"}
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(worker_insert, i) for i in range(5)]
                results = [f.result() for f in futures]

            # Verify all inserts succeeded
            assert len(results) == 5
            assert all(r is not None for r in results)

            # Verify all rows exist
            rows = clients[0].select("worker_test")
            assert len(rows) == 5

        finally:
            for client in clients:
                client.disconnect()

    def test_workers_error_handling(self, rpc_server_with_schema):
        """Test workers error handling."""
        _, socket_path, _ = rpc_server_with_schema

        database = DatabaseClient(socket_path=socket_path)
        database.connect()

        try:
            # Try operations on non-existent table
            from code_analysis.core.database_client.exceptions import (
                RPCResponseError,
                RPCClientError,
            )

            # RPCClientError is raised for database errors
            with pytest.raises((RPCResponseError, RPCClientError)):
                database.select("nonexistent_table")

            with pytest.raises((RPCResponseError, RPCClientError)):
                database.insert("nonexistent_table", {"data": "test"})

        finally:
            database.disconnect()

    def test_workers_connection_pooling(self, rpc_server_with_schema):
        """Test workers connection pooling."""
        _, socket_path, _ = rpc_server_with_schema

        # Create client with connection pool
        database = DatabaseClient(socket_path=socket_path, pool_size=10)
        database.connect()

        try:
            # Create test table
            schema = {
                "name": "pool_test",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "value", "type": "INTEGER"},
                ],
            }
            database.create_table(schema)

            # Make many concurrent requests (test connection pool)
            import concurrent.futures

            def make_request(value):
                # Each request uses the same client with connection pool
                return database.insert("pool_test", {"value": value})

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(make_request, i) for i in range(50)]
                results = [f.result() for f in futures]

            # Verify all requests succeeded
            assert len(results) == 50
            assert all(r is not None for r in results)

            # Verify all rows exist
            rows = database.select("pool_test")
            assert len(rows) == 50

        finally:
            database.disconnect()
