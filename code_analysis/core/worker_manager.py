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
import os
import signal
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import multiprocessing
    from queuemgr.async_simple_api import AsyncQueueSystem

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
                        if process.is_alive():
                            try:
                                # Try using process.terminate() first (standard library)
                                process.terminate()
                                process.join(timeout=timeout)

                                if process.is_alive():
                                    # Force kill if still alive
                                    process.kill()
                                    process.join(timeout=1.0)
                                    logger.warning(
                                        f"Force killed {worker_type} process: {name} (PID: {pid})"
                                    )

                                if not process.is_alive():
                                    logger.info(
                                        f"Stopped {worker_type} process: {name} (PID: {pid})"
                                    )
                                    result["stopped"] += 1
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


# Global instance access
def get_worker_manager() -> WorkerManager:
    """
    Get global WorkerManager instance.

    Returns:
        WorkerManager instance
    """
    return WorkerManager.get_instance()
