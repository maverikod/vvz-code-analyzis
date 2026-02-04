"""
Indexing worker runner: logging, PID file, main loop.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

from .base import IndexingWorker

logger = logging.getLogger(__name__)


def _remove_pid_file_if_ours(pid_file_path: str) -> None:
    """Remove PID file only if it contains this process's PID."""
    import os

    path = Path(pid_file_path)
    if not path.exists():
        return
    try:
        pid_str = path.read_text().strip()
        pid = int(pid_str)
        if pid == os.getpid():
            path.unlink()
            logger.debug("Removed PID file on exit (PID=%s): %s", pid, pid_file_path)
        else:
            logger.debug(
                "PID file contains other process (PID=%s, ours=%s), leaving file",
                pid,
                os.getpid(),
            )
    except (ValueError, OSError) as e:
        logger.warning("Could not read/remove PID file %s: %s", pid_file_path, e)


def _setup_worker_logging(
    log_path: Optional[str] = None,
    max_bytes: int = 10485760,
    backup_count: int = 5,
) -> None:
    """Setup logging for indexing worker: rotating file + console."""
    if log_path:
        log_file = Path(log_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        file_handler = RotatingFileHandler(
            log_file,
            encoding="utf-8",
            mode="a",
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        root_logger.addHandler(file_handler)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        root_logger.addHandler(console_handler)
        logger.info("Worker logging configured: %s", log_file)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


def run_indexing_worker(
    db_path: str,
    poll_interval: int = 30,
    batch_size: int = 5,
    worker_log_path: Optional[str] = None,
    pid_file_path: Optional[str] = None,
    socket_path: Optional[str] = None,
    log_max_bytes: int = 10485760,
    log_backup_count: int = 5,
) -> Dict[str, Any]:
    """Run indexing worker: logging, PID cleanup, create client and worker, loop until stop.

    Args:
        db_path: Path to database file
        poll_interval: Seconds between cycles (default 30)
        batch_size: Max files per project per cycle (default 5)
        worker_log_path: Path to worker log file (optional)
        pid_file_path: Path to PID file (optional); removed on exit only if PID matches
        socket_path: Database driver socket path (optional; derived from db_path if not set)
        log_max_bytes: Max log file size before rotation (default 10 MB)
        log_backup_count: Number of rotated logs to keep (default 5)

    Returns:
        Stats dict when stopped: indexed, errors, cycles.
    """
    from ..constants import DEFAULT_DB_DRIVER_SOCKET_DIR

    _setup_worker_logging(worker_log_path, log_max_bytes, log_backup_count)

    logger.info(
        "Starting indexing worker, poll_interval=%ss, batch_size=%s",
        poll_interval,
        batch_size,
    )

    db_path_obj = Path(db_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    if not socket_path:
        db_name = db_path_obj.stem
        socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
        socket_dir.mkdir(parents=True, exist_ok=True)
        socket_path = str(socket_dir / f"{db_name}_driver.sock")

    if not db_path_obj.exists():
        logger.info(
            "Database file not found at %s; worker will retry when DB is available",
            db_path,
        )

    worker = IndexingWorker(
        db_path=db_path_obj,
        socket_path=socket_path,
        batch_size=batch_size,
        poll_interval=poll_interval,
    )

    try:
        return asyncio.run(worker.process_cycle(poll_interval=poll_interval))
    except KeyboardInterrupt:
        logger.info("Indexing worker interrupted by signal")
        worker.stop()
        return {"indexed": 0, "errors": 0, "cycles": 0, "interrupted": True}
    except Exception as e:
        logger.error("Error in indexing worker: %s", e, exc_info=True)
        return {"indexed": 0, "errors": 1, "cycles": 0}
    finally:
        if pid_file_path:
            _remove_pid_file_if_ours(pid_file_path)
