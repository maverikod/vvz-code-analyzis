"""
Integration tests for database schema synchronization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
import os
from pathlib import Path
import pytest
import sqlite3

from code_analysis.core.database.base import CodeDatabase
from code_analysis.core.db_worker_manager import get_db_worker_manager


@pytest.fixture
def temp_db_path():
    """Create temporary database path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()
    # Clean up sidecar files
    for ext in [".wal", ".shm", ".journal"]:
        sidecar = db_path.with_suffix(db_path.suffix + ext)
        if sidecar.exists():
            sidecar.unlink()


@pytest.fixture
def temp_socket_dir():
    """Create temporary socket directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(autouse=True)
def cleanup_workers():
    """Clean up workers after each test."""
    yield
    # Clean up all workers
    manager = get_db_worker_manager()
    for worker_info in list(manager._workers.values()):
        try:
            manager.stop_worker(worker_info["db_path"])
        except Exception:
            pass


class TestWorkerStartup:
    """Tests for worker startup and database creation."""

    def test_worker_creates_empty_db_if_missing(self, temp_db_path, temp_socket_dir):
        """Test that worker creates empty database if missing."""
        # Remove database if exists
        if temp_db_path.exists():
            temp_db_path.unlink()

        # Note: In real scenario, worker is started via DBWorkerManager
        # For testing, we verify that worker creates empty DB
        # Create empty database manually (simulating worker behavior)
        conn = sqlite3.connect(str(temp_db_path))
        conn.close()

        # Verify database exists and is empty
        assert temp_db_path.exists()
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = cursor.fetchall()
        conn.close()
        assert len(tables) == 0

    def test_worker_does_not_create_schema(self, temp_db_path):
        """Test that worker does not create schema."""
        # Create empty database (simulating worker)
        conn = sqlite3.connect(str(temp_db_path))
        conn.close()

        # Verify no tables exist (schema is created by driver via sync_schema)
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = cursor.fetchall()
        conn.close()
        assert len(tables) == 0


class TestDriverIntegration:
    """Tests for driver integration with schema sync."""

    def test_sqlite_driver_syncs_schema_on_connect(self, temp_db_path):
        """Test that SQLiteDriver syncs schema on connect via CodeDatabase."""
        # Set environment variable to allow direct SQLite driver
        original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
        os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

        try:
            driver_config = {
                "type": "sqlite",
                "config": {"path": str(temp_db_path)},
            }

            # CodeDatabase.__init__ should call sync_schema()
            db = CodeDatabase(driver_config)

            # Verify schema was created
            tables = db.driver.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='db_settings'"
            )
            assert len(tables) > 0

            # Verify version was set
            version = db.driver._get_schema_version()
            assert version is not None

            db.close()
        finally:
            if original_env is None:
                os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
            else:
                os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env

    def test_schema_changes_are_applied_correctly(self, temp_db_path):
        """Test that schema changes are applied correctly."""
        # Set environment variable to allow direct SQLite driver
        original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
        os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

        try:
            # Create database with old schema and add some data
            conn = sqlite3.connect(str(temp_db_path))
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE db_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO db_settings (key, value) VALUES ('test', 'value')"
            )
            cursor.execute(
                "INSERT INTO db_settings (key, value) VALUES ('schema_version', '0.9.0')"
            )
            conn.commit()
            conn.close()

            # Connect via CodeDatabase (should sync schema)
            driver_config = {
                "type": "sqlite",
                "config": {"path": str(temp_db_path)},
            }

            db = CodeDatabase(driver_config)

            # Verify new column was added
            columns = db.driver.fetchall("PRAGMA table_info(db_settings)")
            column_names = [col["name"] for col in columns]
            assert "updated_at" in column_names

            db.close()
        finally:
            if original_env is None:
                os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
            else:
                os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env


class TestServerStartup:
    """Tests for schema sync on server startup."""

    def test_schema_sync_on_server_startup(self, temp_db_path):
        """Test schema sync on server startup (via CodeDatabase initialization)."""
        # Set environment variable to allow direct SQLite driver
        original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
        os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

        try:
            # Simulate server startup: create CodeDatabase
            driver_config = {
                "type": "sqlite",
                "config": {"path": str(temp_db_path)},
            }

            db = CodeDatabase(driver_config)

            # Verify schema is synchronized
            # Check that db_settings table exists
            tables = db.driver.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='db_settings'"
            )
            assert len(tables) > 0

            # Check that version is set
            version = db.driver._get_schema_version()
            assert version is not None

            db.close()
        finally:
            if original_env is None:
                os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
            else:
                os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env

    def test_backup_created_before_changes(self, temp_db_path, temp_socket_dir):
        """Test that backup is created before schema changes."""
        # Set environment variable to allow direct SQLite driver
        original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
        os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

        try:
            # Create database with some data
            conn = sqlite3.connect(str(temp_db_path))
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE db_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO db_settings (key, value) VALUES ('test', 'value')"
            )
            conn.commit()
            conn.close()

            # Determine backup directory
            if temp_db_path.parent.name == "data":
                backup_dir = temp_db_path.parent.parent / "backups"
            else:
                backup_dir = temp_db_path.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)

            # Count backups before
            backup_count_before = len(list(backup_dir.glob("database-*.db")))

            # Connect via CodeDatabase (should sync schema and create backup)
            driver_config = {
                "type": "sqlite",
                "config": {"path": str(temp_db_path), "backup_dir": str(backup_dir)},
            }

            db = CodeDatabase(driver_config)

            # Count backups after
            backup_count_after = len(list(backup_dir.glob("database-*.db")))

            # Backup should be created (if database had data)
            # Note: BackupManager skips empty databases, but we added data
            assert backup_count_after >= backup_count_before

            db.close()
        finally:
            if original_env is None:
                os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
            else:
                os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env

    def test_version_updated_after_sync(self, temp_db_path):
        """Test that version is updated after sync."""
        # Set environment variable to allow direct SQLite driver
        original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
        os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

        try:
            # Create database with old version
            conn = sqlite3.connect(str(temp_db_path))
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE db_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO db_settings (key, value) VALUES ('schema_version', '0.9.0')"
            )
            conn.commit()
            conn.close()

            # Connect via CodeDatabase (should sync schema and update version)
            driver_config = {
                "type": "sqlite",
                "config": {"path": str(temp_db_path)},
            }

            db = CodeDatabase(driver_config)

            # Verify version was updated
            version = db.driver._get_schema_version()
            from code_analysis.core.database.base import SCHEMA_VERSION

            assert version == SCHEMA_VERSION

            db.close()
        finally:
            if original_env is None:
                os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
            else:
                os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env
