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
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkerManager:
    """
    Unified manager for all background workers.

    Responsibilities:
    - Register workers when they start
    - Track worker processes by type and PID
    - Gracefully shut down all workers on server shutdown
    - Provide status information about all workers
    """

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
                                        except Exception:
                                            proc.kill()
                                    logger.info(
                                        f"Stopped {worker_type} process via PID fallback: {name} (PID: {pid})"
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
                                logger.info(f"Sent SIGTERM to {worker_type} worker {name} (PID: {pid})")
                                
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
                                            except Exception:
                                                # Force kill if still running after timeout
                                                proc.kill()
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
                                    process.join(timeout=1.0)
                                    logger.warning(
                                        f"Force killed {worker_type} process: {name} (PID: {pid})"
                                    )

                                try:
                                    is_alive_after = process.is_alive()
                                except AssertionError:
                                    is_alive_after = None

                                if is_alive_after is False:
                                    logger.info(
                                        f"Stopped {worker_type} process: {name} (PID: {pid})"
                                    )
                                    result["stopped"] += 1
                                elif is_alive_after is None:
                                    # Treat as stopped: we no longer have a valid parent handle here.
                                    logger.info(
                                        f"Stopped {worker_type} process (parent handle invalid in this PID): {name} (PID: {pid})"
                                    )
                                    result["stopped"] += 1
                                else:
                                    # Still alive after kill - try PID-based kill
                                    if pid:
                                        try:
                                            import psutil
                                            proc = psutil.Process(pid)
                                            if proc.is_running():
                                                proc.kill()
                                                logger.warning(
                                                    f"Force killed {worker_type} process via PID after kill failed: {name} (PID: {pid})"
                                                )
                                            result["stopped"] += 1
                                        except Exception:
                                            raise RuntimeError(
                                                f"Process {pid} still alive after kill"
                                            )
                                    else:
                                        raise RuntimeError(
                                            f"Process {pid} still alive after kill"
                                        )
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
                                except Exception:
                                    proc.kill()
                                    logger.warning(
                                        f"Force killed {worker_type} process (PID: {pid})"
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
                                logger.info(f"Restarting {worker_type} worker {name}...")
                                new_worker_info = restart_func(*restart_args, **restart_kwargs)
                                if new_worker_info:
                                    self.register_worker(worker_type, new_worker_info)
                                    logger.info(
                                        f"Successfully restarted {worker_type} worker {name} "
                                        f"(new PID: {new_worker_info.get('pid')})"
                                    )
                                else:
                                    logger.error(f"Failed to restart {worker_type} worker {name}: restart function returned None")
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


# Global instance access
def get_worker_manager() -> WorkerManager:
    """
    Get global WorkerManager instance.

    Returns:
        WorkerManager instance
    """
    return WorkerManager.get_instance()
