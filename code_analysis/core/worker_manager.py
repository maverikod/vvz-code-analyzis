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
import multiprocessing
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

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


class WorkerManager:
    """
    Unified manager for all background workers.

    Responsibilities:
    - Register workers when they start
    - Track worker processes by type and PID
    - Gracefully shut down all workers on server shutdown
    """

    def _check_and_cleanup_pid_file(
        self,
        pid_file_path: Path,
        worker_type: str,
        process_name_pattern: Optional[str] = None,
    ) -> Optional[int]:
        """
        Check PID file and verify that process exists and is the correct worker.

        If PID file exists:
        1. Read PID from file
        2. Check if process with that PID exists
        3. Optionally verify process name matches pattern
        4. If process doesn't exist or doesn't match, remove stale PID file
        5. Return PID if process is alive and valid, None otherwise

        Args:
            pid_file_path: Path to PID file
            worker_type: Worker type for logging
            process_name_pattern: Optional pattern to match in process cmdline
                                 (e.g., "vectorization" or "file_watcher")

        Returns:
            PID if process is alive and valid, None if PID file should be ignored
        """
        if not pid_file_path.exists():
            return None

        try:
            with open(pid_file_path, "r") as f:
                pid = int(f.read().strip())
        except (ValueError, IOError) as e:
            logger.warning(
                f"Error reading PID file {pid_file_path} for {worker_type}: {e}, removing stale file"
            )
            try:
                pid_file_path.unlink()
            except Exception:
                pass
            return None

        # Check if process exists
        try:
            os.kill(pid, 0)  # Signal 0 just checks if process exists
        except OSError:
            # Process doesn't exist, remove stale PID file
            logger.info(
                f"Process {pid} from PID file {pid_file_path} doesn't exist, removing stale file"
            )
            try:
                pid_file_path.unlink()
            except Exception:
                pass
            return None

        # Optionally verify process name matches expected pattern
        if process_name_pattern:
            try:
                import psutil

                process = psutil.Process(pid)
                cmdline = " ".join(process.cmdline())
                if process_name_pattern.lower() not in cmdline.lower():
                    logger.warning(
                        f"Process {pid} exists but doesn't match pattern '{process_name_pattern}', "
                        f"removing stale PID file. Cmdline: {cmdline}"
                    )
                    try:
                        pid_file_path.unlink()
                    except Exception:
                        pass
                    return None
            except (psutil.NoSuchProcess, psutil.AccessDenied, ImportError) as e:
                # Process disappeared, psutil not available, or access denied
                # If psutil not available, skip name check but keep PID
                if isinstance(e, ImportError):
                    logger.debug(
                        f"psutil not available, skipping process name verification for {worker_type}"
                    )
                    return pid
                # Process disappeared or access denied - remove stale PID file
                logger.info(
                    f"Process {pid} from PID file {pid_file_path} is not accessible, removing stale file"
                )
                try:
                    pid_file_path.unlink()
                except Exception:
                    pass
                return None

        # Process exists and matches (if pattern provided)
        logger.debug(
            f"Process {pid} from PID file {pid_file_path} is alive and valid for {worker_type}"
        )
        return pid

    _instance: Optional["WorkerManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialize worker manager."""
        self._workers: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._shutdown_requested = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop_event = threading.Event()
        self._monitor_interval = 30.0  # Check every 30 seconds

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

    def register_worker(
        self,
        worker_type: str,
        process_info: Dict[str, Any],
    ) -> None:
        """
        Register a worker with the manager.

        Args:
            worker_type: Type of worker (e.g., 'vectorization', 'file_watcher', 'repair', 'sqlite_queue')
            process_info: Dictionary with worker information:
                - pid: Process ID (required for process-based workers)
                - process: multiprocessing.Process object (optional)
                - queue_system: AsyncQueueSystem object (optional, for queue-based workers)
                - worker: Worker instance (optional)
                - name: Human-readable name (optional)
                - restart_func: Function to restart worker (optional, for auto-restart)
                - restart_args: Arguments for restart function (optional)
                - restart_kwargs: Keyword arguments for restart function (optional)
        """
        with self._lock:
            if worker_type not in self._workers:
                self._workers[worker_type] = []

            # Add registration timestamp
            process_info["registered_at"] = time.time()
            self._workers[worker_type].append(process_info)

            pid = process_info.get("pid")
            name = process_info.get("name", worker_type)
            logger.info(f"Registered {worker_type} worker: {name} (PID: {pid})")

    def unregister_worker(self, worker_type: str, pid: Optional[int] = None) -> None:
        """
        Unregister a worker from the manager.

        Args:
            worker_type: Type of worker
            pid: Process ID (if None, removes all workers of this type)
        """
        with self._lock:
            if worker_type not in self._workers:
                return

            if pid is None:
                # Remove all workers of this type
                removed = len(self._workers[worker_type])
                self._workers[worker_type] = []
                logger.info(
                    f"Unregistered all {worker_type} workers ({removed} workers)"
                )
            else:
                # Remove specific worker by PID
                original_count = len(self._workers[worker_type])
                self._workers[worker_type] = [
                    w for w in self._workers[worker_type] if w.get("pid") != pid
                ]
                removed = original_count - len(self._workers[worker_type])
                if removed > 0:
                    logger.info(f"Unregistered {worker_type} worker (PID: {pid})")

    def get_worker_status(self) -> Dict[str, Any]:
        """
        Get status of all registered workers.

        Returns:
            Dictionary with worker status information
        """
        with self._lock:
            status = {
                "total_workers": 0,
                "by_type": {},
                "workers": [],
            }

            for worker_type, workers in self._workers.items():
                type_status = {
                    "count": len(workers),
                    "pids": [],
                    "names": [],
                }

                for worker_info in workers:
                    pid = worker_info.get("pid")
                    name = worker_info.get("name", worker_type)
                    process = worker_info.get("process")
                    queue_system = worker_info.get("queue_system")

                    # Check if process is still alive
                    is_alive = False
                    if process:
                        is_alive = process.is_alive()
                    elif pid:
                        try:
                            import psutil

                            proc = psutil.Process(pid)
                            is_alive = proc.is_running()
                        except Exception:
                            is_alive = False
                    elif queue_system:
                        is_alive = queue_system.is_running()

                    worker_status = {
                        "type": worker_type,
                        "pid": pid,
                        "name": name,
                        "alive": is_alive,
                        "registered_at": worker_info.get("registered_at"),
                    }

                    status["workers"].append(worker_status)
                    type_status["pids"].append(pid)
                    type_status["names"].append(name)
                    status["total_workers"] += 1

                status["by_type"][worker_type] = type_status

            return status

    def stop_worker_type(
        self, worker_type: str, timeout: float = 10.0
    ) -> Dict[str, Any]:
        """
        Stop all workers of a specific type.

        Args:
            worker_type: Type of worker to stop
            timeout: Timeout in seconds for graceful shutdown

        Returns:
            Dictionary with stop results
        """
        with self._lock:
            if worker_type not in self._workers:
                return {
                    "success": True,
                    "message": f"No {worker_type} workers to stop",
                    "stopped": 0,
                }

            workers = self._workers[worker_type].copy()
            result = {
                "success": True,
                "stopped": 0,
                "failed": 0,
                "errors": [],
            }

            for worker_info in workers:
                try:
                    pid = worker_info.get("pid")
                    process = worker_info.get("process")
                    queue_system = worker_info.get("queue_system")
                    worker = worker_info.get("worker")
                    name = worker_info.get("name", worker_type)

                    # Stop based on type
                    if queue_system:
                        # Async queue system
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # Schedule shutdown
                                asyncio.create_task(queue_system.stop())
                            else:
                                loop.run_until_complete(queue_system.stop())
                            logger.info(f"Stopped {worker_type} queue system: {name}")
                            result["stopped"] += 1
                        except Exception as e:
                            error_msg = (
                                f"Failed to stop {worker_type} queue system {name}: {e}"
                            )
                            logger.error(error_msg)
                            result["errors"].append(error_msg)
                            result["failed"] += 1

                    elif process:
                        # Multiprocessing process
                        # NOTE:
                        # In some cases (e.g. queue worker / forked process) we can have a
                        # multiprocessing.Process object created in a different parent PID.
                        # Calling process.is_alive()/terminate() then raises:
                        #   AssertionError: can only test a child process
                        # In that case, fall back to PID-based termination via psutil.
                        try:
                            is_alive = process.is_alive()
                        except AssertionError:
                            is_alive = None

                        if is_alive is None:
                            # Fall back to PID-based termination if we have PID.
                            if pid:
                                try:
                                    import psutil

                                    proc = psutil.Process(pid)
                                    if proc.is_running():
                                        proc.terminate()
                                        try:
                                            proc.wait(timeout=timeout)
                                            logger.info(
                                                f"Stopped {worker_type} process via PID fallback: {name} (PID: {pid})"
                                            )
                                        except (psutil.TimeoutExpired, Exception):
                                            # Force kill if still running after timeout
                                            proc.kill()
                                            try:
                                                proc.wait(timeout=2.0)
                                            except psutil.TimeoutExpired:
                                                logger.error(
                                                    f"CRITICAL: {worker_type} process {name} (PID: {pid}) did not die after SIGKILL via PID fallback"
                                                )
                                            logger.warning(
                                                f"Force killed {worker_type} process via PID fallback after timeout: {name} (PID: {pid})"
                                            )
                                    result["stopped"] += 1
                                except Exception as e:
                                    error_msg = f"Failed to stop {worker_type} process via PID fallback {name} (PID: {pid}): {e}"
                                    logger.error(error_msg)
                                    result["errors"].append(error_msg)
                                    result["failed"] += 1
                            else:
                                error_msg = f"Cannot stop {worker_type} process {name}: Process handle is not valid in this PID and PID is missing"
                                logger.error(error_msg)
                                result["errors"].append(error_msg)
                                result["failed"] += 1

                        elif is_alive:
                            try:
                                # Send SIGTERM for graceful shutdown
                                process.terminate()
                                logger.info(
                                    f"Sent SIGTERM to {worker_type} worker {name} (PID: {pid})"
                                )

                                # Wait for graceful shutdown with timeout
                                process.join(timeout=timeout)

                                try:
                                    still_alive = process.is_alive()
                                except AssertionError:
                                    still_alive = None

                                if still_alive is None:
                                    # Parent mismatch surfaced after terminate/join. Use PID fallback.
                                    if pid:
                                        import psutil

                                        proc = psutil.Process(pid)
                                        if proc.is_running():
                                            proc.terminate()
                                            try:
                                                proc.wait(timeout=timeout)
                                                logger.info(
                                                    f"Stopped {worker_type} process via PID fallback after parent mismatch: {name} (PID: {pid})"
                                                )
                                            except (psutil.TimeoutExpired, Exception):
                                                # Force kill if still running after timeout
                                                proc.kill()
                                                try:
                                                    proc.wait(timeout=2.0)
                                                except psutil.TimeoutExpired:
                                                    logger.error(
                                                        f"CRITICAL: {worker_type} process {name} (PID: {pid}) did not die after SIGKILL via PID fallback (parent mismatch)"
                                                    )
                                                logger.warning(
                                                    f"Force killed {worker_type} process via PID fallback after timeout: {name} (PID: {pid})"
                                                )
                                        result["stopped"] += 1
                                    else:
                                        raise RuntimeError(
                                            "Cannot stop process: parent mismatch and PID missing"
                                        )

                                elif still_alive:
                                    # Force kill if still alive after timeout
                                    logger.warning(
                                        f"{worker_type} worker {name} (PID: {pid}) did not stop within {timeout}s, sending SIGKILL"
                                    )
                                    process.kill()
                                    process.join(
                                        timeout=2.0
                                    )  # Wait up to 2s for kill to take effect

                                # Verify process is actually dead - use multiple methods
                                process_dead = False
                                try:
                                    is_alive_after = process.is_alive()
                                    if is_alive_after is False:
                                        process_dead = True
                                except AssertionError:
                                    # Process handle invalid - check via PID
                                    is_alive_after = None

                                # If process handle says it's dead, we're done
                                if process_dead:
                                    logger.info(
                                        f"Stopped {worker_type} process: {name} (PID: {pid})"
                                    )
                                    result["stopped"] += 1
                                elif is_alive_after is None:
                                    # Process handle invalid - verify via PID
                                    if pid:
                                        try:
                                            import psutil

                                            proc = psutil.Process(pid)
                                            if proc.is_running():
                                                # Still running - force kill via PID
                                                proc.kill()
                                                try:
                                                    proc.wait(timeout=2.0)
                                                except psutil.TimeoutExpired:
                                                    logger.error(
                                                        f"CRITICAL: {worker_type} process {name} (PID: {pid}) did not die after SIGKILL"
                                                    )
                                                logger.warning(
                                                    f"Force killed {worker_type} process via PID fallback: {name} (PID: {pid})"
                                                )
                                            result["stopped"] += 1
                                        except (
                                            psutil.NoSuchProcess,
                                            psutil.AccessDenied,
                                        ):
                                            # Process is dead or we can't access it
                                            result["stopped"] += 1
                                        except Exception as e:
                                            error_msg = f"Failed to verify/kill {worker_type} process via PID {name} (PID: {pid}): {e}"
                                            logger.error(error_msg)
                                            result["errors"].append(error_msg)
                                            result["failed"] += 1
                                    else:
                                        # No PID available - treat as stopped
                                        logger.info(
                                            f"Stopped {worker_type} process (parent handle invalid, no PID): {name}"
                                        )
                                        result["stopped"] += 1
                                else:
                                    # Process handle says it's still alive - force kill via PID
                                    if pid:
                                        try:
                                            import psutil

                                            proc = psutil.Process(pid)
                                            if proc.is_running():
                                                proc.kill()
                                                try:
                                                    proc.wait(timeout=2.0)
                                                except psutil.TimeoutExpired:
                                                    logger.error(
                                                        f"CRITICAL: {worker_type} process {name} (PID: {pid}) did not die after SIGKILL"
                                                    )
                                                logger.warning(
                                                    f"Force killed {worker_type} process via PID after process.kill() failed: {name} (PID: {pid})"
                                                )
                                            result["stopped"] += 1
                                        except (
                                            psutil.NoSuchProcess,
                                            psutil.AccessDenied,
                                        ):
                                            # Process is dead or we can't access it
                                            result["stopped"] += 1
                                        except Exception as e:
                                            error_msg = f"Failed to kill {worker_type} process via PID {name} (PID: {pid}): {e}"
                                            logger.error(error_msg)
                                            result["errors"].append(error_msg)
                                            result["failed"] += 1
                                    else:
                                        error_msg = f"Cannot kill {worker_type} process {name}: process still alive but no PID available"
                                        logger.error(error_msg)
                                        result["errors"].append(error_msg)
                                        result["failed"] += 1
                            except Exception as e:
                                error_msg = f"Failed to stop {worker_type} process {name} (PID: {pid}): {e}"
                                logger.error(error_msg)
                                result["errors"].append(error_msg)
                                result["failed"] += 1
                        else:
                            result["stopped"] += 1

                    elif worker:
                        # Worker instance with stop method
                        try:
                            if hasattr(worker, "stop"):
                                worker.stop()
                            logger.info(f"Stopped {worker_type} worker: {name}")
                            result["stopped"] += 1
                        except Exception as e:
                            error_msg = (
                                f"Failed to stop {worker_type} worker {name}: {e}"
                            )
                            logger.error(error_msg)
                            result["errors"].append(error_msg)
                            result["failed"] += 1

                    elif pid:
                        # Direct PID
                        try:
                            import psutil

                            proc = psutil.Process(pid)
                            if proc.is_running():
                                proc.terminate()
                                try:
                                    proc.wait(timeout=timeout)
                                    logger.info(
                                        f"Stopped {worker_type} process (PID: {pid})"
                                    )
                                    result["stopped"] += 1
                                except (psutil.TimeoutExpired, Exception):
                                    # Force kill if still running after timeout
                                    proc.kill()
                                    try:
                                        proc.wait(timeout=2.0)
                                    except psutil.TimeoutExpired:
                                        logger.error(
                                            f"CRITICAL: {worker_type} process (PID: {pid}) did not die after SIGKILL"
                                        )
                                    logger.warning(
                                        f"Force killed {worker_type} process (PID: {pid}) after timeout"
                                    )
                                    result["stopped"] += 1
                            else:
                                result["stopped"] += 1
                        except Exception as e:
                            error_msg = f"Failed to stop {worker_type} process (PID: {pid}): {e}"
                            logger.error(error_msg)
                            result["errors"].append(error_msg)
                            result["failed"] += 1

                except Exception as e:
                    error_msg = f"Error stopping {worker_type} worker: {e}"
                    logger.error(error_msg, exc_info=True)
                    result["errors"].append(error_msg)
                    result["failed"] += 1

            # Remove stopped workers from registry
            self._workers[worker_type] = []

            result["success"] = result["failed"] == 0
            result["message"] = (
                f"Stopped {result['stopped']} {worker_type} worker(s), "
                f"{result['failed']} failed"
            )

            return result

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

        with self._lock:
            worker_types = list(self._workers.keys())

        results = {}
        total_stopped = 0
        total_failed = 0
        all_errors = []

        for worker_type in worker_types:
            result = self.stop_worker_type(worker_type, timeout=timeout)
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

    def start_monitoring(self, interval: float = 30.0) -> None:
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

    def stop_monitoring(self, timeout: float = 10.0) -> None:
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
        with self._lock:
            workers_to_check = {}
            for worker_type, workers in self._workers.items():
                workers_to_check[worker_type] = workers.copy()

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
                        self.unregister_worker(worker_type, pid)

                        # Restart if restart function is available
                        if restart_func:
                            try:
                                logger.info(
                                    f"Restarting {worker_type} worker {name}..."
                                )
                                new_worker_info = restart_func(
                                    *restart_args, **restart_kwargs
                                )
                                if new_worker_info:
                                    self.register_worker(worker_type, new_worker_info)
                                    logger.info(
                                        f"Successfully restarted {worker_type} worker {name} "
                                        f"(new PID: {new_worker_info.get('pid')})"
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

    def start_file_watcher_worker(
        self,
        *,
        db_path: str,
        watch_dirs: List[Dict[str, str]],
        locks_dir: str,
        scan_interval: int = 60,
        version_dir: Optional[str] = None,
        worker_log_path: Optional[str] = None,
        ignore_patterns: Optional[List[str]] = None,
    ) -> WorkerStartResult:
        """
        Start file watcher worker in a separate process and register it.

        Projects are discovered automatically within each watch_dir by finding
        projectid files. Multiple projects can exist in one watch_dir.

        CRITICAL: Uses multiprocessing.Process, not threading.Thread or async.
        This ensures workers don't conflict with Hypercorn's event loop.

        Args:
            db_path: Path to database file.
            watch_dirs: List of watch directory configs with 'id' and 'path' keys.
                       Format: [{'id': 'uuid4', 'path': '/absolute/path'}]
            locks_dir: Service state directory for lock files (from StoragePaths).
            scan_interval: Scan interval seconds.
            version_dir: Version directory for deleted files.
            worker_log_path: Log path for worker process.
            ignore_patterns: Optional ignore patterns.

        Returns:
            WorkerStartResult.
        """
        from .file_watcher_pkg.runner import run_file_watcher_worker

        # PID file check (before starting worker)
        pid_file_path = Path("logs") / "file_watcher_worker.pid"
        existing_pid = self._check_and_cleanup_pid_file(
            pid_file_path, "file_watcher", "file_watcher"
        )
        if existing_pid is not None:
            # Process is alive, worker already running
            return WorkerStartResult(
                success=False,
                worker_type="file_watcher",
                pid=existing_pid,
                message="File watcher worker already running",
            )

        # Create process (NOT thread, NOT async task)
        process = multiprocessing.Process(
            target=run_file_watcher_worker,
            args=(db_path, watch_dirs),
            kwargs={
                "locks_dir": locks_dir,
                "scan_interval": int(scan_interval),
                "version_dir": version_dir,
                "worker_log_path": worker_log_path,
                "ignore_patterns": ignore_patterns or [],
            },
            daemon=True,  # Daemon process for background workers
        )
        process.start()

        # Write PID file after worker starts
        try:
            pid_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pid_file_path, "w") as f:
                f.write(str(process.pid))
        except Exception as e:
            logger.warning(f"Failed to write PID file: {e}")

        # Use first watch_dir as identifier for worker name
        first_watch_dir = watch_dirs[0] if watch_dirs else {}
        first_path = (
            first_watch_dir.get("path", "default")
            if isinstance(first_watch_dir, dict)
            else str(first_watch_dir)
        )
        worker_name = f"file_watcher_{Path(first_path).name}"
        self.register_worker(
            "file_watcher",
            {"pid": process.pid, "process": process, "name": worker_name},
        )
        return WorkerStartResult(
            success=True,
            worker_type="file_watcher",
            pid=process.pid,
            message=f"File watcher started (PID {process.pid})",
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
    ) -> WorkerStartResult:
        """
        Start universal vectorization worker in a separate process and register it.

        Worker operates in universal mode - processes all projects from database.
        Worker works only with database - no filesystem access, no watch_dirs.

        CRITICAL: Uses multiprocessing.Process, not threading.Thread or async.
        This ensures workers don't conflict with Hypercorn's event loop.

        Args:
            db_path: Path to database file.
            faiss_dir: Base directory for FAISS index files (project-scoped indexes: {faiss_dir}/{project_id}.bin).
            vector_dim: Embedding vector dimension.
            svo_config: Optional SVO config dict.
            batch_size: Batch size.
            poll_interval: Poll interval seconds.
            worker_log_path: Log path for worker process.

        Returns:
            WorkerStartResult.
        """
        from .vectorization_worker_pkg.runner import run_vectorization_worker

        # PID file check (before starting worker)
        pid_file_path = Path("logs") / "vectorization_worker.pid"
        existing_pid = self._check_and_cleanup_pid_file(
            pid_file_path, "vectorization", "vectorization"
        )
        if existing_pid is not None:
            # Process is alive, worker already running
            return WorkerStartResult(
                success=False,
                worker_type="vectorization",
                pid=existing_pid,
                message="Vectorization worker already running",
            )

        # Create process (NOT thread, NOT async task)
        process = multiprocessing.Process(
            target=run_vectorization_worker,
            args=(db_path, faiss_dir, int(vector_dim)),
            kwargs={
                "svo_config": svo_config,
                "batch_size": int(batch_size),
                "poll_interval": int(poll_interval),
                "worker_log_path": worker_log_path,
            },
            daemon=True,  # Daemon process for background workers
        )
        process.start()

        # Write PID file after worker starts
        try:
            pid_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pid_file_path, "w") as f:
                f.write(str(process.pid))
        except Exception as e:
            logger.warning(f"Failed to write PID file: {e}")

        self.register_worker(
            "vectorization",
            {"pid": process.pid, "process": process, "name": "vectorization_universal"},
        )
        return WorkerStartResult(
            success=True,
            worker_type="vectorization",
            pid=process.pid,
            message=f"Vectorization worker started (PID {process.pid})",
        )

    def start_database_driver(
        self,
        *,
        driver_config: Dict[str, Any],
        socket_path: Optional[str] = None,
        log_path: Optional[str] = None,
        queue_max_size: int = 1000,
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

        # Generate socket path if not provided
        if not socket_path:
            # Use driver config path to generate socket path
            driver_cfg = driver_config.get("config", {})
            db_path = driver_cfg.get("path")
            if db_path:
                # Generate socket path similar to db_worker_manager
                db_name = Path(db_path).stem
                socket_dir = Path("/tmp/code_analysis_db_drivers")
                socket_dir.mkdir(parents=True, exist_ok=True)
                socket_path = str(socket_dir / f"{db_name}_driver.sock")
            else:
                # Fallback to driver type
                socket_dir = Path("/tmp/code_analysis_db_drivers")
                socket_dir.mkdir(parents=True, exist_ok=True)
                socket_path = str(socket_dir / f"{driver_type}_driver.sock")

        # PID file check (before starting driver)
        pid_file_path = Path("logs") / "database_driver.pid"
        existing_pid = self._check_and_cleanup_pid_file(
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
        process = multiprocessing.Process(
            target=run_database_driver,
            args=(driver_type, driver_config.get("config", {})),
            kwargs={
                "socket_path": socket_path,
                "log_path": log_path,
                "queue_max_size": queue_max_size,
            },
            daemon=False,  # NOT daemon - driver process should persist
        )
        process.start()

        # Write PID file after driver starts
        try:
            pid_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pid_file_path, "w") as f:
                f.write(str(process.pid))
        except Exception as e:
            logger.warning(f"Failed to write PID file: {e}")

        # Wait a bit for driver to initialize socket
        import time

        time.sleep(0.5)

        # Verify socket file exists
        socket_file = Path(socket_path)
        if not socket_file.exists():
            # Wait a bit more for socket creation
            time.sleep(0.5)
            if not socket_file.exists():
                logger.warning(
                    f"Database driver socket not created: {socket_path}, but process started (PID: {process.pid})"
                )

        worker_name = f"database_driver_{driver_type}"
        self.register_worker(
            "database_driver",
            {
                "pid": process.pid,
                "process": process,
                "name": worker_name,
                "driver_type": driver_type,
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

    def stop_database_driver(self, timeout: float = 10.0) -> Dict[str, Any]:
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
        queue_max_size: int = 1000,
        timeout: float = 10.0,
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
        import time

        time.sleep(0.5)

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
        with self._lock:
            if "database_driver" not in self._workers:
                return {
                    "running": False,
                    "pid": None,
                    "socket_path": None,
                    "driver_type": None,
                    "message": "Database driver not running",
                }

            workers = self._workers["database_driver"]
            if not workers:
                return {
                    "running": False,
                    "pid": None,
                    "socket_path": None,
                    "driver_type": None,
                    "message": "Database driver not running",
                }

            # Get first worker (should be only one)
            worker_info = workers[0]
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


# Global instance access
def get_worker_manager() -> WorkerManager:
    """
    Get global WorkerManager instance.

    Returns:
        WorkerManager instance
    """
    return WorkerManager.get_instance()
