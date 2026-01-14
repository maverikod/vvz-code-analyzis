"""
Worker registry for managing worker registration and status.

This module handles registration, unregistration, and status tracking
of all worker processes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkerRegistry:
    """
    Registry for managing worker registration and status.

    Responsibilities:
    - Register and unregister workers
    - Track worker status
    - Check and cleanup PID files
    """

    def __init__(self):
        """Initialize worker registry."""
        self._workers: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def check_and_cleanup_pid_file(
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

    def register_worker(
        self,
        worker_type: str,
        process_info: Dict[str, Any],
    ) -> None:
        """
        Register a worker with the registry.

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
        Unregister a worker from the registry.

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

    def get_workers(
        self, worker_type: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get workers dictionary.

        Args:
            worker_type: Optional worker type to filter by (returns all if None)

        Returns:
            Dictionary of workers (filtered by type if specified)
        """
        with self._lock:
            if worker_type is None:
                return self._workers.copy()
            return {worker_type: self._workers.get(worker_type, []).copy()}

    def clear_workers(self, worker_type: str) -> None:
        """
        Clear all workers of a specific type.

        Args:
            worker_type: Type of worker to clear
        """
        with self._lock:
            if worker_type in self._workers:
                self._workers[worker_type] = []
