"""
Obtain socket path for SQLite proxy worker (start or get existing).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
from pathlib import Path
from typing import Any, Optional

from code_analysis.core.db_worker_manager import get_db_worker_manager

logger = logging.getLogger(__name__)


def get_socket_path_for_worker(
    db_path: Any,
    worker_log_path: Optional[str] = None,
    socket_wait_timeout: float = 5.0,
    socket_wait_interval: float = 0.1,
) -> str:
    """
    Get or start DB worker and return its socket path.

    Args:
        db_path: Database path (str or Path).
        worker_log_path: Optional log path for worker.
        socket_wait_timeout: Max seconds to wait for socket file.
        socket_wait_interval: Sleep between checks.

    Returns:
        Socket path string.

    Raises:
        RuntimeError: If worker_info has no socket_path or socket not created.
    """
    worker_manager = get_db_worker_manager()
    logger.debug("Got worker manager, calling get_or_start_worker...")
    worker_info = worker_manager.get_or_start_worker(str(db_path), worker_log_path)
    socket_path = worker_info.get("socket_path") if worker_info else None
    if not socket_path:
        raise RuntimeError(f"No socket_path in worker_info: {worker_info}")

    socket_file = Path(socket_path)
    if not socket_file.exists():
        logger.warning("Socket file does not exist yet, waiting...")
        waited = 0.0
        while not socket_file.exists() and waited < socket_wait_timeout:
            time.sleep(socket_wait_interval)
            waited += socket_wait_interval
        if not socket_file.exists():
            raise RuntimeError(
                f"Socket file not created after {waited:.1f}s: {socket_path}"
            )
        logger.debug("Socket file exists after %.1fs wait", waited)

    return str(socket_path)
