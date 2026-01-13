"""
Tests for driver factory.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import tempfile
from pathlib import Path

from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.exceptions import DriverNotFoundError
from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver


class TestDriverFactory:
    """Test driver factory."""

    def test_create_sqlite_driver(self, tmp_path):
        """Test creating SQLite driver."""
        db_path = tmp_path / "test.db"
        config = {"path": str(db_path)}
        driver = create_driver("sqlite", config)
        assert isinstance(driver, SQLiteDriver)
        assert driver.conn is not None
        driver.disconnect()

    def test_create_sqlite_driver_case_insensitive(self, tmp_path):
        """Test creating SQLite driver with different case."""
        db_path = tmp_path / "test.db"
        config = {"path": str(db_path)}
        driver = create_driver("SQLITE", config)
        assert isinstance(driver, SQLiteDriver)
        driver.disconnect()

    def test_create_unknown_driver(self):
        """Test creating unknown driver type."""
        with pytest.raises(DriverNotFoundError, match="Unknown driver type"):
            create_driver("unknown", {})

    def test_create_postgres_driver_not_implemented(self):
        """Test creating PostgreSQL driver (not yet implemented)."""
        with pytest.raises(DriverNotFoundError, match="not yet implemented"):
            create_driver("postgres", {})

    def test_create_mysql_driver_not_implemented(self):
        """Test creating MySQL driver (not yet implemented)."""
        with pytest.raises(DriverNotFoundError, match="not yet implemented"):
            create_driver("mysql", {})
