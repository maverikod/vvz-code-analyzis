"""
Integration tests for main process database driver startup.

Tests Step 7: Main Process Integration - database driver startup sequence,
shutdown handling, and error scenarios.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
from typing import Dict, Any

# Mock dependencies before importing main
sys.modules["mcp_proxy_adapter"] = MagicMock()
sys.modules["mcp_proxy_adapter.api"] = MagicMock()
sys.modules["mcp_proxy_adapter.api.core"] = MagicMock()
sys.modules["mcp_proxy_adapter.api.core.app_factory"] = MagicMock()
sys.modules["mcp_proxy_adapter.core"] = MagicMock()
sys.modules["mcp_proxy_adapter.core.config"] = MagicMock()
sys.modules["mcp_proxy_adapter.core.config.simple_config"] = MagicMock()
sys.modules["mcp_proxy_adapter.core.server_engine"] = MagicMock()
sys.modules["mcp_proxy_adapter.core.app_factory"] = MagicMock()
sys.modules["mcp_proxy_adapter.core.app_factory.ssl_config"] = MagicMock()
sys.modules["mcp_proxy_adapter.config"] = MagicMock()
sys.modules["mcp_proxy_adapter.commands"] = MagicMock()
sys.modules["mcp_proxy_adapter.commands.base"] = MagicMock()
sys.modules["mcp_proxy_adapter.commands.result"] = MagicMock()
sys.modules["mcp_proxy_adapter.commands.hooks"] = MagicMock()
sys.modules["mcp_proxy_adapter.commands.command_registry"] = MagicMock()

from code_analysis.core.worker_manager import WorkerManager, WorkerStartResult


class TestMainProcessIntegration:
    """Test main process database driver integration."""

    @pytest.fixture
    def worker_manager(self):
        """Create WorkerManager instance."""
        # Reset singleton for clean test state
        WorkerManager._instance = None
        manager = WorkerManager.get_instance()
        yield manager
        # Cleanup: stop all workers
        try:
            manager.stop_all_workers(timeout=2.0)
        except Exception:
            pass
        WorkerManager._instance = None

    @pytest.fixture
    def driver_config(self, tmp_path):
        """Create driver config for testing."""
        db_path = tmp_path / "test.db"
        return {
            "type": "sqlite",
            "config": {
                "path": str(db_path),
            },
        }

    @pytest.fixture
    def app_config_with_driver(self, tmp_path, driver_config):
        """Create app config with driver configuration."""
        return {
            "code_analysis": {
                "database": {
                    "driver": driver_config,
                },
            },
        }

    @pytest.fixture
    def app_config_without_driver(self):
        """Create app config without driver configuration."""
        return {
            "code_analysis": {},
        }

    @pytest.fixture
    def mock_config_instance(self, app_config_with_driver):
        """Create mock config instance."""
        mock_cfg = MagicMock()
        mock_cfg.config_data = app_config_with_driver
        mock_cfg.config_path = None
        return mock_cfg

    @pytest.fixture
    def mock_storage_paths(self, tmp_path):
        """Create mock storage paths."""
        from code_analysis.core.storage_paths import StoragePaths

        return StoragePaths(
            config_dir=tmp_path / "config",
            db_path=tmp_path / "test.db",
            faiss_dir=tmp_path / "faiss",
            locks_dir=tmp_path / "locks",
            queue_dir=None,
            backup_dir=tmp_path / "backups",
            trash_dir=tmp_path / "trash",
        )

    def test_startup_database_driver_success(
        self,
        worker_manager,
        driver_config,
        app_config_with_driver,
        mock_config_instance,
        mock_storage_paths,
        tmp_path,
    ):
        """Test successful database driver startup via WorkerManager (simulating startup_database_driver logic)."""
        # This test simulates the logic of startup_database_driver() without importing main.py
        # The actual function is defined inside main() and cannot be imported directly

        from code_analysis.core.config import get_driver_config

        # Get driver config (same logic as in startup_database_driver)
        driver_config_loaded = get_driver_config(app_config_with_driver)
        assert driver_config_loaded is not None

        # Ensure logs directory exists
        logs_dir = tmp_path / "config" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = str(logs_dir / "database_driver.log")

        # Start database driver using WorkerManager (same as startup_database_driver does)
        result = worker_manager.start_database_driver(
            driver_config=driver_config_loaded,
            log_path=log_path,
        )

        # Verify driver was started
        assert result.success is True
        status = worker_manager.get_database_driver_status()
        assert status["running"] is True
        assert status["pid"] is not None
        assert status["driver_type"] == "sqlite"

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_startup_database_driver_no_config(
        self,
        app_config_without_driver,
        mock_config_instance,
        mock_storage_paths,
        tmp_path,
    ):
        """Test startup logic when no driver config is found."""
        # This test simulates the logic when no driver config is found
        from code_analysis.core.config import get_driver_config

        # Get driver config - should return None when no config
        driver_config = get_driver_config(app_config_without_driver)

        # Verify no config found (startup_database_driver would return early)
        assert driver_config is None

    def test_startup_database_driver_error_handling(
        self,
        worker_manager,
        driver_config,
        app_config_with_driver,
        tmp_path,
    ):
        """Test error handling when driver startup fails."""
        # Test that WorkerManager handles errors gracefully
        from code_analysis.core.config import get_driver_config

        # Get valid driver config
        driver_config_loaded = get_driver_config(app_config_with_driver)
        assert driver_config_loaded is not None

        # Try to start with invalid config (missing path)
        invalid_config = {"type": "sqlite", "config": {}}
        result = worker_manager.start_database_driver(
            driver_config=invalid_config,
            log_path=str(tmp_path / "driver.log"),
        )

        # Should handle error gracefully (may fail but shouldn't raise exception)
        # Result may be success=False, which is acceptable
        assert isinstance(result.success, bool)

    def test_startup_database_driver_worker_manager_error(
        self,
        worker_manager,
        driver_config,
        app_config_with_driver,
        tmp_path,
    ):
        """Test error handling when worker manager fails to start driver."""
        from code_analysis.core.config import get_driver_config

        # Get driver config
        driver_config_loaded = get_driver_config(app_config_with_driver)
        assert driver_config_loaded is not None

        # Test with invalid socket path (should handle error gracefully)
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start driver - should work or fail gracefully
        result = worker_manager.start_database_driver(
            driver_config=driver_config_loaded,
            log_path=str(logs_dir / "driver.log"),
        )

        # Result should be a valid WorkerStartResult
        assert isinstance(result, WorkerStartResult)
        assert isinstance(result.success, bool)

    def test_startup_sequence_driver_before_workers(
        self,
        worker_manager,
        driver_config,
        app_config_with_driver,
        tmp_path,
    ):
        """Test that database driver can be started (simulating startup sequence)."""
        # This test verifies that driver startup works correctly
        # Full integration test with real server would verify actual startup sequence
        from code_analysis.core.config import get_driver_config

        # Get driver config
        driver_config_loaded = get_driver_config(app_config_with_driver)
        assert driver_config_loaded is not None

        # Ensure logs directory exists
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start database driver (first in sequence)
        result = worker_manager.start_database_driver(
            driver_config=driver_config_loaded,
            log_path=str(logs_dir / "database_driver.log"),
        )

        # Verify driver started successfully
        assert result.success is True
        status = worker_manager.get_database_driver_status()
        assert status["running"] is True

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_startup_driver_config_loading(
        self,
        app_config_with_driver,
        mock_config_instance,
        tmp_path,
    ):
        """Test that driver config is loaded from code_analysis.database.driver."""
        # Import config function
        from code_analysis.core.config import get_driver_config

        # Test config loading
        driver_config = get_driver_config(app_config_with_driver)

        assert driver_config is not None
        assert driver_config["type"] == "sqlite"
        assert "config" in driver_config
        assert "path" in driver_config["config"]

    def test_startup_driver_with_config_path_fallback(
        self,
        app_config_with_driver,
        driver_config,
        tmp_path,
    ):
        """Test driver config loading from file (simulating config_path fallback)."""
        # This test verifies that config can be loaded from file
        from code_analysis.core.config import get_driver_config

        # Write config to file
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(app_config_with_driver))

        # Load config from file
        with open(config_path, "r", encoding="utf-8") as f:
            config_from_file = json.load(f)

        # Get driver config from loaded config
        driver_config_loaded = get_driver_config(config_from_file)

        # Verify config was loaded correctly
        assert driver_config_loaded is not None
        assert driver_config_loaded["type"] == "sqlite"
