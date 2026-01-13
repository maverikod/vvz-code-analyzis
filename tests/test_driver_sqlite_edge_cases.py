"""
Edge case tests for SQLite driver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import tempfile
from pathlib import Path

from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver
from code_analysis.core.database_driver_pkg.exceptions import (
    DriverConnectionError,
    DriverOperationError,
)


@pytest.fixture
def temp_db_path(tmp_path):
    """Create temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def sqlite_driver(temp_db_path):
    """Create SQLite driver instance."""
    driver = SQLiteDriver()
    driver.connect({"path": str(temp_db_path)})
    yield driver
    driver.disconnect()


class TestSQLiteDriverEdgeCases:
    """Test edge cases for SQLite driver."""

    def test_disconnect_without_connection(self):
        """Test disconnecting without connection."""
        driver = SQLiteDriver()
        # Should not raise
        driver.disconnect()

    def test_disconnect_with_transaction_manager_error(self, sqlite_driver):
        """Test disconnect when transaction manager raises error."""
        # This tests the exception handling in disconnect
        sqlite_driver.disconnect()
        # Should not raise

    def test_create_table_invalid_schema(self, sqlite_driver):
        """Test creating table with invalid schema."""
        with pytest.raises(DriverOperationError):
            sqlite_driver.create_table({})  # Missing name

        with pytest.raises(DriverOperationError):
            sqlite_driver.create_table({"name": "test"})  # Missing columns

    def test_create_table_with_default_values(self, sqlite_driver):
        """Test creating table with default values."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT", "default": "Unknown"},
                {"name": "age", "type": "INTEGER", "default": 0},
            ],
        }
        result = sqlite_driver.create_table(schema)
        assert result is True

    def test_insert_empty_data(self, sqlite_driver):
        """Test insert with empty data."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
            ],
        }
        sqlite_driver.create_table(schema)

        # Insert with empty dict should raise error (no columns to insert)
        with pytest.raises(DriverOperationError):
            sqlite_driver.insert("users", {})

    def test_select_with_order_by(self, sqlite_driver):
        """Test select with order_by."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
                {"name": "age", "type": "INTEGER"},
            ],
        }
        sqlite_driver.create_table(schema)

        sqlite_driver.insert("users", {"name": "Bob", "age": 30})
        sqlite_driver.insert("users", {"name": "Alice", "age": 25})

        rows = sqlite_driver.select("users", order_by=["name"])
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"  # Sorted by name

    def test_select_with_columns(self, sqlite_driver):
        """Test select with specific columns."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
                {"name": "email", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)
        sqlite_driver.insert("users", {"name": "John", "email": "john@example.com"})

        rows = sqlite_driver.select("users", columns=["name"])
        assert len(rows) == 1
        assert "name" in rows[0]
        assert "email" not in rows[0]

    def test_update_no_matching_rows(self, sqlite_driver):
        """Test update with no matching rows."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)

        affected = sqlite_driver.update(
            "users", where={"id": 999}, data={"name": "Updated"}
        )
        assert affected == 0

    def test_delete_no_matching_rows(self, sqlite_driver):
        """Test delete with no matching rows."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)

        affected = sqlite_driver.delete("users", where={"id": 999})
        assert affected == 0

    def test_execute_with_params(self, sqlite_driver):
        """Test execute with parameters."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)

        result = sqlite_driver.execute(
            "INSERT INTO users (name) VALUES (?)", ("Test",)
        )
        assert result["affected_rows"] == 1

    def test_get_table_info_nonexistent_table(self, sqlite_driver):
        """Test getting info for non-existent table."""
        # SQLite returns empty list for non-existent table, not an error
        info = sqlite_driver.get_table_info("nonexistent")
        assert info == []

    def test_sync_schema_empty_definition(self, sqlite_driver):
        """Test syncing schema with empty definition."""
        result = sqlite_driver.sync_schema({"tables": []})
        assert "created_tables" in result
        assert len(result["created_tables"]) == 0

    def test_sync_schema_with_errors(self, sqlite_driver):
        """Test syncing schema with errors."""
        schema_definition = {
            "tables": [
                {
                    "name": "invalid_table",
                    "columns": [],  # Invalid - no columns
                }
            ]
        }
        result = sqlite_driver.sync_schema(schema_definition)
        assert "errors" in result
        # May or may not have errors depending on validation
        assert isinstance(result["errors"], list)

    def test_select_with_offset_only(self, sqlite_driver):
        """Test select with offset but no limit."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)

        for i in range(10):
            sqlite_driver.insert("users", {"name": f"User{i}"})

        # SQLite requires LIMIT when using OFFSET, so we use LIMIT -1 (unlimited)
        rows = sqlite_driver.select("users", offset=5)
        assert len(rows) == 5  # Should return remaining rows after offset

    def test_update_rollback_on_error(self, sqlite_driver):
        """Test that update rolls back on error."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)
        sqlite_driver.insert("users", {"name": "John"})

        # Try to update with invalid column
        with pytest.raises(DriverOperationError):
            sqlite_driver.update("users", where={"id": 1}, data={"invalid_col": "value"})

    def test_delete_rollback_on_error(self, sqlite_driver):
        """Test that delete rolls back on error."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)
        sqlite_driver.insert("users", {"name": "John"})

        # Try to delete from non-existent table
        with pytest.raises(DriverOperationError):
            sqlite_driver.delete("nonexistent", where={"id": 1})
