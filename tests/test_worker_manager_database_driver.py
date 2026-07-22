"""
Tests for WorkerManager database driver management methods.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from code_analysis.core.worker_manager import WorkerManager


class TestWorkerManagerDatabaseDriver:
    """Test WorkerManager database driver management methods."""

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

    def test_start_database_driver_missing_type(self, worker_manager):
        """Test database driver startup with missing type."""
        driver_config = {"config": {"path": "/tmp/test.db"}}

        result = worker_manager.start_database_driver(driver_config=driver_config)

        assert result.success is False
        assert "missing 'type' field" in result.message.lower()

    def test_stop_database_driver_not_running(self, worker_manager):
        """Test stopping database driver when not running."""
        stop_result = worker_manager.stop_database_driver(timeout=2.0)

        assert stop_result["success"] is True
        assert stop_result["stopped"] == 0
        assert "no database_driver workers" in stop_result["message"].lower()

    def test_get_database_driver_status_not_running(self, worker_manager):
        """Test getting database driver status when not running."""
        status = worker_manager.get_database_driver_status()

        assert status["running"] is False
        assert status["pid"] is None
        assert status["socket_path"] is None
        assert status["driver_type"] is None
        assert "not running" in status["message"].lower()

    def test_database_driver_socket_path_without_db_path(
        self, worker_manager, tmp_path
    ):
        """Test socket path generation when db_path is not in config."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Driver config without path
        driver_config = {
            "type": "postgres",
            "config": {
                "host": "localhost",
                "port": 5432,
            },
        }

        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            log_path=str(tmp_path / "driver.log"),
        )
        assert result.success is True

        # Get status to check generated socket path
        status = worker_manager.get_database_driver_status()
        assert status["socket_path"] is not None
        assert "postgres_driver.sock" in status["socket_path"]

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)
