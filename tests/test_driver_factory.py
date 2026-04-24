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

    def test_create_postgres_driver_registered(self):
        """PostgreSQL driver is registered (requires psycopg + DB to instantiate)."""
        from code_analysis.core.database_driver_pkg.driver_factory import (
            _SUPPORTED_DRIVERS,
        )
        from code_analysis.core.database_driver_pkg.drivers.postgres import (
            PostgreSQLDriver,
        )

        assert "postgres" in _SUPPORTED_DRIVERS
        assert _SUPPORTED_DRIVERS["postgres"] is PostgreSQLDriver

    def test_create_mysql_driver_not_implemented(self):
        """Test creating MySQL driver (not supported; raises DriverNotFoundError)."""
        with pytest.raises(DriverNotFoundError, match="Unknown driver type"):
            create_driver("mysql", {})
