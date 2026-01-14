"""
Worker monitor for monitoring and auto-restarting workers.

This module handles background monitoring of worker processes
and automatic restart of dead workers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import threading
from typing import Any, Callable, Optional

from .constants import DEFAULT_WORKER_MONITOR_INTERVAL, DEFAULT_WORKER_STOP_TIMEOUT

logger = logging.getLogger(__name__)


class WorkerMonitor:
    """
    Monitor for worker processes with auto-restart capability.

    Responsibilities:
    - Monitor worker processes in background thread
    - Detect dead workers
    - Auto-restart dead workers if restart function is provided
    """

    def __init__(
        self, registry: Any, unregister_callback: Callable, register_callback: Callable
    ):
        """
        Initialize worker monitor.

        Args:
            registry: Worker registry instance
            unregister_callback: Callback function to unregister worker
            register_callback: Callback function to register worker
        """
        self.registry = registry
        self.unregister_callback = unregister_callback
        self.register_callback = register_callback
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop_event = threading.Event()
        self._monitor_interval = DEFAULT_WORKER_MONITOR_INTERVAL
        self._shutdown_requested = False

    def start_monitoring(
        self, interval: float = DEFAULT_WORKER_MONITOR_INTERVAL
    ) -> None:
        """
        Start background thread to monitor worker processes and restart dead ones.

        Args:
            interval: Check interval in seconds (default: 30.0)
        """
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            logger.warning("Worker monitoring thread is already running")
            return

        self._monitor_stop_event.clear()
        self._monitor_interval = interval
        self._monitor_thread = threading.Thread(
            target=self._monitor_workers_loop,
            name="WorkerMonitor",
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info(f"Started worker monitoring thread (check interval: {interval}s)")

    def stop_monitoring(self, timeout: float = DEFAULT_WORKER_STOP_TIMEOUT) -> None:
        """
        Stop worker monitoring thread.

        Args:
            timeout: Timeout in seconds to wait for thread to stop
        """
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            return

        logger.info("Stopping worker monitoring thread...")
        self._monitor_stop_event.set()
        self._monitor_thread.join(timeout=timeout)

        if self._monitor_thread.is_alive():
            logger.warning("Worker monitoring thread did not stop within timeout")
        else:
            logger.info("Worker monitoring thread stopped")

    def set_shutdown_requested(self, value: bool) -> None:
        """
        Set shutdown requested flag.

        Args:
            value: True if shutdown is requested
        """
        self._shutdown_requested = value

    def _monitor_workers_loop(self) -> None:
        """Background loop to monitor worker processes."""
        logger.info("Worker monitoring loop started")

        while not self._monitor_stop_event.is_set():
            try:
                if self._shutdown_requested:
                    break

                self._check_and_restart_workers()

                # Wait for interval or stop event
                if self._monitor_stop_event.wait(timeout=self._monitor_interval):
                    break

            except Exception as e:
                logger.error(f"Error in worker monitoring loop: {e}", exc_info=True)
                # Wait a bit before retrying
                if self._monitor_stop_event.wait(timeout=5.0):
                    break

        logger.info("Worker monitoring loop stopped")

    def _check_and_restart_workers(self) -> None:
        """Check all workers and restart dead ones."""
        workers_to_check = self.registry.get_workers()

        for worker_type, workers in workers_to_check.items():
            for worker_info in workers:
                try:
                    pid = worker_info.get("pid")
                    process = worker_info.get("process")
                    name = worker_info.get("name", worker_type)
                    restart_func = worker_info.get("restart_func")
                    restart_args = worker_info.get("restart_args", ())
                    restart_kwargs = worker_info.get("restart_kwargs", {})

                    # Check if process is alive
                    is_alive = False
                    if process:
                        try:
                            is_alive = process.is_alive()
                        except (ValueError, AssertionError):
                            # Process handle invalid, check by PID
                            is_alive = False

                    if not is_alive and pid:
                        try:
                            import psutil

                            proc = psutil.Process(pid)
                            is_alive = proc.is_running()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            is_alive = False

                    if not is_alive:
                        logger.warning(
                            f"Worker {worker_type} {name} (PID: {pid}) is dead, attempting restart..."
                        )

                        # Unregister dead worker
                        self.unregister_callback(worker_type, pid)

                        # Restart if restart function is available
                        if restart_func:
                            try:
                                logger.info(
                                    f"Restarting {worker_type} worker {name}..."
                                )
                                restart_result = restart_func(
                                    *restart_args, **restart_kwargs
                                )
                                
                                # Check if restart was successful
                                # restart_func may return WorkerStartResult or Dict[str, Any]
                                if restart_result:
                                    # Check if it's a WorkerStartResult (has 'success' attribute)
                                    if hasattr(restart_result, 'success'):
                                        # WorkerStartResult - worker already registered in start method
                                        if restart_result.success:
                                            logger.info(
                                                f"Successfully restarted {worker_type} worker {name} "
                                                f"(new PID: {restart_result.pid})"
                                            )
                                        else:
                                            logger.error(
                                                f"Failed to restart {worker_type} worker {name}: {restart_result.message}"
                                            )
                                    elif isinstance(restart_result, dict):
                                        # Dict[str, Any] - need to register manually
                                        self.register_callback(worker_type, restart_result)
                                        new_pid = restart_result.get('pid')
                                        logger.info(
                                            f"Successfully restarted {worker_type} worker {name} "
                                            f"(new PID: {new_pid})"
                                        )
                                    else:
                                        logger.error(
                                            f"Unexpected return type from restart function for {worker_type} worker {name}: {type(restart_result)}"
                                        )
                                else:
                                    logger.error(
                                        f"Failed to restart {worker_type} worker {name}: restart function returned None"
                                    )
                            except Exception as e:
                                logger.error(
                                    f"Failed to restart {worker_type} worker {name}: {e}",
                                    exc_info=True,
                                )
                        else:
                            logger.warning(
                                f"Cannot restart {worker_type} worker {name}: no restart function provided"
                            )

                except Exception as e:
                    logger.error(
                        f"Error checking {worker_type} worker: {e}",
                        exc_info=True,
                    )
