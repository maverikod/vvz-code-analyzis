"""
Tests for SQLite driver.

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
    TransactionError,
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


class TestSQLiteDriverConnection:
    """Test SQLite driver connection."""

    def test_connect_success(self, temp_db_path):
        """Test successful connection."""
        driver = SQLiteDriver()
        driver.connect({"path": str(temp_db_path)})
        assert driver.conn is not None
        assert driver.db_path == temp_db_path.resolve()
        driver.disconnect()

    def test_connect_missing_path(self):
        """Test connection without path."""
        driver = SQLiteDriver()
        with pytest.raises(DriverConnectionError, match="path"):
            driver.connect({})

    def test_disconnect(self, sqlite_driver):
        """Test disconnection."""
        sqlite_driver.disconnect()
        assert sqlite_driver.conn is None


class TestSQLiteDriverTableOperations:
    """Test SQLite driver table operations."""

    def test_create_table(self, sqlite_driver):
        """Test creating table."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT", "nullable": False},
                {"name": "email", "type": "TEXT", "nullable": True},
            ],
        }
        result = sqlite_driver.create_table(schema)
        assert result is True

    def test_create_table_with_constraints(self, sqlite_driver):
        """Test creating table with constraints."""
        schema = {
            "name": "posts",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "user_id", "type": "INTEGER", "nullable": False},
                {"name": "title", "type": "TEXT", "nullable": False},
            ],
            "constraints": [
                {
                    "type": "foreign_key",
                    "columns": ["user_id"],
                    "references_table": "users",
                    "references_columns": ["id"],
                }
            ],
        }
        # First create users table
        users_schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(users_schema)

        # Then create posts table
        result = sqlite_driver.create_table(schema)
        assert result is True

    def test_drop_table(self, sqlite_driver):
        """Test dropping table."""
        schema = {
            "name": "test_table",
            "columns": [{"name": "id", "type": "INTEGER"}],
        }
        sqlite_driver.create_table(schema)
        result = sqlite_driver.drop_table("test_table")
        assert result is True


class TestSQLiteDriverCRUD:
    """Test SQLite driver CRUD operations."""

    def test_insert(self, sqlite_driver):
        """Test insert operation."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
                {"name": "email", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)

        row_id = sqlite_driver.insert("users", {"name": "John", "email": "john@example.com"})
        assert row_id > 0

    def test_select(self, sqlite_driver):
        """Test select operation."""
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
        sqlite_driver.insert("users", {"name": "Jane", "email": "jane@example.com"})

        rows = sqlite_driver.select("users")
        assert len(rows) == 2

        rows = sqlite_driver.select("users", where={"name": "John"})
        assert len(rows) == 1
        assert rows[0]["name"] == "John"

    def test_select_with_limit_offset(self, sqlite_driver):
        """Test select with limit and offset."""
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

        rows = sqlite_driver.select("users", limit=5)
        assert len(rows) == 5

        rows = sqlite_driver.select("users", limit=5, offset=5)
        assert len(rows) == 5

    def test_update(self, sqlite_driver):
        """Test update operation."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
                {"name": "email", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)

        row_id = sqlite_driver.insert("users", {"name": "John", "email": "old@example.com"})
        affected = sqlite_driver.update(
            "users", where={"id": row_id}, data={"email": "new@example.com"}
        )
        assert affected == 1

        rows = sqlite_driver.select("users", where={"id": row_id})
        assert rows[0]["email"] == "new@example.com"

    def test_delete(self, sqlite_driver):
        """Test delete operation."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)

        row_id = sqlite_driver.insert("users", {"name": "John"})
        affected = sqlite_driver.delete("users", where={"id": row_id})
        assert affected == 1

        rows = sqlite_driver.select("users")
        assert len(rows) == 0


class TestSQLiteDriverTransactions:
    """Test SQLite driver transactions."""

    def test_begin_commit_transaction(self, sqlite_driver):
        """Test begin and commit transaction."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)

        transaction_id = sqlite_driver.begin_transaction()
        assert transaction_id is not None

        result = sqlite_driver.commit_transaction(transaction_id)
        assert result is True

    def test_begin_rollback_transaction(self, sqlite_driver):
        """Test begin and rollback transaction."""
        transaction_id = sqlite_driver.begin_transaction()
        assert transaction_id is not None

        result = sqlite_driver.rollback_transaction(transaction_id)
        assert result is True

    def test_commit_nonexistent_transaction(self, sqlite_driver):
        """Test committing non-existent transaction."""
        with pytest.raises(TransactionError):
            sqlite_driver.commit_transaction("nonexistent")


class TestSQLiteDriverSchema:
    """Test SQLite driver schema operations."""

    def test_get_table_info(self, sqlite_driver):
        """Test getting table info."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT", "nullable": False},
                {"name": "email", "type": "TEXT", "nullable": True},
            ],
        }
        sqlite_driver.create_table(schema)

        info = sqlite_driver.get_table_info("users")
        assert len(info) == 3
        assert info[0]["name"] == "id"
        assert info[0]["primary_key"] is True
        assert info[1]["name"] == "name"
        assert info[2]["name"] == "email"

    def test_sync_schema(self, sqlite_driver):
        """Test schema synchronization."""
        schema_definition = {
            "tables": [
                {
                    "name": "users",
                    "columns": [
                        {"name": "id", "type": "INTEGER", "primary_key": True},
                        {"name": "name", "type": "TEXT"},
                    ],
                },
                {
                    "name": "posts",
                    "columns": [
                        {"name": "id", "type": "INTEGER", "primary_key": True},
                        {"name": "title", "type": "TEXT"},
                    ],
                },
            ]
        }

        result = sqlite_driver.sync_schema(schema_definition)
        assert "created_tables" in result
        assert len(result["created_tables"]) == 2


class TestSQLiteDriverExecute:
    """Test SQLite driver execute method."""

    def test_execute_select(self, sqlite_driver):
        """Test executing SELECT statement."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)
        sqlite_driver.insert("users", {"name": "John"})

        result = sqlite_driver.execute("SELECT * FROM users")
        assert "data" in result
        assert len(result["data"]) == 1

    def test_execute_insert(self, sqlite_driver):
        """Test executing INSERT statement."""
        schema = {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
            ],
        }
        sqlite_driver.create_table(schema)

        result = sqlite_driver.execute(
            "INSERT INTO users (name) VALUES (?)", ("John",)
        )
        assert result["affected_rows"] == 1
        assert result["lastrowid"] > 0
