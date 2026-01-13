"""
Edge case tests for SQLite schema manager.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from code_analysis.core.database_driver_pkg.drivers.sqlite_schema import (
    SQLiteSchemaManager,
)
from code_analysis.core.database_driver_pkg.exceptions import DriverOperationError


@pytest.fixture
def temp_db_path(tmp_path):
    """Create temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def schema_manager(temp_db_path):
    """Create schema manager instance."""
    conn = sqlite3.connect(str(temp_db_path))
    conn.row_factory = sqlite3.Row
    yield SQLiteSchemaManager(conn)
    conn.close()


class TestSQLiteSchemaManager:
    """Test SQLite schema manager."""

    def test_get_table_info(self, schema_manager, temp_db_path):
        """Test getting table info."""
        conn = schema_manager.conn
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)"
        )
        conn.commit()

        info = schema_manager.get_table_info("users")
        assert len(info) == 3
        assert info[0]["name"] == "id"
        assert info[1]["name"] == "name"
        assert info[2]["name"] == "age"

    def test_get_table_info_nonexistent(self, schema_manager):
        """Test getting info for non-existent table."""
        # Should return empty list, not raise error
        info = schema_manager.get_table_info("nonexistent")
        assert info == []

    def test_sync_schema_create_tables(self, schema_manager, temp_db_path):
        """Test syncing schema - creating tables."""
        def create_table_func(schema):
            conn = schema_manager.conn
            conn.execute(
                f"CREATE TABLE {schema['name']} (id INTEGER PRIMARY KEY)"
            )
            conn.commit()

        schema_definition = {
            "tables": [
                {"name": "users", "columns": [{"name": "id", "type": "INTEGER"}]},
                {"name": "posts", "columns": [{"name": "id", "type": "INTEGER"}]},
            ]
        }

        result = schema_manager.sync_schema(schema_definition, None, create_table_func)
        assert len(result["created_tables"]) == 2

    def test_sync_schema_existing_tables(self, schema_manager, temp_db_path):
        """Test syncing schema with existing tables."""
        conn = schema_manager.conn
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        conn.commit()

        def create_table_func(schema):
            pass  # Table already exists

        schema_definition = {
            "tables": [
                {"name": "users", "columns": [{"name": "id", "type": "INTEGER"}]},
            ]
        }

        result = schema_manager.sync_schema(schema_definition, None, create_table_func)
        assert "users" in result["modified_tables"]

    def test_sync_schema_with_errors(self, schema_manager, temp_db_path):
        """Test syncing schema with errors."""
        def create_table_func(schema):
            raise Exception("Table creation failed")

        schema_definition = {
            "tables": [
                {"name": "users", "columns": [{"name": "id", "type": "INTEGER"}]},
            ]
        }

        result = schema_manager.sync_schema(schema_definition, None, create_table_func)
        assert len(result["errors"]) > 0

    def test_sync_schema_empty_name(self, schema_manager, temp_db_path):
        """Test syncing schema with empty table name."""
        def create_table_func(schema):
            pass

        schema_definition = {
            "tables": [
                {"name": "", "columns": [{"name": "id", "type": "INTEGER"}]},
            ]
        }

        result = schema_manager.sync_schema(schema_definition, None, create_table_func)
        # Empty name should be skipped
        assert len(result["created_tables"]) == 0
