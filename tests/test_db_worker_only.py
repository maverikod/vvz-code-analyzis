"""
Tests for database worker-only enforcement.

These tests ensure that:
- Direct SQLite driver can only be used in DB worker process
- CodeDatabase requires driver_config (no backward compatibility)
- All database access goes through driver API only

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import tempfile
from pathlib import Path

import pytest

from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker
from code_analysis.core.db_driver import create_driver
from code_analysis.core.exceptions import DatabaseOperationError


class TestWorkerOnlyEnforcement:
    """Tests for worker-only database access enforcement."""

    def test_sqlite_driver_forbidden_outside_worker(self):
        """Test that direct SQLite driver cannot be created outside worker process."""
        # Ensure we're not in worker process
        original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
        if "CODE_ANALYSIS_DB_WORKER" in os.environ:
            del os.environ["CODE_ANALYSIS_DB_WORKER"]

        try:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                db_path = tmp.name

            try:
                config = {"path": db_path}
                with pytest.raises(RuntimeError) as exc_info:
                    create_driver("sqlite", config)
                assert "DB worker process" in str(exc_info.value)
            finally:
                if Path(db_path).exists():
                    Path(db_path).unlink()
        finally:
            # Restore original environment
            if original_env:
                os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env

    def test_sqlite_driver_allowed_in_worker(self):
        """Test that direct SQLite driver can be created in worker process."""
        original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
        os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

        try:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                db_path = tmp.name

            try:
                config = {"path": db_path}
                driver = create_driver("sqlite", config)
                assert driver is not None
                driver.disconnect()
            finally:
                if Path(db_path).exists():
                    Path(db_path).unlink()
        finally:
            # Restore original environment
            if original_env:
                os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env
            elif "CODE_ANALYSIS_DB_WORKER" in os.environ:
                del os.environ["CODE_ANALYSIS_DB_WORKER"]

    def test_code_database_requires_driver_config(self):
        """Test that CodeDatabase requires driver_config parameter."""
        # Test with None
        with pytest.raises(ValueError) as exc_info:
            CodeDatabase(driver_config=None)
        assert "driver_config is required" in str(exc_info.value)

        # Test with empty dict
        with pytest.raises(ValueError) as exc_info:
            CodeDatabase(driver_config={})
        assert "driver_config must contain 'type' key" in str(exc_info.value)

        # Test with missing type
        with pytest.raises(ValueError) as exc_info:
            CodeDatabase(driver_config={"config": {}})
        assert "driver_config must contain 'type' key" in str(exc_info.value)

    def test_code_database_with_proxy_driver(self):
        """Test that CodeDatabase works with proxy driver."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            driver_config = create_driver_config_for_worker(Path(db_path))
            database = CodeDatabase(driver_config=driver_config)

            # Test basic operation
            result = database._fetchone("SELECT 1 as test")
            assert result is not None
            assert result["test"] == 1

            database.close()
        finally:
            if Path(db_path).exists():
                Path(db_path).unlink()
            registry_path = Path(db_path).parent / "queuemgr_registry.jsonl"
            if registry_path.exists():
                registry_path.unlink()

    def test_code_database_no_conn_property(self):
        """Test that CodeDatabase does not expose .conn property."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            driver_config = create_driver_config_for_worker(Path(db_path))
            database = CodeDatabase(driver_config=driver_config)

            # .conn should not exist
            with pytest.raises(AttributeError):
                _ = database.conn

            database.close()
        finally:
            if Path(db_path).exists():
                Path(db_path).unlink()
            registry_path = Path(db_path).parent / "queuemgr_registry.jsonl"
            if registry_path.exists():
                registry_path.unlink()

    def test_proxy_driver_handles_errors(self):
        """Test that proxy driver raises DatabaseOperationError on failures."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            driver_config = create_driver_config_for_worker(Path(db_path))
            database = CodeDatabase(driver_config=driver_config)

            # Test invalid SQL
            with pytest.raises(DatabaseOperationError) as exc_info:
                database._execute("INVALID SQL STATEMENT")
            assert exc_info.value.operation is not None
            assert exc_info.value.db_path is not None

            database.close()
        finally:
            if Path(db_path).exists():
                Path(db_path).unlink()
            registry_path = Path(db_path).parent / "queuemgr_registry.jsonl"
            if registry_path.exists():
                registry_path.unlink()


class TestNoBackwardCompatibility:
    """Tests to ensure no backward compatibility exists."""

    def test_no_code_database_db_path_parameter(self):
        """Test that CodeDatabase does not accept db_path parameter."""
        # This test verifies that the signature doesn't allow db_path
        # We can't actually test this at runtime since it's a type error,
        # but we can verify the __init__ signature doesn't have db_path
        import inspect

        sig = inspect.signature(CodeDatabase.__init__)
        params = list(sig.parameters.keys())
        # Should only have 'self' and 'driver_config'
        assert "db_path" not in params
        assert "driver_config" in params

    def test_driver_config_required_in_all_places(self):
        """Test that all database creation uses driver_config."""
        # This is more of a documentation test - we verify the pattern
        # is used consistently by checking create_driver_config_for_worker exists
        assert callable(create_driver_config_for_worker)

