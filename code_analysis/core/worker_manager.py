"""
Unified worker manager for all background workers.

This module provides a centralized way to manage all worker processes,
ensuring they are properly registered and gracefully shut down when
the server stops.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional

from .constants import (
    DEFAULT_QUEUE_MAX_SIZE,
    DEFAULT_WORKER_MONITOR_INTERVAL,
    DEFAULT_WORKER_STOP_TIMEOUT,
)
from .database_driver_manager import DatabaseDriverManager, WorkerStartResult
from .worker_lifecycle import WorkerLifecycleManager
from .worker_monitor import WorkerMonitor
from .worker_registry import WorkerRegistry

# Re-export WorkerStartResult for backward compatibility
__all__ = ["WorkerManager", "get_worker_manager", "WorkerStartResult"]

logger = logging.getLogger(__name__)


class WorkerManager:
    """
    Unified manager for all background workers.

    This is a facade class that delegates to specialized managers:
    - WorkerRegistry: Registration and status tracking
    - WorkerLifecycleManager: Starting and stopping workers
    - WorkerMonitor: Monitoring and auto-restart
    - DatabaseDriverManager: Database driver management

    Responsibilities:
    - Register workers when they start
    - Track worker processes by type and PID
    - Gracefully shut down all workers on server shutdown
    - Monitor workers and auto-restart dead ones
    """

    _instance: Optional["WorkerManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialize worker manager."""
        # Initialize components
        self._registry = WorkerRegistry()
        self._lifecycle = WorkerLifecycleManager(
            registry=self._registry,
            check_pid_file_callback=self._registry.check_and_cleanup_pid_file,
            register_callback=self._registry.register_worker,
            clear_workers_callback=self._registry.clear_workers,
        )
        self._monitor = WorkerMonitor(
            registry=self._registry,
            unregister_callback=self._registry.unregister_worker,
            register_callback=self._registry.register_worker,
        )
        self._driver_manager = DatabaseDriverManager(
            registry=self._registry,
            check_pid_file_callback=self._registry.check_and_cleanup_pid_file,
            register_callback=self._registry.register_worker,
            stop_worker_type_callback=self._lifecycle.stop_worker_type,
        )
        self._shutdown_requested = False

    @classmethod
    def get_instance(cls) -> "WorkerManager":
        """
        Get singleton instance of WorkerManager.

        Returns:
            WorkerManager instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # Registry methods
    def register_worker(
        self,
        worker_type: str,
        process_info: Dict[str, Any],
    ) -> None:
        """
        Register a worker with the manager.

        Args:
            worker_type: Type of worker (e.g., 'vectorization', 'file_watcher', 'repair', 'sqlite_queue')
            process_info: Dictionary with worker information
        """
        self._registry.register_worker(worker_type, process_info)

    def unregister_worker(self, worker_type: str, pid: Optional[int] = None) -> None:
        """
        Unregister a worker from the manager.

        Args:
            worker_type: Type of worker
            pid: Process ID (if None, removes all workers of this type)
        """
        self._registry.unregister_worker(worker_type, pid)

    def get_worker_status(self) -> Dict[str, Any]:
        """
        Get status of all registered workers.

        Returns:
            Dictionary with worker status information
        """
        return self._registry.get_worker_status()

    # Lifecycle methods
    def stop_worker_type(
        self, worker_type: str, timeout: float = DEFAULT_WORKER_STOP_TIMEOUT
    ) -> Dict[str, Any]:
        """
        Stop all workers of a specific type.

        Args:
            worker_type: Type of worker to stop
            timeout: Timeout in seconds for graceful shutdown

        Returns:
            Dictionary with stop results
        """
        return self._lifecycle.stop_worker_type(worker_type, timeout=timeout)

    def stop_all_workers(self, timeout: float = 30.0) -> Dict[str, Any]:
        """
        Stop all registered workers.

        Args:
            timeout: Timeout in seconds for graceful shutdown per worker type

        Returns:
            Dictionary with stop results
        """
        self._shutdown_requested = True

        # Stop monitoring thread first
        self.stop_monitoring()

        logger.info("Stopping all workers...")

        workers = self._registry.get_workers()
        worker_types = list(workers.keys())

        results = {}
        total_stopped = 0
        total_failed = 0
        all_errors = []

        for worker_type in worker_types:
            result = self._lifecycle.stop_worker_type(worker_type, timeout=timeout)
            results[worker_type] = result
            total_stopped += result.get("stopped", 0)
            total_failed += result.get("failed", 0)
            all_errors.extend(result.get("errors", []))

        summary = {
            "success": total_failed == 0,
            "total_stopped": total_stopped,
            "total_failed": total_failed,
            "by_type": results,
            "errors": all_errors,
            "message": (
                f"Stopped {total_stopped} worker(s) total, " f"{total_failed} failed"
            ),
        }

        logger.info(f"Worker shutdown complete: {summary['message']}")

        return summary

    async def stop_all_workers_async(self, timeout: float = 30.0) -> Dict[str, Any]:
        """
        Stop all registered workers asynchronously.

        Args:
            timeout: Timeout in seconds for graceful shutdown per worker type

        Returns:
            Dictionary with stop results
        """
        # Run stop_all_workers in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.stop_all_workers, timeout)

    def cleanup_on_shutdown(self) -> None:
        """
        Cleanup on server shutdown.

        This method should be called during server shutdown to ensure
        all workers are properly stopped.
        """
        if not self._shutdown_requested:
            logger.info("Cleanup requested, stopping all workers...")
            self.stop_all_workers()

    # Monitor methods
    def start_monitoring(
        self, interval: float = DEFAULT_WORKER_MONITOR_INTERVAL
    ) -> None:
        """
        Start background thread to monitor worker processes and restart dead ones.

        Args:
            interval: Check interval in seconds (default: 30.0)
        """
        self._monitor.set_shutdown_requested(False)
        self._monitor.start_monitoring(interval)

    def stop_monitoring(self, timeout: float = DEFAULT_WORKER_STOP_TIMEOUT) -> None:
        """
        Stop worker monitoring thread.

        Args:
            timeout: Timeout in seconds to wait for thread to stop
        """
        self._monitor.set_shutdown_requested(True)
        self._monitor.stop_monitoring(timeout)

    # Worker start methods
    def start_file_watcher_worker(
        self,
        *,
        db_path: str,
        watch_dirs: List[Dict[str, str]],
        locks_dir: str,
        scan_interval: int = 60,
        version_dir: Optional[str] = None,
        worker_log_path: Optional[str] = None,
        worker_logs_dir: Optional[str] = None,
        ignore_patterns: Optional[List[str]] = None,
    ) -> WorkerStartResult:
        """
        Start file watcher worker in a separate process and register it.

        Args:
            db_path: Path to database file.
            watch_dirs: List of watch directory configs with 'id' and 'path' keys.
            locks_dir: Service state directory for lock files.
            scan_interval: Scan interval seconds.
            version_dir: Version directory for deleted files.
            worker_log_path: Log path for worker process.
            worker_logs_dir: Absolute directory for worker log and PID file (optional).
            ignore_patterns: Optional ignore patterns.

        Returns:
            WorkerStartResult.
        """
        return self._lifecycle.start_file_watcher_worker(
            db_path=db_path,
            watch_dirs=watch_dirs,
            locks_dir=locks_dir,
            scan_interval=scan_interval,
            version_dir=version_dir,
            worker_log_path=worker_log_path,
            worker_logs_dir=worker_logs_dir,
            ignore_patterns=ignore_patterns,
        )

    def start_vectorization_worker(
        self,
        *,
        db_path: str,
        faiss_dir: str,
        vector_dim: int = 384,
        svo_config: Optional[Dict[str, Any]] = None,
        batch_size: int = 10,
        poll_interval: int = 30,
        worker_log_path: Optional[str] = None,
        worker_logs_dir: Optional[str] = None,
    ) -> WorkerStartResult:
        """
        Start universal vectorization worker in a separate process and register it.

        Args:
            db_path: Path to database file.
            faiss_dir: Base directory for FAISS index files.
            vector_dim: Embedding vector dimension.
            svo_config: Optional SVO config dict.
            batch_size: Batch size.
            poll_interval: Poll interval seconds.
            worker_log_path: Log path for worker process.
            worker_logs_dir: Absolute directory for worker log and PID file (optional).

        Returns:
            WorkerStartResult.
        """
        return self._lifecycle.start_vectorization_worker(
            db_path=db_path,
            faiss_dir=faiss_dir,
            vector_dim=vector_dim,
            svo_config=svo_config,
            batch_size=batch_size,
            poll_interval=poll_interval,
            worker_log_path=worker_log_path,
            worker_logs_dir=worker_logs_dir,
        )

    # Database driver methods
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

        Args:
            driver_config: Driver configuration dict with 'type' and 'config' keys.
            socket_path: Path to Unix socket for RPC communication (optional).
            log_path: Path to driver log file (optional).
            queue_max_size: Maximum size of request queue (default: 1000).

        Returns:
            WorkerStartResult.
        """
        return self._driver_manager.start_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=log_path,
            queue_max_size=queue_max_size,
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
        return self._driver_manager.stop_database_driver(timeout=timeout)

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

        Args:
            driver_config: Driver configuration dict with 'type' and 'config' keys.
            socket_path: Path to Unix socket for RPC communication (optional).
            log_path: Path to driver log file (optional).
            queue_max_size: Maximum size of request queue (default: 1000).
            timeout: Timeout in seconds for graceful shutdown of old driver.

        Returns:
            WorkerStartResult.
        """
        return self._driver_manager.restart_database_driver(
            driver_config=driver_config,
            socket_path=socket_path,
            log_path=log_path,
            queue_max_size=queue_max_size,
            timeout=timeout,
        )

    def get_database_driver_status(self) -> Dict[str, Any]:
        """
        Get status of database driver process.

        Returns:
            Dictionary with driver status information.
        """
        return self._driver_manager.get_database_driver_status()


# Global instance access
def get_worker_manager() -> WorkerManager:
    """
    Get global WorkerManager instance.

    Returns:
        WorkerManager instance
    """
    return WorkerManager.get_instance()
