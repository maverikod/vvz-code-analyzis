"""
Worker lifecycle management for starting and stopping workers.

This module handles starting and stopping of worker processes,
including file watcher and vectorization workers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import logging
import multiprocessing
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import DEFAULT_WORKER_STOP_TIMEOUT, LOGS_DIR_NAME
from .database_driver_manager import WorkerStartResult  # Re-exported for compatibility

logger = logging.getLogger(__name__)


class WorkerLifecycleManager:
    """
    Manager for worker lifecycle operations.

    Responsibilities:
    - Start worker processes (file_watcher, vectorization)
    - Stop worker processes gracefully
    - Handle process termination with fallbacks
    """

    def __init__(
        self,
        registry: Any,
        check_pid_file_callback: Any,
        register_callback: Any,
        clear_workers_callback: Any,
    ):
        """
        Initialize worker lifecycle manager.

        Args:
            registry: Worker registry instance
            check_pid_file_callback: Callback to check PID file
            register_callback: Callback to register worker
            clear_workers_callback: Callback to clear workers
        """
        self.registry = registry
        self.check_pid_file = check_pid_file_callback
        self.register_worker = register_callback
        self.clear_workers = clear_workers_callback

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
        workers = self.registry.get_workers(worker_type)
        worker_list = workers.get(worker_type, [])

        if not worker_list:
            return {
                "success": True,
                "message": f"No {worker_type} workers to stop",
                "stopped": 0,
            }

        result = {
            "success": True,
            "stopped": 0,
            "failed": 0,
            "errors": [],
        }

        for worker_info in worker_list:
            try:
                pid = worker_info.get("pid")
                process = worker_info.get("process")
                queue_system = worker_info.get("queue_system")
                worker = worker_info.get("worker")
                name = worker_info.get("name", worker_type)

                # Stop based on type
                if queue_system:
                    result = self._stop_queue_system(
                        queue_system, worker_type, name, result
                    )
                elif process:
                    result = self._stop_process(
                        process, pid, worker_type, name, timeout, result
                    )
                elif worker:
                    result = self._stop_worker_instance(
                        worker, worker_type, name, result
                    )
                elif pid:
                    result = self._stop_by_pid(pid, worker_type, timeout, result)

            except Exception as e:
                error_msg = f"Error stopping {worker_type} worker: {e}"
                logger.error(error_msg, exc_info=True)
                result["errors"].append(error_msg)
                result["failed"] += 1

        # Clear stopped workers from registry
        self.clear_workers(worker_type)

        result["success"] = result["failed"] == 0
        result["message"] = (
            f"Stopped {result['stopped']} {worker_type} worker(s), "
            f"{result['failed']} failed"
        )

        return result

    def _stop_queue_system(
        self, queue_system: Any, worker_type: str, name: str, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Stop async queue system."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(queue_system.stop())
            else:
                loop.run_until_complete(queue_system.stop())
            logger.info(f"Stopped {worker_type} queue system: {name}")
            result["stopped"] += 1
        except Exception as e:
            error_msg = f"Failed to stop {worker_type} queue system {name}: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            result["failed"] += 1
        return result

    def _stop_process(
        self,
        process: multiprocessing.Process,
        pid: Optional[int],
        worker_type: str,
        name: str,
        timeout: float,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Stop multiprocessing process with fallback to PID-based termination."""
        try:
            is_alive = process.is_alive()
        except AssertionError:
            is_alive = None

        if is_alive is None:
            # Fall back to PID-based termination
            if pid:
                return self._stop_by_pid(pid, worker_type, timeout, result)
            else:
                error_msg = (
                    f"Cannot stop {worker_type} process {name}: "
                    "Process handle is not valid in this PID and PID is missing"
                )
                logger.error(error_msg)
                result["errors"].append(error_msg)
                result["failed"] += 1
                return result

        if not is_alive:
            result["stopped"] += 1
            return result

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
                # Parent mismatch - use PID fallback
                if pid:
                    return self._stop_by_pid(pid, worker_type, timeout, result)
                else:
                    raise RuntimeError(
                        "Cannot stop process: parent mismatch and PID missing"
                    )

            if still_alive:
                # Force kill if still alive after timeout
                logger.warning(
                    f"{worker_type} worker {name} (PID: {pid}) did not stop within {timeout}s, sending SIGKILL"
                )
                process.kill()
                process.join(timeout=2.0)

            # Verify process is dead
            process_dead = False
            try:
                is_alive_after = process.is_alive()
                if is_alive_after is False:
                    process_dead = True
            except AssertionError:
                is_alive_after = None

            if process_dead:
                logger.info(f"Stopped {worker_type} process: {name} (PID: {pid})")
                result["stopped"] += 1
            elif is_alive_after is None:
                # Process handle invalid - verify via PID
                if pid:
                    return self._stop_by_pid(pid, worker_type, timeout, result)
                else:
                    logger.info(
                        f"Stopped {worker_type} process (parent handle invalid, no PID): {name}"
                    )
                    result["stopped"] += 1
            else:
                # Process still alive - force kill via PID
                if pid:
                    return self._stop_by_pid(pid, worker_type, timeout, result)
                else:
                    error_msg = (
                        f"Cannot kill {worker_type} process {name}: "
                        "process still alive but no PID available"
                    )
                    logger.error(error_msg)
                    result["errors"].append(error_msg)
                    result["failed"] += 1

        except Exception as e:
            error_msg = f"Failed to stop {worker_type} process {name} (PID: {pid}): {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            result["failed"] += 1

        return result

    def _stop_worker_instance(
        self, worker: Any, worker_type: str, name: str, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Stop worker instance with stop method."""
        try:
            if hasattr(worker, "stop"):
                worker.stop()
            logger.info(f"Stopped {worker_type} worker: {name}")
            result["stopped"] += 1
        except Exception as e:
            error_msg = f"Failed to stop {worker_type} worker {name}: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            result["failed"] += 1
        return result

    def _stop_by_pid(
        self, pid: int, worker_type: str, timeout: float, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Stop process by PID using psutil."""
        try:
            import psutil

            proc = psutil.Process(pid)
            if proc.is_running():
                proc.terminate()
                try:
                    proc.wait(timeout=timeout)
                    logger.info(f"Stopped {worker_type} process (PID: {pid})")
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
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process is dead or we can't access it
            result["stopped"] += 1
        except Exception as e:
            error_msg = f"Failed to stop {worker_type} process (PID: {pid}): {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            result["failed"] += 1
        return result

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
            worker_logs_dir: Absolute directory for worker log and PID file (optional).
            ignore_patterns: Optional ignore patterns.

        Returns:
            WorkerStartResult.
        """
        from .file_watcher_pkg.runner import run_file_watcher_worker

        # PID file: use absolute path when worker_logs_dir provided
        if worker_logs_dir:
            pid_file_path = Path(worker_logs_dir).resolve() / "file_watcher_worker.pid"
        else:
            pid_file_path = Path(LOGS_DIR_NAME).resolve() / "file_watcher_worker.pid"

        # Check: read PID from file and verify that process is running (never "file exists" alone)
        existing_pid = self.check_pid_file(
            pid_file_path, "file_watcher", "file_watcher"
        )
        if existing_pid is not None:
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
                "pid_file_path": str(pid_file_path),
                "ignore_patterns": ignore_patterns or [],
            },
            daemon=True,  # Daemon process for background workers
        )
        process.start()

        # Write process number (PID) to PID file; check logic reads this and verifies process exists
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
        worker_logs_dir: Optional[str] = None,
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
        worker_logs_dir: Absolute directory for worker log and PID file (optional).
                         If provided, PID file is {worker_logs_dir}/vectorization_worker.pid.

        Returns:
            WorkerStartResult.
        """
        from .vectorization_worker_pkg.runner import run_vectorization_worker

        # PID file: use absolute path when worker_logs_dir provided so cwd does not affect it
        if worker_logs_dir:
            pid_file_path = Path(worker_logs_dir).resolve() / "vectorization_worker.pid"
        else:
            pid_file_path = Path(LOGS_DIR_NAME).resolve() / "vectorization_worker.pid"

        # Check: read PID from file and verify that process is running (never "file exists" alone)
        existing_pid = self.check_pid_file(
            pid_file_path, "vectorization", "vectorization"
        )
        if existing_pid is not None:
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
                "pid_file_path": str(pid_file_path),
            },
            daemon=True,  # Daemon process for background workers
        )
        process.start()

        # Write process number (PID) to PID file; check logic reads this and verifies process exists
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

    def start_indexing_worker(
        self,
        *,
        db_path: str,
        poll_interval: int = 30,
        batch_size: int = 5,
        worker_log_path: Optional[str] = None,
        worker_logs_dir: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> WorkerStartResult:
        """
        Start indexing worker in a separate process and register it.

        Worker processes files with needs_chunking=1 via driver index_file RPC.
        Must run before vectorization worker (startup order) so indexer clears
        needs_chunking before vectorization chunks.
        When config_path is set, worker vectorizes each file after successful index.

        CRITICAL: Uses multiprocessing.Process, not threading.Thread or async.

        Args:
            db_path: Path to database file.
            poll_interval: Poll interval seconds (default 30).
            batch_size: Max files per project per cycle (default 5).
            worker_log_path: Log path for worker process.
            worker_logs_dir: Absolute directory for worker log and PID file (optional).
                             If provided, PID file is {worker_logs_dir}/indexing_worker.pid.
            config_path: Optional path to config; when set, vectorize file after each successful index.

        Returns:
            WorkerStartResult.
        """
        from .indexing_worker_pkg.runner import run_indexing_worker

        if worker_logs_dir:
            pid_file_path = Path(worker_logs_dir).resolve() / "indexing_worker.pid"
        else:
            pid_file_path = Path(LOGS_DIR_NAME).resolve() / "indexing_worker.pid"

        existing_pid = self.check_pid_file(pid_file_path, "indexing", "indexing")
        if existing_pid is not None:
            return WorkerStartResult(
                success=False,
                worker_type="indexing",
                pid=existing_pid,
                message="Indexing worker already running",
            )

        kwargs = {
            "poll_interval": int(poll_interval),
            "batch_size": int(batch_size),
            "worker_log_path": worker_log_path,
            "pid_file_path": str(pid_file_path),
        }
        if config_path is not None:
            kwargs["config_path"] = config_path

        process = multiprocessing.Process(
            target=run_indexing_worker,
            args=(db_path,),
            kwargs=kwargs,
            daemon=True,
        )
        process.start()

        try:
            pid_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pid_file_path, "w") as f:
                f.write(str(process.pid))
        except Exception as e:
            logger.warning(f"Failed to write PID file: {e}")

        self.register_worker(
            "indexing",
            {"pid": process.pid, "process": process, "name": "indexing_universal"},
        )
        return WorkerStartResult(
            success=True,
            worker_type="indexing",
            pid=process.pid,
            message=f"Indexing worker started (PID {process.pid})",
        )
