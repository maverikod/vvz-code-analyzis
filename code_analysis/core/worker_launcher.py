"""
Background worker launcher utilities.

This module centralizes process spawning for background workers (file watcher,
vectorization) and registers them in WorkerManager.

It is intentionally small and dependency-light to avoid circular imports.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import multiprocessing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .worker_manager import get_worker_manager


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


def start_file_watcher_worker(
    *,
    db_path: str,
    watch_dirs: List[str],
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

    Args:
        db_path: Path to database file.
        watch_dirs: Directories to scan (projects discovered automatically).
        locks_dir: Service state directory for lock files (from StoragePaths).
        scan_interval: Scan interval seconds.
        version_dir: Version directory for deleted files.
        worker_log_path: Log path for worker process.
        ignore_patterns: Optional ignore patterns.

    Returns:
        WorkerStartResult.
    """
    from .file_watcher_pkg.runner import run_file_watcher_worker

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
        daemon=True,
    )
    process.start()

    # Use first watch_dir as identifier for worker name
    worker_name = f"file_watcher_{Path(watch_dirs[0]).name if watch_dirs else 'default'}"
    get_worker_manager().register_worker(
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
    import logging
    import os
    from pathlib import Path

    logger = logging.getLogger(__name__)

    from .vectorization_worker_pkg.runner import run_vectorization_worker

    # PID file check (before starting worker)
    pid_file_path = Path("logs") / "vectorization_worker.pid"
    if pid_file_path.exists():
        try:
            with open(pid_file_path, "r") as f:
                pid = int(f.read().strip())
            # Check if process is alive
            try:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                # Process is alive, worker already running
                return WorkerStartResult(
                    success=False,
                    worker_type="vectorization",
                    pid=pid,
                    message="Vectorization worker already running",
                )
            except OSError:
                # Process is dead, remove stale PID file
                pid_file_path.unlink()
        except Exception as e:
            logger.warning(f"Error checking PID file: {e}, removing stale file")
            try:
                pid_file_path.unlink()
            except Exception:
                pass

    process = multiprocessing.Process(
        target=run_vectorization_worker,
        args=(db_path, faiss_dir, int(vector_dim)),
        kwargs={
            "svo_config": svo_config,
            "batch_size": int(batch_size),
            "poll_interval": int(poll_interval),
            "worker_log_path": worker_log_path,
        },
        daemon=True,
    )
    process.start()

    # Write PID file after worker starts
    try:
        pid_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(pid_file_path, "w") as f:
            f.write(str(process.pid))
    except Exception as e:
        logger.warning(f"Failed to write PID file: {e}")

    get_worker_manager().register_worker(
        "vectorization",
        {"pid": process.pid, "process": process, "name": "vectorization_universal"},
    )
    return WorkerStartResult(
        success=True,
        worker_type="vectorization",
        pid=process.pid,
        message=f"Vectorization worker started (PID {process.pid})",
    )


def stop_worker_type(worker_type: str, *, timeout: float = 10.0) -> Dict[str, Any]:
    """
    Stop all workers of a given type via WorkerManager.

    Args:
        worker_type: Worker type string.
        timeout: Stop timeout seconds.

    Returns:
        Stop result dict.
    """
    return get_worker_manager().stop_worker_type(worker_type, timeout=timeout)
