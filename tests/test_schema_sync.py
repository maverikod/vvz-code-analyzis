"""
Unit tests for database schema synchronization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
import os
from pathlib import Path
import pytest
import sqlite3

from code_analysis.core.database.base import CodeDatabase, SCHEMA_VERSION
from code_analysis.core.db_driver.sqlite import SQLiteDriver
from code_analysis.core.database.schema_sync import SchemaComparator
from code_analysis.core.backup_manager import BackupManager


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
def temp_backup_dir():
    """Create temporary backup directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sqlite_driver(temp_db_path):
    """Create SQLiteDriver instance for testing."""
    # Set environment variable to allow direct SQLite driver
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

    driver = SQLiteDriver()
    driver.connect({"path": str(temp_db_path)})

    yield driver

    driver.disconnect()

    if original_env is None:
        os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
    else:
        os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env


@pytest.fixture
def code_database(temp_db_path):
    """Create CodeDatabase instance for testing."""
    # Set environment variable to allow direct SQLite driver
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

    driver_config = {
        "type": "sqlite",
        "config": {"path": str(temp_db_path)},
    }

    db = CodeDatabase(driver_config)

    yield db

    db.close()

    if original_env is None:
        os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
    else:
        os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env


@pytest.fixture
def minimal_schema_definition():
    """Create minimal schema definition for testing."""
    return {
        "version": SCHEMA_VERSION,
        "tables": {
            "db_settings": {
                "columns": [
                    {
                        "name": "key",
                        "type": "TEXT",
                        "not_null": True,
                        "primary_key": True,
                    },
                    {"name": "value", "type": "TEXT", "not_null": True},
                    {
                        "name": "updated_at",
                        "type": "REAL",
                        "not_null": False,
                        "default": "julianday('now')",
                    },
                ],
                "foreign_keys": [],
                "unique_constraints": [],
                "check_constraints": [],
            },
        },
        "indexes": [],
        "virtual_tables": [],
        "migration_methods": {},
    }


class TestSchemaVersionManagement:
    """Tests for schema version management."""

    def test_get_schema_version_empty_db(self, sqlite_driver):
        """Test getting schema version from empty database."""
        version = sqlite_driver._get_schema_version()
        assert version is None

    def test_set_schema_version(self, sqlite_driver):
        """Test setting schema version."""
        sqlite_driver._set_schema_version("1.0.0")
        version = sqlite_driver._get_schema_version()
        assert version == "1.0.0"

    def test_update_schema_version(self, sqlite_driver):
        """Test updating schema version."""
        sqlite_driver._set_schema_version("1.0.0")
        sqlite_driver._set_schema_version("1.1.0")
        version = sqlite_driver._get_schema_version()
        assert version == "1.1.0"

    def test_version_update_on_schema_sync(
        self, sqlite_driver, temp_backup_dir, minimal_schema_definition
    ):
        """Test version update on schema sync."""
        # Sync schema (creates db_settings table and sets version)
        result = sqlite_driver.sync_schema(minimal_schema_definition, temp_backup_dir)
        assert result["success"] is True

        # Check version was set
        version = sqlite_driver._get_schema_version()
        assert version == SCHEMA_VERSION


