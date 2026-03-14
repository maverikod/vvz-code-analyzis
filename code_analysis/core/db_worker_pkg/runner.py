"""
Database worker process runner.

This worker runs in a separate process and handles database operations
via Unix socket, ensuring thread/process safety for SQLite.

Architecture:
1. Client connects via socket, sends request, receives job_id, disconnects
2. Client periodically polls server for results
3. Client sends delete command after receiving results
4. Server automatically cleans up expired jobs

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import os
import signal
import socket
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .runner_cleanup import cleanup_expired_jobs
from .runner_logging import setup_worker_logging
from .runner_socket import handle_client_connection

os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

logger = logging.getLogger(__name__)


def run_db_worker(
    db_path: str,
    socket_path: str,
    worker_log_path: Optional[str] = None,
    job_timeout: float = 300.0,
    cleanup_interval: float = 60.0,
) -> None:
    """
    Run database worker process.

    Handles database operations via Unix socket. Clients submit jobs,
    poll for results, and delete completed jobs.
    """
    setup_worker_logging(worker_log_path)

    logger.info(f"🚀 DB worker started for database: {db_path}, socket: {socket_path}")

    db_path_obj = Path(db_path)
    if not db_path_obj.exists():
        logger.info(f"Creating empty database at {db_path}")
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path_obj))
        conn.close()
        logger.info(f"Empty database created at {db_path}")

    shutdown_event = False

    def signal_handler(signum, frame):
        nonlocal shutdown_event
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event = True

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    jobs: Dict[str, Dict[str, Any]] = {}
    jobs_lock = threading.Lock()

    def cleanup_worker():
        while not shutdown_event:
            time.sleep(cleanup_interval)
            if not shutdown_event:
                cleanup_expired_jobs(jobs, jobs_lock, job_timeout)

    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()

    socket_file = Path(socket_path)
    if socket_file.exists():
        socket_file.unlink()

    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(socket_path)
    server_sock.listen(5)
    server_sock.settimeout(1.0)

    logger.info(f"DB worker listening on socket: {socket_path}")

    try:
        while not shutdown_event:
            try:
                client_sock, _ = server_sock.accept()
                thread = threading.Thread(
                    target=handle_client_connection,
                    args=(client_sock, db_path, jobs, jobs_lock, job_timeout),
                    daemon=True,
                )
                thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                if not shutdown_event:
                    logger.error(f"Error accepting connection: {e}", exc_info=True)
    except KeyboardInterrupt:
        logger.info("DB worker interrupted by keyboard")
    except Exception as e:
        logger.error(f"DB worker crashed: {e}", exc_info=True)
    finally:
        logger.info("🛑 DB worker shutting down")
        try:
            server_sock.close()
        except Exception:
            pass
        if socket_file.exists():
            try:
                socket_file.unlink()
            except Exception:
                pass
