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
    project_id: str,
    watch_dirs: List[str],
    scan_interval: int = 60,
    lock_file_name: str = ".file_watcher.lock",
    version_dir: Optional[str] = None,
    worker_log_path: Optional[str] = None,
    project_root: Optional[str] = None,
    ignore_patterns: Optional[List[str]] = None,
) -> WorkerStartResult:
    """
    Start file watcher worker in a separate process and register it.

    Args:
        db_path: Path to database file.
        project_id: Project ID to watch.
        watch_dirs: Directories to scan.
        scan_interval: Scan interval seconds.
        lock_file_name: Lock file name.
        version_dir: Version directory for deleted files.
        worker_log_path: Log path for worker process.
        project_root: Project root for relative paths.
        ignore_patterns: Optional ignore patterns.

    Returns:
        WorkerStartResult.
    """
    from .file_watcher_pkg.runner import run_file_watcher_worker

    process = multiprocessing.Process(
        target=run_file_watcher_worker,
        args=(db_path, project_id, watch_dirs),
        kwargs={
            "scan_interval": int(scan_interval),
            "lock_file_name": lock_file_name,
            "version_dir": version_dir,
            "worker_log_path": worker_log_path,
            "project_root": project_root,
            "ignore_patterns": ignore_patterns or [],
        },
        daemon=True,
    )
    process.start()

    get_worker_manager().register_worker(
        "file_watcher",
        {"pid": process.pid, "process": process, "name": f"file_watcher_{project_id}"},
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
    project_id: str,
    faiss_index_path: str,
    vector_dim: int = 384,
    svo_config: Optional[Dict[str, Any]] = None,
    batch_size: int = 10,
    poll_interval: int = 30,
    worker_log_path: Optional[str] = None,
) -> WorkerStartResult:
    """
    Start vectorization worker in a separate process and register it.

    Args:
        db_path: Path to database file.
        project_id: Project ID to process.
        faiss_index_path: Path to FAISS index directory/file.
        vector_dim: Embedding vector dimension.
        svo_config: Optional SVO config dict.
        batch_size: Batch size.
        poll_interval: Poll interval seconds.
        worker_log_path: Log path for worker process.

    Returns:
        WorkerStartResult.
    """
    from .vectorization_worker_pkg.runner import run_vectorization_worker

    process = multiprocessing.Process(
        target=run_vectorization_worker,
        args=(db_path, project_id, faiss_index_path, int(vector_dim)),
        kwargs={
            "svo_config": svo_config,
            "batch_size": int(batch_size),
            "poll_interval": int(poll_interval),
            "worker_log_path": worker_log_path,
        },
        daemon=True,
    )
    process.start()

    get_worker_manager().register_worker(
        "vectorization",
        {"pid": process.pid, "process": process, "name": f"vectorization_{project_id}"},
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


def default_faiss_index_path(root_dir: str) -> str:
    """
    Default FAISS index path for a project root.

    Args:
        root_dir: Project root directory.

    Returns:
        Path string.
    """
    root_path = Path(root_dir).resolve()
    return str((root_path / "data" / "faiss_index").resolve())
