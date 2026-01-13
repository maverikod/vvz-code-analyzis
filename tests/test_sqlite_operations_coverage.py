"""
Additional tests for SQLite operations to improve coverage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import sqlite3
from pathlib import Path

from code_analysis.core.database_driver_pkg.drivers.sqlite_operations import (
    SQLiteOperations,
)
from code_analysis.core.database_driver_pkg.exceptions import DriverOperationError


@pytest.fixture
def temp_db_path(tmp_path):
    """Create temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def operations(temp_db_path):
    """Create SQLite operations instance."""
    conn = sqlite3.connect(str(temp_db_path))
    conn.row_factory = sqlite3.Row
    yield SQLiteOperations(conn)
    conn.close()


class TestSQLiteOperationsCoverage:
    """Test SQLite operations for coverage."""

    def test_insert_no_connection(self):
        """Test insert without connection."""
        operations = SQLiteOperations(None)
        with pytest.raises(DriverOperationError, match="not established"):
            operations.insert("users", {"name": "John"})

    def test_update_no_connection(self):
        """Test update without connection."""
        operations = SQLiteOperations(None)
        with pytest.raises(DriverOperationError, match="not established"):
            operations.update("users", {"id": 1}, {"name": "John"})

    def test_delete_no_connection(self):
        """Test delete without connection."""
        operations = SQLiteOperations(None)
        with pytest.raises(DriverOperationError, match="not established"):
            operations.delete("users", {"id": 1})

    def test_select_no_connection(self):
        """Test select without connection."""
        operations = SQLiteOperations(None)
        with pytest.raises(DriverOperationError, match="not established"):
            operations.select("users")

    def test_select_with_offset_only(self, operations, temp_db_path):
        """Test select with offset but no limit."""
        conn = operations.conn
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"
        )
        for i in range(10):
            conn.execute("INSERT INTO users (name) VALUES (?)", (f"User{i}",))
        conn.commit()

        rows = operations.select("users", offset=5)
        assert len(rows) == 5
