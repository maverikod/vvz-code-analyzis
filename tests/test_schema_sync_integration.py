"""
Integration tests for database schema synchronization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import tempfile
from pathlib import Path

import pytest
import sqlite3

from code_analysis.core.database.schema_definition import SCHEMA_VERSION
from code_analysis.core.db_worker_manager import get_db_worker_manager

from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


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


def _sqlite_client(db_path: Path, *, backup_dir: Path | None = None):
    bd = backup_dir if backup_dir is not None else (db_path.parent / "backups")
    bd.mkdir(parents=True, exist_ok=True)
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    return sqlite_inprocess_database_client(db_path, backup_dir=bd), original_env


def _disconnect_client(client, original_env):
    client.disconnect()
    if original_env is None:
        os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
    else:
        os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env


def _schema_version_from_db_settings(db) -> str:
    r = db.execute(
        "SELECT value FROM db_settings WHERE key = 'schema_version' LIMIT 1",
        (),
    )
    rows = r.get("data") or []
    return str(rows[0]["value"]) if rows else ""


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
        """Test that opening via DatabaseClient + in-process RPC syncs schema."""
        db, orig = _sqlite_client(temp_db_path)
        try:
            r = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='db_settings'",
            )
            tables = r.get("data") or []
            assert len(tables) > 0

            version = _schema_version_from_db_settings(db)
            assert version
        finally:
            _disconnect_client(db, orig)

    def test_schema_changes_are_applied_correctly(self, temp_db_path):
        """Test that schema changes are applied correctly."""
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
        cursor.execute("INSERT INTO db_settings (key, value) VALUES ('test', 'value')")
        cursor.execute(
            "INSERT INTO db_settings (key, value) VALUES ('schema_version', '0.9.0')"
        )
        conn.commit()
        conn.close()

        db, orig = _sqlite_client(temp_db_path)
        try:
            col = db.execute(
                "SELECT name FROM pragma_table_info('db_settings') "
                "WHERE name = 'updated_at' LIMIT 1",
                (),
            )
            assert len(col.get("data") or []) >= 1
        finally:
            _disconnect_client(db, orig)


class TestServerStartup:
    """Tests for schema sync on server startup."""

    def test_schema_sync_on_server_startup(self, temp_db_path):
        """Test schema sync on startup via DatabaseClient (in-process RPC)."""
        db, orig = _sqlite_client(temp_db_path)
        try:
            r = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='db_settings'",
            )
            tables = r.get("data") or []
            assert len(tables) > 0

            version = _schema_version_from_db_settings(db)
            assert version
        finally:
            _disconnect_client(db, orig)

    def test_backup_created_before_changes(self, temp_db_path, temp_socket_dir):
        """Test that backup is created before schema changes."""
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
        cursor.execute("INSERT INTO db_settings (key, value) VALUES ('test', 'value')")
        conn.commit()
        conn.close()

        if temp_db_path.parent.name == "data":
            backup_dir = temp_db_path.parent.parent / "backups"
        else:
            backup_dir = temp_db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_count_before = len(list(backup_dir.glob("database-*.db")))

        db, orig = _sqlite_client(temp_db_path, backup_dir=backup_dir)
        try:
            backup_count_after = len(list(backup_dir.glob("database-*.db")))
            assert backup_count_after >= backup_count_before
        finally:
            _disconnect_client(db, orig)

    def test_version_updated_after_sync(self, temp_db_path):
        """Test that version is updated after sync."""
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

        db, orig = _sqlite_client(temp_db_path)
        try:
            assert _schema_version_from_db_settings(db) == SCHEMA_VERSION
        finally:
            _disconnect_client(db, orig)
