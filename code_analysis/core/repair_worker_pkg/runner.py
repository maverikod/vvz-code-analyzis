"""
Repair worker runner.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

from .base import RepairWorker

logger = logging.getLogger(__name__)


def _setup_worker_logging(
    log_path: Optional[str] = None,
    max_bytes: int = 10485760,  # 10 MB default
    backup_count: int = 5,
) -> None:
    """
    Setup logging for repair worker to separate log file with rotation.

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

        logger.info(f"Repair worker logging configured: {log_file}")
    else:
        # Default logging if no path specified
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


def run_repair_worker(
    db_path: str,
    project_id: str,
    root_dir: str,
    version_dir: str,
    batch_size: int = 10,
    poll_interval: int = 30,
    worker_log_path: Optional[str] = None,
    log_max_bytes: int = 10485760,  # 10 MB default
    log_backup_count: int = 5,
) -> Dict[str, Any]:
    """
    Run repair worker in separate process.

    This function is designed to be called from multiprocessing.Process.
    It runs indefinitely, repairing database integrity at specified intervals.

    Args:
        db_path: Path to database file
        project_id: Project ID
        root_dir: Project root directory
        version_dir: Version directory for deleted files
        batch_size: Number of files to process per batch (default: 10)
        poll_interval: Interval in seconds between repair cycles (default: 30)
        worker_log_path: Path to worker log file (optional)
        log_max_bytes: Maximum log file size in bytes before rotation (default: 10 MB)
        log_backup_count: Number of backup log files to keep (default: 5)

    Returns:
        Dictionary with processing statistics (only when stopped)
    """
    # Setup worker logging first
    _setup_worker_logging(worker_log_path, log_max_bytes, log_backup_count)

    logger.info(
        f"Starting repair worker for project {project_id}, "
        f"batch size: {batch_size}, "
        f"poll interval: {poll_interval}s"
    )

    try:
        # Create worker
        worker = RepairWorker(
            db_path=Path(db_path),
            project_id=project_id,
            root_dir=Path(root_dir),
            version_dir=version_dir,
            batch_size=batch_size,
            poll_interval=poll_interval,
        )

        # Run worker
        result = asyncio.run(worker.run())
        return result
    except KeyboardInterrupt:
        logger.info("Repair worker interrupted")
        return {
            "files_processed": 0,
            "files_restored": 0,
            "files_marked_deleted": 0,
            "files_restored_from_cst": 0,
            "errors": 0,
            "interrupted": True,
        }
    except Exception as e:
        logger.error(f"Repair worker error: {e}", exc_info=True)
        return {
            "files_processed": 0,
            "files_restored": 0,
            "files_marked_deleted": 0,
            "files_restored_from_cst": 0,
            "errors": 1,
            "error": str(e),
        }
