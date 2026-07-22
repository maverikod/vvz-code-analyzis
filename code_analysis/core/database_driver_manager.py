"""
Database driver manager: legacy subprocess-driver lifecycle facade.

``start_database_driver``/``restart_database_driver`` are stubs (stage 2 layer
collapse): the subprocess/RPC driver architecture they used to spawn was
physically deleted -- PostgreSQL always runs in-process. ``stop_database_driver``
and ``get_database_driver_status`` remain functional against the (now always
empty) worker registry entry for backward compatibility.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import (
    DEFAULT_QUEUE_MAX_SIZE,
    DEFAULT_WORKER_STOP_TIMEOUT,
    DRIVER_STARTUP_DELAY,
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
        No longer supported: the database driver subprocess/RPC architecture
        was physically deleted (stage 2 layer collapse, client/RPC stack removal).

        PostgreSQL (the only supported driver) always runs in-process -- see
        :func:`code_analysis.main_workers.startup_database_driver`, which already
        skips this subprocess path entirely, and
        :mod:`code_analysis.core.database_client.factory`, which hands commands a
        connected :class:`~code_analysis.core.database_driver_pkg.drivers.postgres.PostgreSQLDriver`
        directly. Kept only so existing callers get an explicit, typed failure
        instead of an import error; not wired into any startup path.

        Args:
            driver_config: Driver configuration dict with 'type' and 'config' keys.
            socket_path: Unused (no Unix socket in the in-process architecture).
            log_path: Unused.
            queue_max_size: Unused.

        Returns:
            WorkerStartResult with ``success=False``.
        """
        _ = (socket_path, log_path, queue_max_size)
        driver_type = driver_config.get("type")
        if not driver_type:
            return WorkerStartResult(
                success=False,
                worker_type="database_driver",
                pid=None,
                message="Driver config missing 'type' field",
            )
        return WorkerStartResult(
            success=False,
            worker_type="database_driver",
            pid=None,
            message=(
                "Database driver subprocess/RPC architecture no longer supported; "
                "PostgreSQL always runs in-process (see main_workers.startup_database_driver)"
            ),
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
