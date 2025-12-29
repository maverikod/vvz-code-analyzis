"""
Global DB worker manager.

Manages a single DB worker process per database path, shared across all connections.
The worker is started from the main process (not daemon) to avoid "daemonic processes
are not allowed to have children" error.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import multiprocessing
import threading
import time
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .db_worker_pkg.runner import run_db_worker

logger = logging.getLogger(__name__)


class DBWorkerManager:
    """
    Global manager for DB worker processes.

    Ensures only one worker process per database path is running,
    shared across all connections. Workers are started with daemon=False
    to allow them to be created from any process.
    
    Uses file-based coordination for cross-process communication:
    - PID files to track worker processes
    - Unix sockets for client-server communication
    """

    _instance: Optional["DBWorkerManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialize DB worker manager."""
        self._workers: Dict[str, Dict[str, Any]] = {}  # db_path -> worker info (main process only)
        self._lock = threading.Lock()
        self._pid_file_dir = Path("/tmp/code_analysis_db_workers")
        self._pid_file_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> "DBWorkerManager":
        """
        Get singleton instance of DBWorkerManager.

        Returns:
            DBWorkerManager instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_or_start_worker(
        self,
        db_path: str,
        worker_log_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get existing worker or start new one for database path.

        Args:
            db_path: Path to database file
            worker_log_path: Path to worker log file (optional)

        Returns:
            Dictionary with worker info:
                - socket_path: Path to Unix socket for communication
                - process: multiprocessing.Process object
                - pid: Process ID
        """
        db_path_str = str(Path(db_path).resolve())

        with self._lock:
            # Check if worker already exists and is alive
            if db_path_str in self._workers:
                worker_info = self._workers[db_path_str]
                process = worker_info.get("process")
                if process:
                    try:
                        if process.is_alive():
                            logger.debug(f"[DBWorkerManager] Using existing worker for {db_path_str}")
                            return worker_info
                    except (ValueError, AssertionError):
                        # Process not started or already terminated
                        pass
                    # Worker died, remove it
                    logger.warning(f"[DBWorkerManager] Worker for {db_path_str} died, removing")
                    del self._workers[db_path_str]

            # Check if we're in a daemon process - if so, we can't start new processes
            # In this case, we should only connect to existing worker
            import multiprocessing as mp
            current_process = mp.current_process()
            is_daemon = getattr(current_process, 'daemon', False)
            
            if is_daemon:
                # We're in a daemon process - can't start new processes
                # Try to find existing worker by checking if process with name exists
                # For now, raise error - worker should be started from main process
                raise RuntimeError(
                    f"Cannot start DB worker from daemon process. "
                    f"DB worker must be started from main process before daemon workers start. "
                    f"Database path: {db_path_str}"
                )

            # Start new worker
            logger.info(f"[DBWorkerManager] Starting new DB worker for {db_path_str}")

            # Generate unique socket path
            db_name = Path(db_path_str).stem
            socket_path = str(self._pid_file_dir / f"{db_name}.sock")

            # Start worker process (daemon=False to allow creation from any process)
            process = multiprocessing.Process(
                target=run_db_worker,
                args=(
                    db_path_str,
                    socket_path,
                    worker_log_path,
                ),
                name=f"DBWorker-{Path(db_path_str).name}",
                daemon=False,  # NOT daemon - can be started from any process
            )
            process.start()

            # Wait a bit for worker to initialize socket
            time.sleep(0.5)

            try:
                if not process.is_alive():
                    raise RuntimeError(f"DB worker process failed to start for {db_path_str}")
            except (ValueError, AssertionError):
                # Process not started or already terminated
                raise RuntimeError(f"DB worker process failed to start for {db_path_str}")

            # Verify socket file exists
            socket_file = Path(socket_path)
            if not socket_file.exists():
                # Wait a bit more for socket creation
                time.sleep(0.5)
                if not socket_file.exists():
                    raise RuntimeError(f"DB worker socket not created: {socket_path}")

            worker_info = {
                "socket_path": socket_path,
                "process": process,
                "pid": process.pid,
                "db_path": db_path_str,
            }

            self._workers[db_path_str] = worker_info
            
            # Write PID file for cross-process coordination
            pid_file = self._pid_file_dir / f"{Path(db_path_str).name}.pid"
            pid_file.write_text(str(process.pid))
            
            logger.info(
                f"[DBWorkerManager] DB worker started for {db_path_str} (PID: {process.pid}, socket: {socket_path})"
            )

            return worker_info

    def stop_worker(self, db_path: str) -> None:
        """
        Stop worker for database path.

        Args:
            db_path: Path to database file
        """
        db_path_str = str(Path(db_path).resolve())

        with self._lock:
            if db_path_str not in self._workers:
                return

            worker_info = self._workers[db_path_str]
            process = worker_info.get("process")

            if process:
                try:
                    is_alive = process.is_alive()
                except (ValueError, AssertionError):
                    is_alive = False
                
                if is_alive:
                    logger.info(f"[DBWorkerManager] Stopping DB worker for {db_path_str}")
                    # Send SIGTERM for graceful shutdown
                    try:
                        process.terminate()
                    except Exception:
                        pass

                    # Wait for graceful shutdown
                    process.join(timeout=5.0)

                    # Force terminate if still alive
                    try:
                        if process.is_alive():
                            process.terminate()
                            process.join(timeout=1.0)
                            try:
                                if process.is_alive():
                                    process.kill()
                            except (ValueError, AssertionError):
                                pass  # Process already terminated
                    except (ValueError, AssertionError):
                        pass  # Process already terminated

            del self._workers[db_path_str]
            logger.info(f"[DBWorkerManager] DB worker stopped for {db_path_str}")

    def stop_all_workers(self) -> None:
        """Stop all DB workers."""
        with self._lock:
            db_paths = list(self._workers.keys())
            for db_path in db_paths:
                self.stop_worker(db_path)


def get_db_worker_manager() -> DBWorkerManager:
    """
    Get singleton instance of DBWorkerManager.

    Returns:
        DBWorkerManager instance
    """
    return DBWorkerManager.get_instance()

