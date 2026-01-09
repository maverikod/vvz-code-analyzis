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

import os
import sqlite3
import logging
import signal
import sys
import socket
import json
import struct
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union, List
from datetime import datetime, timedelta

# Set environment variable to indicate this is a DB worker process
os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

logger = logging.getLogger(__name__)


def _setup_worker_logging(
    log_path: Optional[str] = None,
    max_bytes: int = 10485760,  # 10 MB default
    backup_count: int = 5,
) -> None:
    """
    Setup logging for DB worker to separate log file with rotation.

    Args:
        log_path: Path to worker log file (optional)
        max_bytes: Maximum log file size in bytes before rotation (default: 10 MB)
        backup_count: Number of backup log files to keep (default: 5)
    """
    if log_path:
        from logging.handlers import RotatingFileHandler

        log_file = Path(log_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Configure root logger for worker process
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Rotating file handler for worker log
        file_handler = RotatingFileHandler(
            log_file,
            encoding="utf-8",
            mode="a",
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Also add console handler for immediate feedback
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)
    logging.getLogger().addHandler(console_handler)


# Global dictionary to store transaction connections
# Key: transaction_id, Value: sqlite3.Connection
_transaction_connections: Dict[str, Any] = {}


def _execute_operation(
    operation: str,
    db_path: str,
    sql: Optional[str] = None,
    params: Optional[tuple] = None,
    table_name: Optional[str] = None,
    transaction_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute database operation.

    Args:
        operation: Operation type (execute, fetchone, fetchall, commit, rollback, lastrowid, get_table_info)
        db_path: Path to database file
        sql: SQL statement (for execute, fetchone, fetchall)
        params: Query parameters tuple (optional)
        table_name: Table name (for get_table_info)

    Returns:
        Dictionary with operation result or error
    """
    db_path_obj = Path(db_path)
    # SQLite will create the file automatically if it doesn't exist
    # Ensure parent directory exists
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # Get or create connection for transaction
    conn: Optional[sqlite3.Connection] = None
    use_transaction_connection = False

    # Handle begin_transaction separately - create connection and store it
    if operation == "begin_transaction":
        if not transaction_id:
            raise ValueError("transaction_id is required for begin_transaction")
        if transaction_id in _transaction_connections:
            raise ValueError(f"Transaction {transaction_id} already exists")
        # Create new connection for transaction
        conn = sqlite3.connect(str(db_path_obj), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            pass
        # Begin transaction
        conn.execute("BEGIN TRANSACTION")
        _transaction_connections[transaction_id] = conn
        use_transaction_connection = True
        return {"success": True, "result": {"success": True}, "error": None}

    # For other operations, get or create connection
    if transaction_id:
        # Use transaction connection if exists
        if transaction_id in _transaction_connections:
            conn = _transaction_connections[transaction_id]
            use_transaction_connection = True
        else:
            raise ValueError(
                f"Transaction {transaction_id} not found. Call begin_transaction first."
            )
    else:
        # Create new connection for this operation (non-transaction mode)
        conn = sqlite3.connect(str(db_path_obj), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            pass

    try:
        result: Union[Dict[str, Any], List[Dict[str, Any]], None] = None

        if operation == "commit_transaction":
            if transaction_id and transaction_id in _transaction_connections:
                conn = _transaction_connections[transaction_id]
                conn.commit()
                conn.close()
                del _transaction_connections[transaction_id]
                result = {"success": True}
            else:
                raise ValueError(f"Transaction {transaction_id} not found")

        elif operation == "rollback_transaction":
            if transaction_id and transaction_id in _transaction_connections:
                conn = _transaction_connections[transaction_id]
                conn.rollback()
                conn.close()
                del _transaction_connections[transaction_id]
                result = {"success": True}
            else:
                raise ValueError(f"Transaction {transaction_id} not found")

        elif operation == "execute":
            if not sql:
                raise ValueError("sql parameter is required for execute operation")
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            # Only commit if not in transaction
            if not use_transaction_connection:
                conn.commit()
            result = {
                "lastrowid": cursor.lastrowid,
                "rowcount": cursor.rowcount,
            }

        elif operation == "fetchone":
            if not sql:
                raise ValueError("sql parameter is required for fetchone operation")
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            row = cursor.fetchone()
            if row:
                result = dict(zip(row.keys(), row))
            else:
                result = None

        elif operation == "fetchall":
            if not sql:
                raise ValueError("sql parameter is required for fetchall operation")
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            rows = cursor.fetchall()
            result = [dict(zip(row.keys(), row)) for row in rows]

        elif operation == "commit":
            conn.commit()
            result = None

        elif operation == "rollback":
            conn.rollback()
            result = None

        elif operation == "lastrowid":
            # Not supported with per-operation connections
            result = None

        elif operation == "get_table_info":
            if not table_name:
                raise ValueError(
                    "table_name parameter is required for get_table_info operation"
                )
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            rows = cursor.fetchall()
            columns = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
            result = [dict(zip(columns, row)) for row in rows]

        else:
            raise ValueError(f"Unknown operation: {operation}")

        return {"success": True, "result": result, "error": None}

    except Exception as e:
        logger.error(
            f"Database operation '{operation}' failed: {e}",
            exc_info=True,
            extra={
                "operation": operation,
                "db_path": db_path,
                "sql": sql[:200] if sql else None,
            },
        )
        return {
            "success": False,
            "result": None,
            "error": {
                "type": type(e).__name__,
                "message": str(e),
                "sql": sql[:200] if sql else None,
            },
        }

    finally:
        # Only close connection if not in transaction
        # Transaction connections are closed in commit_transaction/rollback_transaction
        if not use_transaction_connection and conn:
            conn.close()


def _send_response(sock: socket.socket, response: Dict[str, Any]) -> None:
    """
    Send JSON response over socket.

    Args:
        sock: Socket connection
        response: Response dictionary to send
    """
    try:
        data = json.dumps(response).encode("utf-8")
        length = struct.pack("!I", len(data))
        sock.sendall(length + data)
    except Exception as e:
        logger.error(f"Failed to send response: {e}", exc_info=True)


def _receive_request(
    sock: socket.socket, timeout: float = 5.0
) -> Optional[Dict[str, Any]]:
    """
    Receive JSON request from socket.

    Args:
        sock: Socket connection
        timeout: Socket timeout in seconds

    Returns:
        Request dictionary or None if connection closed
    """
    try:
        sock.settimeout(timeout)
        # Receive length (4 bytes)
        length_data = b""
        while len(length_data) < 4:
            chunk = sock.recv(4 - len(length_data))
            if not chunk:
                return None
            length_data += chunk

        length = struct.unpack("!I", length_data)[0]

        # Receive data
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk

        return json.loads(data.decode("utf-8"))
    except socket.timeout:
        return None
    except Exception as e:
        logger.error(f"Failed to receive request: {e}", exc_info=True)
        return None


def _handle_client_connection(
    client_sock: socket.socket,
    db_path: str,
    jobs: Dict[str, Dict[str, Any]],
    jobs_lock: threading.Lock,
    job_timeout: float = 300.0,
) -> None:
    """
    Handle client connection: receive request, process, send response.

    Args:
        client_sock: Client socket connection
        db_path: Path to database file
        jobs: Dictionary to store job results (job_id -> result)
        jobs_lock: Lock for jobs dictionary
        job_timeout: Job timeout in seconds (default: 5 minutes)
    """
    try:
        request = _receive_request(client_sock, timeout=5.0)
        if not request:
            return

        command = request.get("command")

        if command == "submit":
            # Submit new job
            job_id = request.get("job_id")
            operation = request.get("operation")
            sql = request.get("sql")
            params = request.get("params")
            table_name = request.get("table_name")
            transaction_id = request.get(
                "transaction_id"
            )  # Get transaction_id from request

            if not job_id:
                _send_response(
                    client_sock,
                    {
                        "success": False,
                        "error": "Missing job_id",
                    },
                )
                return

            logger.debug(
                f"Received job submission: job_id={job_id}, operation={operation}"
            )

            # Add job to queue (will be processed asynchronously)
            with jobs_lock:
                jobs[job_id] = {
                    "status": "pending",
                    "operation": operation,
                    "created_at": datetime.now(),
                    "result": None,
                    "error": None,
                }

            # Execute operation in background thread
            def execute_job():
                try:
                    result = _execute_operation(
                        operation=operation,
                        db_path=db_path,
                        sql=sql,
                        params=params,
                        table_name=table_name,
                        transaction_id=transaction_id,  # Pass transaction_id
                    )
                    with jobs_lock:
                        if job_id in jobs:
                            jobs[job_id].update(
                                {
                                    "status": "completed",
                                    "result": result.get("result"),
                                    "error": result.get("error"),
                                    "success": result.get("success", False),
                                }
                            )
                except Exception as e:
                    logger.error(f"Error executing job {job_id}: {e}", exc_info=True)
                    with jobs_lock:
                        if job_id in jobs:
                            jobs[job_id].update(
                                {
                                    "status": "failed",
                                    "error": {
                                        "type": type(e).__name__,
                                        "message": str(e),
                                    },
                                    "success": False,
                                }
                            )

            thread = threading.Thread(target=execute_job, daemon=True)
            thread.start()

            # Send job_id back to client
            _send_response(
                client_sock,
                {
                    "success": True,
                    "job_id": job_id,
                },
            )

        elif command == "poll":
            # Poll for job result
            job_id = request.get("job_id")
            if not job_id:
                _send_response(
                    client_sock,
                    {
                        "success": False,
                        "error": "Missing job_id",
                    },
                )
                return

            with jobs_lock:
                job = jobs.get(job_id)
                if not job:
                    _send_response(
                        client_sock,
                        {
                            "success": False,
                            "error": "Job not found",
                        },
                    )
                    return

                status = job.get("status")
                if status == "pending":
                    _send_response(
                        client_sock,
                        {
                            "success": True,
                            "status": "pending",
                        },
                    )
                elif status in ("completed", "failed"):
                    _send_response(
                        client_sock,
                        {
                            "success": job.get("success", False),
                            "status": status,
                            "result": job.get("result"),
                            "error": job.get("error"),
                        },
                    )
                else:
                    _send_response(
                        client_sock,
                        {
                            "success": False,
                            "error": f"Unknown job status: {status}",
                        },
                    )

        elif command == "delete":
            # Delete job from queue
            job_id = request.get("job_id")
            if not job_id:
                _send_response(
                    client_sock,
                    {
                        "success": False,
                        "error": "Missing job_id",
                    },
                )
                return

            with jobs_lock:
                if job_id in jobs:
                    del jobs[job_id]
                    _send_response(
                        client_sock,
                        {
                            "success": True,
                        },
                    )
                else:
                    _send_response(
                        client_sock,
                        {
                            "success": False,
                            "error": "Job not found",
                        },
                    )

        else:
            _send_response(
                client_sock,
                {
                    "success": False,
                    "error": f"Unknown command: {command}",
                },
            )

    except Exception as e:
        logger.error(f"Error handling client connection: {e}", exc_info=True)
        try:
            _send_response(
                client_sock,
                {
                    "success": False,
                    "error": str(e),
                },
            )
        except Exception:
            pass
    finally:
        try:
            client_sock.close()
        except Exception:
            pass


def _cleanup_expired_jobs(
    jobs: Dict[str, Dict[str, Any]],
    jobs_lock: threading.Lock,
    job_timeout: float = 300.0,
) -> None:
    """
    Clean up expired jobs from queue.

    Args:
        jobs: Dictionary storing job results
        jobs_lock: Lock for jobs dictionary
        job_timeout: Job timeout in seconds
    """
    now = datetime.now()
    expired_job_ids = []

    with jobs_lock:
        for job_id, job in jobs.items():
            created_at = job.get("created_at")
            if created_at and (now - created_at) > timedelta(seconds=job_timeout):
                expired_job_ids.append(job_id)

        for job_id in expired_job_ids:
            logger.debug(f"Cleaning up expired job: {job_id}")
            del jobs[job_id]

    if expired_job_ids:
        logger.info(f"Cleaned up {len(expired_job_ids)} expired jobs")


def run_db_worker(
    db_path: str,
    socket_path: str,
    worker_log_path: Optional[str] = None,
    job_timeout: float = 300.0,
    cleanup_interval: float = 60.0,
) -> None:
    """
    Run database worker process.

    This function runs in a separate process and handles database operations
    via Unix socket. Clients submit jobs, poll for results, and delete completed jobs.

    Args:
        db_path: Path to SQLite database file
        socket_path: Path to Unix socket for communication
        worker_log_path: Path to worker log file (optional)
        job_timeout: Job timeout in seconds (default: 5 minutes)
        cleanup_interval: Interval for cleaning up expired jobs in seconds (default: 60s)
    """
    # Setup logging
    _setup_worker_logging(worker_log_path)

    logger.info(f"🚀 DB worker started for database: {db_path}, socket: {socket_path}")

    # Setup signal handlers for graceful shutdown
    shutdown_event = False

    def signal_handler(signum, frame):
        """Handle shutdown signals."""
        nonlocal shutdown_event
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event = True

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Jobs storage: job_id -> {status, result, error, created_at}
    jobs: Dict[str, Dict[str, Any]] = {}
    jobs_lock = threading.Lock()

    # Cleanup thread
    def cleanup_worker():
        """Background thread for cleaning up expired jobs."""
        while not shutdown_event:
            time.sleep(cleanup_interval)
            if not shutdown_event:
                _cleanup_expired_jobs(jobs, jobs_lock, job_timeout)

    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()

    # Remove existing socket file if it exists
    socket_file = Path(socket_path)
    if socket_file.exists():
        socket_file.unlink()

    # Create Unix socket server
    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(socket_path)
    server_sock.listen(5)
    server_sock.settimeout(1.0)  # Allow checking shutdown_event

    logger.info(f"DB worker listening on socket: {socket_path}")

    try:
        while not shutdown_event:
            try:
                client_sock, _ = (
                    server_sock.accept()
                )  # addr is not used for Unix sockets
                # Handle client in separate thread
                thread = threading.Thread(
                    target=_handle_client_connection,
                    args=(client_sock, db_path, jobs, jobs_lock, job_timeout),
                    daemon=True,
                )
                thread.start()
            except socket.timeout:
                # Timeout is expected, continue loop to check shutdown_event
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