class TestSchemaComparison:
    """Tests for schema comparison."""

    def test_missing_tables_detection(self, sqlite_driver, minimal_schema_definition):
        """Test detection of missing tables."""
        comparator = SchemaComparator(sqlite_driver, minimal_schema_definition)
        diff = comparator.compare_schemas()

        assert "db_settings" in diff.missing_tables

    def test_missing_columns_detection(
        self, sqlite_driver, temp_backup_dir, minimal_schema_definition
    ):
        """Test detection of missing columns."""
        # Create table with missing column
        sqlite_driver.execute(
            """
            CREATE TABLE db_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        sqlite_driver.commit()

        comparator = SchemaComparator(sqlite_driver, minimal_schema_definition)
        diff = comparator.compare_schemas()

        assert "db_settings" in diff.table_diffs
        table_diff = diff.table_diffs["db_settings"]
        assert len(table_diff.missing_columns) > 0
        assert any(col.name == "updated_at" for col in table_diff.missing_columns)

    def test_type_changes_detection(
        self, sqlite_driver, temp_backup_dir, minimal_schema_definition
    ):
        """Test detection of type changes."""
        # Create table with different type
        sqlite_driver.execute(
            """
            CREATE TABLE db_settings (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL,
                updated_at REAL
            )
            """
        )
        sqlite_driver.commit()

        comparator = SchemaComparator(sqlite_driver, minimal_schema_definition)
        diff = comparator.compare_schemas()

        assert "db_settings" in diff.table_diffs
        table_diff = diff.table_diffs["db_settings"]
        assert len(table_diff.type_changes) > 0
        # Check that value column type change is detected
        assert any(col_name == "value" for col_name, _, _ in table_diff.type_changes)

    def test_index_comparison(self, sqlite_driver, temp_backup_dir):
        """Test index comparison."""
        # Create schema with index
        schema_with_index = {
            "version": SCHEMA_VERSION,
            "tables": {
                "test_table": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                        },
                        {"name": "name", "type": "TEXT", "not_null": True},
                    ],
                    "foreign_keys": [],
                    "unique_constraints": [],
                    "check_constraints": [],
                },
            },
            "indexes": [
                {
                    "name": "idx_test_name",
                    "table": "test_table",
                    "columns": ["name"],
                    "unique": False,
                },
            ],
            "virtual_tables": [],
            "migration_methods": {},
        }

        # Create table without index
        sqlite_driver.execute(
            """
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
        sqlite_driver.commit()

        comparator = SchemaComparator(sqlite_driver, schema_with_index)
        diff = comparator.compare_schemas()

        assert len(diff.missing_indexes) > 0
        assert any(idx.name == "idx_test_name" for idx in diff.missing_indexes)


class TestBackupCreation:
    """Tests for database backup creation."""

    def test_database_backup_creation(self, temp_db_path, temp_backup_dir):
        """Test database backup creation."""
        # Create database with some data
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        cursor.execute("INSERT INTO test (name) VALUES ('test')")
        conn.commit()
        conn.close()

        # Create backup
        project_root = temp_db_path.parent
        backup_manager = BackupManager(project_root)
        backup_uuid = backup_manager.create_database_backup(
            temp_db_path, backup_dir=temp_backup_dir, comment="Test backup"
        )

        assert backup_uuid is not None

        # Check backup file exists
        backup_files = list(temp_backup_dir.glob(f"database-*-{backup_uuid}.db"))
        assert len(backup_files) > 0

    def test_empty_database_no_backup(self, temp_db_path, temp_backup_dir):
        """Test that empty database doesn't create backup."""
        # Create empty database
        conn = sqlite3.connect(str(temp_db_path))
        conn.close()

        # Try to create backup
        project_root = temp_db_path.parent
        backup_manager = BackupManager(project_root)
        backup_uuid = backup_manager.create_database_backup(
            temp_db_path, backup_dir=temp_backup_dir, comment="Test backup"
        )

        # Should return None for empty database
        assert backup_uuid is None


class TestSchemaSync:
    """Tests for schema synchronization."""

    def test_sync_with_empty_database(
        self, sqlite_driver, temp_backup_dir, minimal_schema_definition
    ):
        """Test sync with empty database."""
        result = sqlite_driver.sync_schema(minimal_schema_definition, temp_backup_dir)

        assert result["success"] is True
        assert len(result["changes_applied"]) > 0

        # Check that table was created
        tables = sqlite_driver.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='db_settings'"
        )
        assert len(tables) > 0

    def test_sync_with_outdated_schema(
        self, sqlite_driver, temp_backup_dir, minimal_schema_definition
    ):
        """Test sync with outdated schema."""
        # Create table with old structure (missing column)
        sqlite_driver.execute(
            """
            CREATE TABLE db_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        sqlite_driver.commit()

        result = sqlite_driver.sync_schema(minimal_schema_definition, temp_backup_dir)

        assert result["success"] is True
        assert len(result["changes_applied"]) > 0

        # Check that column was added
        columns = sqlite_driver.fetchall("PRAGMA table_info(db_settings)")
        column_names = [col["name"] for col in columns]
        assert "updated_at" in column_names

    def test_sync_with_identical_schema(
        self, sqlite_driver, temp_backup_dir, minimal_schema_definition
    ):
        """Test sync with identical schema (no changes)."""
        # First sync to create schema
        result1 = sqlite_driver.sync_schema(minimal_schema_definition, temp_backup_dir)
        assert result1["success"] is True

        # Second sync should have no changes
        result2 = sqlite_driver.sync_schema(minimal_schema_definition, temp_backup_dir)

        assert result2["success"] is True
        assert len(result2["changes_applied"]) == 0

    def test_sync_updates_version(
        self, sqlite_driver, temp_backup_dir, minimal_schema_definition
    ):
        """Test that sync updates schema version."""
        # Set old version
        sqlite_driver.execute(
            """
            CREATE TABLE db_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        sqlite_driver.execute(
            "INSERT INTO db_settings (key, value) VALUES ('schema_version', '0.9.0')"
        )
        sqlite_driver.commit()

        # Sync schema
        result = sqlite_driver.sync_schema(minimal_schema_definition, temp_backup_dir)
        assert result["success"] is True

        # Check version was updated
        version = sqlite_driver._get_schema_version()
        assert version == SCHEMA_VERSION

    def test_sync_creates_backup_for_non_empty_db(
        self, sqlite_driver, temp_backup_dir, minimal_schema_definition
    ):
        """Test that sync creates backup for non-empty database."""
        # Create table with data
        sqlite_driver.execute(
            """
            CREATE TABLE db_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        sqlite_driver.execute(
            "INSERT INTO db_settings (key, value) VALUES ('test_key', 'test_value')"
        )
        sqlite_driver.commit()

        # Sync schema
        result = sqlite_driver.sync_schema(minimal_schema_definition, temp_backup_dir)

        assert result["success"] is True
        # Backup should be created for non-empty database
        assert result["backup_uuid"] is not None
