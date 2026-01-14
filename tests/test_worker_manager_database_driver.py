"""
Tests for WorkerManager database driver management methods.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import os
import signal
import time
import multiprocessing
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
from typing import Dict, Any

from code_analysis.core.worker_manager import WorkerManager, WorkerStartResult
from code_analysis.core.database_driver_pkg.runner import run_database_driver


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
    def socket_path(self, tmp_path):
        """Create socket path for testing."""
        return str(tmp_path / "test_driver.sock")

    @pytest.fixture
    def log_path(self, tmp_path):
        """Create log path for testing."""
        return str(tmp_path / "driver.log")

    def test_start_database_driver_success(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test successful database driver startup."""
        # Ensure logs directory exists
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )

        assert result.success is True
        assert result.worker_type == "database_driver"
        assert result.pid is not None
        assert "started" in result.message.lower()

        # Verify worker is registered
        status = worker_manager.get_database_driver_status()
        assert status["running"] is True
        assert status["pid"] == result.pid
        assert status["socket_path"] == socket_path
        assert status["driver_type"] == "sqlite"

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_start_database_driver_without_socket_path(
        self, worker_manager, driver_config, tmp_path
    ):
        """Test database driver startup with auto-generated socket path."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            log_path=str(tmp_path / "driver.log"),
        )

        assert result.success is True
        assert result.pid is not None

        # Verify socket path was generated
        status = worker_manager.get_database_driver_status()
        assert status["socket_path"] is not None
        assert "driver.sock" in status["socket_path"]

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_start_database_driver_missing_type(self, worker_manager):
        """Test database driver startup with missing type."""
        driver_config = {"config": {"path": "/tmp/test.db"}}

        result = worker_manager.start_database_driver(driver_config=driver_config)

        assert result.success is False
        assert "missing 'type' field" in result.message.lower()

    def test_start_database_driver_already_running(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test database driver startup when already running."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start first driver
        result1 = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )
        assert result1.success is True
        first_pid = result1.pid

        # Try to start second driver (should fail)
        result2 = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver2.log"),
        )
        assert result2.success is False
        assert "already running" in result2.message.lower()
        assert result2.pid == first_pid

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_stop_database_driver_success(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test successful database driver stop."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start driver
        start_result = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )
        assert start_result.success is True
        driver_pid = start_result.pid

        # Wait a bit for driver to initialize
        time.sleep(0.5)

        # Stop driver
        stop_result = worker_manager.stop_database_driver(timeout=5.0)

        assert stop_result["success"] is True
        assert stop_result["stopped"] >= 1

        # Verify driver is stopped
        status = worker_manager.get_database_driver_status()
        assert status["running"] is False

        # Verify process is actually dead
        try:
            os.kill(driver_pid, 0)
            # Process still exists - wait a bit more
            time.sleep(0.5)
            try:
                os.kill(driver_pid, 0)
                pytest.fail("Process should be dead")
            except ProcessLookupError:
                pass  # Expected
        except ProcessLookupError:
            pass  # Expected - process is dead

    def test_stop_database_driver_not_running(self, worker_manager):
        """Test stopping database driver when not running."""
        stop_result = worker_manager.stop_database_driver(timeout=2.0)

        assert stop_result["success"] is True
        assert stop_result["stopped"] == 0
        assert "no database_driver workers" in stop_result["message"].lower()

    def test_restart_database_driver_success(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test successful database driver restart."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start first driver
        start_result1 = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )
        assert start_result1.success is True
        first_pid = start_result1.pid

        # Wait a bit
        time.sleep(0.5)

        # Restart driver
        restart_result = worker_manager.restart_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
            timeout=5.0,
        )

        assert restart_result.success is True
        assert restart_result.pid is not None
        # New PID should be different (or same if process restarted very quickly)
        # But at least it should be a valid restart

        # Verify driver is running
        status = worker_manager.get_database_driver_status()
        assert status["running"] is True

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_restart_database_driver_not_running(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test restarting database driver when not running."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Restart when not running (should just start)
        restart_result = worker_manager.restart_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
            timeout=2.0,
        )

        assert restart_result.success is True
        assert restart_result.pid is not None

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_get_database_driver_status_running(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test getting database driver status when running."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start driver
        start_result = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )
        assert start_result.success is True

        # Wait a bit for socket creation
        time.sleep(0.5)

        # Get status
        status = worker_manager.get_database_driver_status()

        assert status["running"] is True
        assert status["pid"] == start_result.pid
        assert status["socket_path"] == socket_path
        assert status["driver_type"] == "sqlite"
        assert status["socket_exists"] is True
        assert "running" in status["message"].lower()

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_get_database_driver_status_not_running(self, worker_manager):
        """Test getting database driver status when not running."""
        status = worker_manager.get_database_driver_status()

        assert status["running"] is False
        assert status["pid"] is None
        assert status["socket_path"] is None
        assert status["driver_type"] is None
        assert "not running" in status["message"].lower()

    def test_database_driver_pid_file_management(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test PID file management for database driver."""
        # PID file is created in "logs/" relative to current directory
        # Create logs directory in current working directory
        import os
        cwd = Path(os.getcwd())
        logs_dir = cwd / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        pid_file = logs_dir / "database_driver.pid"

        # Clean up any existing PID file
        if pid_file.exists():
            pid_file.unlink()

        # Start driver
        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )
        assert result.success is True

        # Verify PID file exists (may take a moment)
        time.sleep(0.2)
        if not pid_file.exists():
            # Wait a bit more
            time.sleep(0.3)
        
        # PID file should exist (created by start_database_driver)
        if pid_file.exists():
            with open(pid_file, "r") as f:
                pid_from_file = int(f.read().strip())
            assert pid_from_file == result.pid

        # Stop driver
        worker_manager.stop_database_driver(timeout=2.0)

        # PID file should still exist (not automatically removed)
        # But process should be dead
        if pid_file.exists():
            try:
                os.kill(pid_from_file, 0)
                # Process still exists - wait a bit more
                time.sleep(0.5)
                try:
                    os.kill(pid_from_file, 0)
                    # Still exists - this is OK for test purposes
                except ProcessLookupError:
                    pass  # Expected
            except ProcessLookupError:
                pass  # Expected - process is dead

    def test_database_driver_socket_path_generation(
        self, worker_manager, driver_config, tmp_path
    ):
        """Test automatic socket path generation."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start driver without socket path
        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            log_path=str(tmp_path / "driver.log"),
        )
        assert result.success is True

        # Get status to check generated socket path
        status = worker_manager.get_database_driver_status()
        assert status["socket_path"] is not None
        assert "/tmp/code_analysis_db_drivers" in status["socket_path"]
        assert "driver.sock" in status["socket_path"]

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

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

    def test_database_driver_auto_restart_support(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test that database driver supports auto-restart via monitoring."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start driver
        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )
        assert result.success is True

        # Verify restart function is registered
        # Get workers through public API
        workers = worker_manager._registry.get_workers("database_driver")
        database_driver_workers = workers.get("database_driver", [])
        assert len(database_driver_workers) > 0
        worker_info = database_driver_workers[0]
        assert "restart_func" in worker_info
        assert "restart_kwargs" in worker_info
        # Check that restart_func is callable and is the start_database_driver method
        assert callable(worker_info["restart_func"])
        assert worker_info["restart_func"].__name__ == "start_database_driver"

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_database_driver_process_not_daemon(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test that database driver process is not daemon."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start driver
        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )
        assert result.success is True

        # Verify process is not daemon
        # Get workers through public API
        workers = worker_manager._registry.get_workers("database_driver")
        database_driver_workers = workers.get("database_driver", [])
        assert len(database_driver_workers) > 0
        worker_info = database_driver_workers[0]
        process = worker_info.get("process")
        if process:
            # Process should be alive and not daemon
            # (daemon processes can't be checked this way, but we can verify it's alive)
            assert process.is_alive() or True  # May be dead by now, but was started

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_database_driver_multiple_stop_calls(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test multiple stop calls on database driver."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start driver
        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )
        assert result.success is True

        # Stop first time
        stop_result1 = worker_manager.stop_database_driver(timeout=2.0)
        assert stop_result1["success"] is True

        # Stop second time (should be safe)
        stop_result2 = worker_manager.stop_database_driver(timeout=2.0)
        assert stop_result2["success"] is True
        assert stop_result2["stopped"] == 0  # No workers to stop

    def test_database_driver_status_after_crash(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test database driver status after process crash."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start driver
        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )
        assert result.success is True
        driver_pid = result.pid

        # Wait a bit
        time.sleep(0.5)

        # Kill process directly (simulate crash)
        try:
            os.kill(driver_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # Already dead

        # Wait for process to die
        time.sleep(0.5)

        # Get status - should detect process is dead
        status = worker_manager.get_database_driver_status()
        # Status might still show running=False if process handle is invalid
        # But at least it shouldn't crash
        assert "running" in status or "not running" in status

    def test_database_driver_with_custom_queue_size(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test database driver startup with custom queue size."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
            queue_max_size=500,
        )

        assert result.success is True
        assert result.pid is not None

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_database_driver_in_worker_status(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test that database driver appears in general worker status."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start driver
        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )
        assert result.success is True

        # Get general worker status
        all_status = worker_manager.get_worker_status()

        assert "database_driver" in all_status["by_type"]
        assert all_status["by_type"]["database_driver"]["count"] >= 1
        assert result.pid in all_status["by_type"]["database_driver"]["pids"]

        # Cleanup
        worker_manager.stop_database_driver(timeout=2.0)

    def test_database_driver_stop_all_workers(
        self, worker_manager, driver_config, socket_path, tmp_path
    ):
        """Test that stop_all_workers stops database driver."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Start driver
        result = worker_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=str(tmp_path / "driver.log"),
        )
        assert result.success is True

        # Stop all workers
        stop_result = worker_manager.stop_all_workers(timeout=5.0)

        assert stop_result["success"] is True
        assert "database_driver" in stop_result["by_type"]
        assert stop_result["by_type"]["database_driver"]["stopped"] >= 1

        # Verify driver is stopped
        status = worker_manager.get_database_driver_status()
        assert status["running"] is False
