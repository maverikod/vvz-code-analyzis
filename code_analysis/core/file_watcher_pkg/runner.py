"""
Module runner.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _setup_worker_logging(
    log_path: Optional[str] = None,
    max_bytes: int = 10485760,  # 10 MB default
    backup_count: int = 5,
) -> None:
    """
    Setup logging for file watcher worker to separate log file with rotation.

    Args:
        log_path: Path to worker log file (optional)
        max_bytes: Maximum log file size in bytes before rotation (default: 10 MB)
        backup_count: Number of backup log files to keep (default: 5)
    """
    if log_path:
        log_file = Path(log_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Configure root logger for worker process
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Rotating file handler for worker log with detailed format
        file_handler = RotatingFileHandler(
            log_file,
            encoding="utf-8",
            mode="a",
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        # Also log to stderr for visibility (less verbose)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        logger.info(f"File watcher worker logging configured: {log_file}")
    else:
        # Default logging if no path specified
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


def run_file_watcher_worker(
    db_path: str,
    project_watch_dirs: List[tuple[str, str]],
    scan_interval: int = 60,
    lock_file_name: str = ".file_watcher.lock",
    version_dir: Optional[str] = None,
    ignore_patterns: Optional[List[str]] = None,
    worker_log_path: Optional[str] = None,
    log_max_bytes: int = 10485760,  # 10 MB default
    log_backup_count: int = 5,
) -> Dict[str, Any]:
    """Run file watcher worker in separate process.

    Worker policy:
        This worker must NOT start other processes (including DB worker).
        It connects to an already running DB worker via sqlite_proxy.

    Args:
        db_path: Path to database file.
        project_watch_dirs: List of (project_id, watch_dir) pairs.
        scan_interval: Scan interval seconds.
        lock_file_name: Lock file name.
        version_dir: Version directory for deleted files.
        ignore_patterns: Optional ignore patterns.
        worker_log_path: Optional log file path.
        log_max_bytes: Log rotation max bytes.
        log_backup_count: Log rotation backup count.

    Returns:
        Stats dict (only when stopped).
    """
    import os

    # Enforce worker policy: never spawn DB worker from this process.
    os.environ["CODE_ANALYSIS_DB_WORKER_NO_SPAWN"] = "1"

    # Setup worker logging first
    _setup_worker_logging(worker_log_path, log_max_bytes, log_backup_count)

    from .multi_project_worker import MultiProjectFileWatcherWorker, build_project_specs

    worker = MultiProjectFileWatcherWorker(
        db_path=Path(db_path),
        projects=build_project_specs(project_watch_dirs),
        scan_interval=int(scan_interval),
        lock_file_name=lock_file_name,
        version_dir=version_dir,
        ignore_patterns=ignore_patterns or [],
    )

    try:
        return asyncio.run(worker.run())
    except KeyboardInterrupt:
        worker.stop()
        return {"cycles": 0, "errors": 0, "interrupted": True}
    except Exception as e:
        logger.error(f"File watcher worker error: {e}", exc_info=True)
        return {"cycles": 0, "errors": 1}
