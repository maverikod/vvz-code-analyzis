"""
Tests for SQLite proxy driver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
from pathlib import Path

import pytest

from code_analysis.core.db_driver import create_driver


class TestSQLiteProxyDriver:
    """Tests for SQLite proxy driver."""

    def test_create_proxy_driver(self):
        """Test creating proxy driver."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            config = {
                "path": db_path,
                "worker_config": {
                    "registry_path": str(
                        Path(db_path).parent / "test_queuemgr_registry.jsonl"
                    ),
                    "command_timeout": 10.0,
                },
            }

            driver = create_driver("sqlite_proxy", config)

            assert driver is not None
            assert hasattr(driver, "execute")
            assert hasattr(driver, "fetchone")
            assert hasattr(driver, "fetchall")

            # Cleanup
            driver.disconnect()
        finally:
            if Path(db_path).exists():
                Path(db_path).unlink()
            registry_path = Path(db_path).parent / "test_queuemgr_registry.jsonl"
            if registry_path.exists():
                registry_path.unlink()

    def test_proxy_driver_is_thread_safe(self):
        """Test that proxy driver reports as thread-safe."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            config = {
                "path": db_path,
                "worker_config": {
                    "registry_path": str(
                        Path(db_path).parent / "test_queuemgr_registry.jsonl"
                    ),
                    "command_timeout": 10.0,
                },
            }

            driver = create_driver("sqlite_proxy", config)

            assert driver.is_thread_safe is True

            # Cleanup
            driver.disconnect()
        finally:
            if Path(db_path).exists():
                Path(db_path).unlink()
            registry_path = Path(db_path).parent / "test_queuemgr_registry.jsonl"
            if registry_path.exists():
                registry_path.unlink()

    @pytest.mark.skip(reason="Requires queuemgr to be running - integration test")
    def test_proxy_driver_execute(self):
        """Test proxy driver execute operation."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            config = {
                "path": db_path,
                "worker_config": {
                    "registry_path": str(
                        Path(db_path).parent / "test_queuemgr_registry.jsonl"
                    ),
                    "command_timeout": 30.0,
                },
            }

            driver = create_driver("sqlite_proxy", config)

            # Create table
            driver.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")

            # Insert data
            driver.execute("INSERT INTO test (name) VALUES (?)", ("test1",))
            driver.commit()

            # Fetch data
            row = driver.fetchone("SELECT * FROM test WHERE id = ?", (1,))
            assert row is not None
            assert row["id"] == 1
            assert row["name"] == "test1"

            # Cleanup
            driver.disconnect()
        finally:
            if Path(db_path).exists():
                Path(db_path).unlink()
            registry_path = Path(db_path).parent / "test_queuemgr_registry.jsonl"
            if registry_path.exists():
                registry_path.unlink()
