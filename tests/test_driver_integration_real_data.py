"""
Integration tests for database driver on real data from test_data.

Tests driver operations on real database schemas and data from test_data projects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path

from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
from code_analysis.core.project_resolution import load_project_info

# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


class TestDriverIntegrationRealData:
    """Test database driver on real data from test_data/."""

    @pytest.fixture
    def real_db_path(self, tmp_path):
        """Create database path for real data tests."""
        return tmp_path / "real_data_test.db"

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

    def test_driver_create_table_real_schema(self, real_db_path):
        """Test creating tables with real schema from test_data."""
        self._check_test_data_available()

        driver = create_driver("sqlite", {"path": str(real_db_path)})
        try:
            # Create projects table (real schema)
            schema = {
                "name": "projects",
                "columns": [
                    {"name": "id", "type": "TEXT", "primary_key": True},
                    {"name": "root_path", "type": "TEXT", "not_null": True},
                    {"name": "name", "type": "TEXT"},
                    {"name": "updated_at", "type": "REAL"},
                ],
            }
            result = driver.create_table(schema)
            assert result is True

            # Create files table (real schema)
            schema = {
                "name": "files",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "path", "type": "TEXT", "not_null": True},
                    {"name": "project_id", "type": "TEXT", "not_null": True},
                    {"name": "lines", "type": "INTEGER"},
                    {"name": "last_modified", "type": "REAL"},
                ],
            }
            result = driver.create_table(schema)
            assert result is True

            # Verify tables exist
            info = driver.get_table_info("projects")
            assert len(info) > 0
            info = driver.get_table_info("files")
            assert len(info) > 0
        finally:
            driver.disconnect()

    def test_driver_insert_select_real_data(self, real_db_path):
        """Test insert and select operations on real data."""
        self._check_test_data_available()

        driver = create_driver("sqlite", {"path": str(real_db_path)})
        try:
            # Create projects table
            schema = {
                "name": "projects",
                "columns": [
                    {"name": "id", "type": "TEXT", "primary_key": True},
                    {"name": "root_path", "type": "TEXT", "not_null": True},
                    {"name": "name", "type": "TEXT"},
                ],
            }
            driver.create_table(schema)

            # Load real project info
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            # Insert real project data
            row_id = driver.insert(
                "projects",
                {
                    "id": project_id,
                    "root_path": str(project_info.root_path),
                    "name": VAST_SRV_DIR.name,
                },
            )
            assert row_id is not None

            # Select project
            rows = driver.select("projects", where={"id": project_id})
            assert len(rows) == 1
            assert rows[0]["id"] == project_id
            assert rows[0]["root_path"] == str(project_info.root_path)
        finally:
            driver.disconnect()

    def test_driver_operations_on_real_files(self, real_db_path):
        """Test driver operations on real files from test_data."""
        self._check_test_data_available()

        driver = create_driver("sqlite", {"path": str(real_db_path)})
        try:
            # Create files table
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
                file_id = driver.insert(
                    "files",
                    {
                        "path": str(file_path),
                        "project_id": project_id,
                        "lines": len(file_path.read_text().splitlines()),
                    },
                )
                file_ids.append(file_id)

            # Select files for project
            rows = driver.select("files", where={"project_id": project_id})
            assert len(rows) >= len(test_files)

            # Update file
            if file_ids:
                affected = driver.update(
                    "files",
                    where={"id": file_ids[0]},
                    data={"lines": 999},
                )
                assert affected == 1

                # Verify update
                rows = driver.select("files", where={"id": file_ids[0]})
                assert len(rows) == 1
                assert rows[0]["lines"] == 999
        finally:
            driver.disconnect()

    def test_driver_transactions_on_real_data(self, real_db_path):
        """Test transactions on real data."""
        self._check_test_data_available()

        driver = create_driver("sqlite", {"path": str(real_db_path)})
        try:
            # Create projects table
            schema = {
                "name": "projects",
                "columns": [
                    {"name": "id", "type": "TEXT", "primary_key": True},
                    {"name": "root_path", "type": "TEXT", "not_null": True},
                    {"name": "name", "type": "TEXT"},
                ],
            }
            driver.create_table(schema)

            # Load real project info
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            # Begin transaction
            transaction_id = driver.begin_transaction()

            # Insert in transaction
            driver.insert(
                "projects",
                {
                    "id": project_id,
                    "root_path": str(project_info.root_path),
                    "name": VAST_SRV_DIR.name,
                },
            )

            # Commit transaction
            result = driver.commit_transaction(transaction_id)
            assert result is True

            # Verify data was committed
            rows = driver.select("projects", where={"id": project_id})
            assert len(rows) == 1
        finally:
            driver.disconnect()

    def test_driver_schema_operations_on_real_database(self, real_db_path):
        """Test schema operations on real database."""
        self._check_test_data_available()

        driver = create_driver("sqlite", {"path": str(real_db_path)})
        try:
            # Create initial schema
            schema_definition = {
                "tables": [
                    {
                        "name": "projects",
                        "columns": [
                            {"name": "id", "type": "TEXT", "primary_key": True},
                            {"name": "root_path", "type": "TEXT", "not_null": True},
                            {"name": "name", "type": "TEXT"},
                        ],
                    },
                    {
                        "name": "files",
                        "columns": [
                            {"name": "id", "type": "INTEGER", "primary_key": True},
                            {"name": "path", "type": "TEXT", "not_null": True},
                            {"name": "project_id", "type": "TEXT", "not_null": True},
                        ],
                    },
                ]
            }

            # Sync schema
            result = driver.sync_schema(schema_definition, backup_dir=None)
            assert isinstance(result, dict)

            # Verify tables exist
            info = driver.get_table_info("projects")
            assert len(info) > 0
            info = driver.get_table_info("files")
            assert len(info) > 0
        finally:
            driver.disconnect()

    def test_driver_request_queue_with_real_requests(self, real_db_path):
        """Test request queue with real requests."""
        self._check_test_data_available()

        driver = create_driver("sqlite", {"path": str(real_db_path)})
        try:
            # Create table
            schema = {
                "name": "test_table",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "data", "type": "TEXT"},
                ],
            }
            driver.create_table(schema)

            # Create request queue
            request_queue = RequestQueue(max_size=100)

            # Load real project info
            project_info = load_project_info(VAST_SRV_DIR)
            project_id = project_info.project_id

            # Enqueue multiple real requests
            for i in range(10):
                request_queue.enqueue(
                    f"req_{i}",
                    {
                        "method": "insert",
                        "params": {
                            "table_name": "test_table",
                            "data": {"data": f"test_data_{i}_{project_id}"},
                        },
                    },
                )

            # Process requests
            processed = 0
            while processed < 10:
                queued_request = request_queue.dequeue()
                if queued_request:
                    # Simulate processing
                    request_data = queued_request.data
                    if request_data.get("method") == "insert":
                        driver.insert(
                            request_data["params"]["table_name"],
                            request_data["params"]["data"],
                        )
                    processed += 1
                else:
                    break

            assert processed == 10

            # Verify data was inserted
            rows = driver.select("test_table")
            assert len(rows) == 10
        finally:
            driver.disconnect()
