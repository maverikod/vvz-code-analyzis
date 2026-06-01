"""
Database driver manager for managing database driver process.

This module handles starting, stopping, restarting, and status checking
of the database driver process.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import multiprocessing
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import (
    DEFAULT_DB_DRIVER_SOCKET_DIR,
    DEFAULT_QUEUE_MAX_SIZE,
    DEFAULT_WORKER_STOP_TIMEOUT,
    DRIVER_STARTUP_DELAY,
    LOGS_DIR_NAME,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerStartResult:
    """
    Result of starting a worker process.

    Attributes:
        success: Whether the worker started.
        worker_type: Worker type string.
        pid: PID of spawned process if any.
        message: Human-readable message.
    """

    success: bool
    worker_type: str
    pid: Optional[int]
    message: str


class DatabaseDriverManager:
    """
    Manager for database driver process.

    Responsibilities:
    - Start database driver process
    - Stop database driver process
    - Restart database driver process
    - Get database driver status
    """

    def __init__(
        self,
        registry: Any,
        check_pid_file_callback: Any,
        register_callback: Any,
        stop_worker_type_callback: Any,
    ):
        """
        Initialize database driver manager.

        Args:
            registry: Worker registry instance
            check_pid_file_callback: Callback to check PID file
            register_callback: Callback to register worker
            stop_worker_type_callback: Callback to stop worker type
        """
        self.registry = registry
        self.check_pid_file = check_pid_file_callback
        self.register_worker = register_callback
        self.stop_worker_type = stop_worker_type_callback

    def start_database_driver(
        self,
        *,
        driver_config: Dict[str, Any],
        socket_path: Optional[str] = None,
        log_path: Optional[str] = None,
        queue_max_size: int = DEFAULT_QUEUE_MAX_SIZE,
    ) -> WorkerStartResult:
        """
        Start database driver process in a separate process and register it.

        The driver process runs the database driver (SQLite, PostgreSQL, etc.)
        and provides RPC interface for database operations.

        CRITICAL: Uses multiprocessing.Process, not threading.Thread or async.
        This ensures workers don't conflict with Hypercorn's event loop.

        Args:
            driver_config: Driver configuration dict with 'type' and 'config' keys.
            socket_path: Path to Unix socket for RPC communication (optional).
                        If not provided, will be generated based on driver config.
            log_path: Path to driver log file (optional).
            queue_max_size: Maximum size of request queue (default: 1000).

        Returns:
            WorkerStartResult.
        """
        from .database_driver_pkg.runner import run_database_driver

        driver_type = driver_config.get("type")
        if not driver_type:
            return WorkerStartResult(
                success=False,
                worker_type="database_driver",
                pid=None,
                message="Driver config missing 'type' field",
            )

        # Convert sqlite_proxy to sqlite for driver process
        # sqlite_proxy is for main process, sqlite is for worker process
        actual_driver_type = driver_type
        if driver_type == "sqlite_proxy":
            actual_driver_type = "sqlite"
            logger.info(
                "Converting driver type from 'sqlite_proxy' to 'sqlite' for driver process"
            )

        # Generate socket path if not provided
        if not socket_path:
            # Use driver config path to generate socket path
            driver_cfg = driver_config.get("config", {})
            db_path = driver_cfg.get("path")
            if db_path:
                # Generate socket path similar to db_worker_manager
                db_name = Path(db_path).stem
                socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
                socket_dir.mkdir(parents=True, exist_ok=True)
                socket_path = str(socket_dir / f"{db_name}_driver.sock")
            else:
                # Fallback to driver type
                socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
                socket_dir.mkdir(parents=True, exist_ok=True)
                socket_path = str(socket_dir / f"{driver_type}_driver.sock")

        # Check: read PID from file and verify that process is running (never "file exists" alone)
        pid_file_path = Path(LOGS_DIR_NAME) / "database_driver.pid"
        existing_pid = self.check_pid_file(
            pid_file_path, "database_driver", "database_driver"
        )
        if existing_pid is not None:
            # Process is alive, driver already running
            return WorkerStartResult(
                success=False,
                worker_type="database_driver",
                pid=existing_pid,
                message="Database driver already running",
            )

        # Create process (NOT thread, NOT async task)
        # Note: CODE_ANALYSIS_DB_WORKER=1 is set in run_database_driver() itself
        process = multiprocessing.Process(
            target=run_database_driver,
            args=(actual_driver_type, driver_config.get("config", {})),
            kwargs={
                "socket_path": socket_path,
                "log_path": log_path,
                "queue_max_size": queue_max_size,
            },
            daemon=False,  # NOT daemon - driver process should persist
        )
        process.start()

        # Write process number (PID) to PID file; check logic reads this and verifies process exists
        try:
            pid_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pid_file_path, "w") as f:
                f.write(str(process.pid))
        except Exception as e:
            logger.warning(f"Failed to write PID file: {e}")

        # Wait a bit for driver to initialize socket
        time.sleep(DRIVER_STARTUP_DELAY)

        # Verify socket file exists
        socket_file = Path(socket_path)
        if not socket_file.exists():
            # Wait a bit more for socket creation
            time.sleep(DRIVER_STARTUP_DELAY)
            if not socket_file.exists():
                logger.warning(
                    f"Database driver socket not created: {socket_path}, but process started (PID: {process.pid})"
                )

        worker_name = f"database_driver_{actual_driver_type}"
        self.register_worker(
            "database_driver",
            {
                "pid": process.pid,
                "process": process,
                "name": worker_name,
                "driver_type": driver_type,  # Keep original type for logging
                "actual_driver_type": actual_driver_type,  # Actual type used in process
                "socket_path": socket_path,
                "restart_func": self.start_database_driver,
                "restart_kwargs": {
                    "driver_config": driver_config,
                    "socket_path": socket_path,
                    "log_path": log_path,
                    "queue_max_size": queue_max_size,
                },
            },
        )
        return WorkerStartResult(
            success=True,
            worker_type="database_driver",
            pid=process.pid,
            message=f"Database driver started (PID {process.pid}, socket: {socket_path})",
        )

    def stop_database_driver(
        self, timeout: float = DEFAULT_WORKER_STOP_TIMEOUT
    ) -> Dict[str, Any]:
        """
        Stop database driver process.

        Args:
            timeout: Timeout in seconds for graceful shutdown.

        Returns:
            Dictionary with stop results.
        """
        return self.stop_worker_type("database_driver", timeout=timeout)

    def restart_database_driver(
        self,
        *,
        driver_config: Dict[str, Any],
        socket_path: Optional[str] = None,
        log_path: Optional[str] = None,
        queue_max_size: int = DEFAULT_QUEUE_MAX_SIZE,
        timeout: float = DEFAULT_WORKER_STOP_TIMEOUT,
    ) -> WorkerStartResult:
        """
        Restart database driver process.

        Stops the existing driver (if running) and starts a new one.

        Args:
            driver_config: Driver configuration dict with 'type' and 'config' keys.
            socket_path: Path to Unix socket for RPC communication (optional).
            log_path: Path to driver log file (optional).
            queue_max_size: Maximum size of request queue (default: 1000).
            timeout: Timeout in seconds for graceful shutdown of old driver.

        Returns:
            WorkerStartResult.
        """
        # Stop existing driver
        stop_result = self.stop_database_driver(timeout=timeout)
        if stop_result.get("failed", 0) > 0:
            logger.warning(
                f"Some errors occurred while stopping database driver: {stop_result.get('errors', [])}"
            )

        # Wait a bit before starting new driver
        time.sleep(DRIVER_STARTUP_DELAY)

        # Start new driver
        return self.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=log_path,
            queue_max_size=queue_max_size,
        )

    def get_database_driver_status(self) -> Dict[str, Any]:
        """
        Get status of database driver process.

        Returns:
            Dictionary with driver status information.
        """
        workers = self.registry.get_workers("database_driver")
        database_driver_workers = workers.get("database_driver", [])

        if not database_driver_workers:
            return {
                "running": False,
                "pid": None,
                "socket_path": None,
                "driver_type": None,
                "message": "Database driver not running",
            }

        # Get first worker (should be only one)
        worker_info = database_driver_workers[0]
        pid = worker_info.get("pid")
        process = worker_info.get("process")
        socket_path = worker_info.get("socket_path")
        driver_type = worker_info.get("driver_type")

        # Check if process is alive
        is_alive = False
        if process:
            try:
                is_alive = process.is_alive()
            except (ValueError, AssertionError):
                is_alive = False
        elif pid:
            try:
                import psutil

                proc = psutil.Process(pid)
                is_alive = proc.is_running()
            except Exception:
                is_alive = False

        # Check if socket exists
        socket_exists = False
        if socket_path:
            socket_exists = Path(socket_path).exists()

        return {
            "running": is_alive,
            "pid": pid,
            "socket_path": socket_path,
            "driver_type": driver_type,
            "socket_exists": socket_exists,
            "message": (
                f"Database driver {'running' if is_alive else 'not running'} "
                f"(PID: {pid}, socket: {socket_path})"
            ),
        }
