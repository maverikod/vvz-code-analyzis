"""
SQLite database driver proxy.

This proxy driver sends database operations to a separate process worker,
ensuring thread/process safety.

Architecture:
1. Client connects via socket, sends request, receives job_id, disconnects
2. Client periodically polls server for results
3. Client sends delete command after receiving results
4. Server automatically cleans up expired jobs

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import socket
import json
import struct
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseDatabaseDriver
from ..db_worker_manager import get_db_worker_manager
from ..exceptions import DatabaseOperationError

logger = logging.getLogger(__name__)


class SQLiteDriverProxy(BaseDatabaseDriver):
    """
    Proxy driver that sends SQLite operations to a separate process worker.

    This driver implements the BaseDatabaseDriver interface but delegates
    all operations to a dedicated DB worker process via IPC queues.
    """

    @property
    def is_thread_safe(self) -> bool:
        """Proxy driver is thread-safe as operations are serialized through queue."""
        return True

    def __init__(self) -> None:
        """Initialize SQLite proxy driver."""
        # Initialize all attributes first
        self.conn: Optional[Any] = None  # Not used, kept for compatibility
        self.db_path: Optional[Path] = None
        self._socket_path: Optional[str] = None
        self._worker_initialized: bool = False
        self.command_timeout: float = 30.0
        self.poll_interval: float = (
            0.01  # Polling interval in seconds (default: 10ms; reduced for IPC latency)
        )
        self.worker_log_path: Optional[str] = None
        self._lastrowid: Optional[int] = None
        self._socket_timeout: float = 5.0  # Socket connection timeout
        self._transaction_id: Optional[str] = (
            None  # Transaction ID for tracking transactions
        )
        logger.debug(
            f"[SQLITE_PROXY] __init__ completed, poll_interval={self.poll_interval}"
        )

    def connect(self, config: Dict[str, Any]) -> None:
        """
        Establish connection to worker process.

        Args:
            config: Configuration dict with:
                - path: Path to SQLite database file
                - worker_config (optional): Configuration for worker:
                    - command_timeout: Timeout for commands in seconds
                    - poll_interval: Polling interval in seconds
                    - worker_log_path: Path to worker log file
        """
        logger.info("[SQLITE_PROXY] connect() called")
        if "path" not in config:
            raise ValueError("SQLite proxy driver requires 'path' in config")

        # Ensure all attributes are initialized (defensive programming)
        if not hasattr(self, "poll_interval"):
            self.poll_interval = 0.01
            logger.warning(
                "[SQLITE_PROXY] poll_interval not initialized, using default 0.01"
            )
        if not hasattr(self, "command_timeout"):
            self.command_timeout = 30.0
            logger.warning(
                "[SQLITE_PROXY] command_timeout not initialized, using default 30.0"
            )
        if not hasattr(self, "_socket_timeout"):
            self._socket_timeout = 5.0
        if not hasattr(self, "_worker_initialized"):
            self._worker_initialized = False
        if not hasattr(self, "_lastrowid"):
            self._lastrowid = None

        self.db_path = Path(config["path"]).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"[SQLITE_PROXY] db_path resolved: {self.db_path}")

        # Get worker config
        worker_config = config.get("worker_config", {})
        # Use getattr to safely get current values (defensive - in case __init__ wasn't called)
        current_command_timeout = getattr(self, "command_timeout", 30.0)
        current_poll_interval = getattr(self, "poll_interval", 0.01)

        # Update from config, using current values as defaults
        new_command_timeout = worker_config.get(
            "command_timeout", current_command_timeout
        )
        new_poll_interval = worker_config.get("poll_interval", current_poll_interval)

        self.command_timeout = new_command_timeout
        self.poll_interval = new_poll_interval
        self.worker_log_path = worker_config.get("worker_log_path")
        logger.debug(
            f"[SQLITE_PROXY] connect() updated poll_interval={self.poll_interval}, command_timeout={self.command_timeout}"
        )

        # Start worker process
        self._start_worker()

        logger.info(
            f"[SQLITE_PROXY] SQLite proxy driver connected to database: {self.db_path}"
        )

    def _start_worker(self) -> None:
        """Connect to existing DB worker process via global manager."""
        if self._worker_initialized and self._socket_path:
            logger.info(
                f"[SQLITE_PROXY] Worker already initialized (socket: {self._socket_path})"
            )
            return

        logger.info(
            f"[SQLITE_PROXY] Connecting to DB worker via manager (db_path: {self.db_path})"
        )

        # Get existing worker or start new one via global manager
        # Note: Worker should be started from main process, not from daemon workers
        # If worker doesn't exist, manager will start it (but this should be rare)
        try:
            worker_manager = get_db_worker_manager()
            logger.info(
                "[SQLITE_PROXY] Got worker manager, calling get_or_start_worker..."
            )
            worker_info = worker_manager.get_or_start_worker(
                str(self.db_path),
                self.worker_log_path,
            )
            logger.info(
                f"[SQLITE_PROXY] get_or_start_worker returned: worker_info keys: {list(worker_info.keys()) if worker_info else 'None'}"
            )

            self._socket_path = worker_info.get("socket_path")
            if not self._socket_path:
                raise RuntimeError(f"No socket_path in worker_info: {worker_info}")

            logger.info(f"[SQLITE_PROXY] Got socket_path: {self._socket_path}")

            # Verify socket file exists
            socket_file = Path(self._socket_path)
            if not socket_file.exists():
                logger.warning(
                    f"[SQLITE_PROXY] Socket file does not exist: {self._socket_path}, waiting..."
                )
                import time

                max_wait = 5.0
                wait_interval = 0.1
                waited = 0.0
                while not socket_file.exists() and waited < max_wait:
                    time.sleep(wait_interval)
                    waited += wait_interval
                if not socket_file.exists():
                    raise RuntimeError(
                        f"Socket file not created after {waited:.1f}s: {self._socket_path}"
                    )
                logger.info(
                    f"[SQLITE_PROXY] Socket file exists after {waited:.1f}s wait"
                )

            self._worker_initialized = True
            logger.info(
                f"[SQLITE_PROXY] Connected to DB worker (socket: {self._socket_path}, exists: {socket_file.exists()})"
            )
        except Exception as e:
            logger.error(
                f"[SQLITE_PROXY] Failed to start worker: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise

    def _ensure_worker_running(self) -> None:
        """Ensure worker process is running."""
        if not self._worker_initialized or not self._socket_path:
            # Try to reconnect instead of failing immediately
            logger.warning(
                "[SQLITE_PROXY] Worker not initialized, attempting to reconnect..."
            )
            try:
                self._start_worker()
            except Exception as e:
                logger.error(
                    f"[SQLITE_PROXY] Failed to reconnect worker: {e}",
                    exc_info=True,
                )
                raise RuntimeError(
                    "Worker not initialized. Ensure connect() was called."
                ) from e
            # Verify reconnection was successful
            if not self._worker_initialized or not self._socket_path:
                raise RuntimeError(
                    "Worker not initialized. Ensure connect() was called."
                )

        # Check if socket file exists
        if not Path(self._socket_path).exists():
            logger.warning("[SQLITE_PROXY] Worker socket not found, reconnecting...")
            self._worker_initialized = False
            self._start_worker()

    def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send request to worker via socket and receive response.

        Args:
            request: Request dictionary

        Returns:
            Response dictionary

        Raises:
            DatabaseOperationError: If communication fails
        """
        logger.debug(
            f"[SQLITE_PROXY] _send_request called, socket_path: {self._socket_path}, initialized: {self._worker_initialized}"
        )

        # Ensure worker is running before sending request
        if not self._worker_initialized or not self._socket_path:
            # Try to reconnect instead of failing immediately
            logger.warning(
                f"[SQLITE_PROXY] Worker not initialized! initialized: {self._worker_initialized}, socket_path: {self._socket_path}, attempting to reconnect..."
            )
            try:
                self._start_worker()
            except Exception as e:
                logger.error(
                    f"[SQLITE_PROXY] Failed to reconnect worker: {e}",
                    exc_info=True,
                )
                raise RuntimeError(
                    "Worker not initialized. Ensure connect() was called."
                ) from e
            # Verify reconnection was successful
            if not self._worker_initialized or not self._socket_path:
                logger.error(
                    f"[SQLITE_PROXY] Worker still not initialized after reconnect attempt! initialized: {self._worker_initialized}, socket_path: {self._socket_path}"
                )
                raise RuntimeError(
                    "Worker not initialized. Ensure connect() was called."
                )

        # Verify socket file exists before attempting connection
        socket_file = Path(self._socket_path)
        if not socket_file.exists():
            logger.error(
                f"[SQLITE_PROXY] Socket file does not exist: {self._socket_path}"
            )
            logger.error("[SQLITE_PROXY] Attempting to reconnect...")
            self._worker_initialized = False
            self._start_worker()
            socket_file = Path(self._socket_path)
            if not socket_file.exists():
                raise DatabaseOperationError(
                    f"Socket file does not exist after reconnect: {self._socket_path}",
                    operation=request.get("command", "unknown"),
                )

        logger.debug(f"[SQLITE_PROXY] Connecting to socket: {self._socket_path}")
        sock = None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self._socket_timeout)
            sock.connect(self._socket_path)
            logger.debug("[SQLITE_PROXY] Successfully connected to socket")

            # Send request
            data = json.dumps(request).encode("utf-8")
            length = struct.pack("!I", len(data))
            sock.sendall(length + data)

            # Receive response
            length_data = b""
            while len(length_data) < 4:
                chunk = sock.recv(4 - len(length_data))
                if not chunk:
                    raise DatabaseOperationError(
                        message="Connection closed by worker",
                        operation=request.get("command", "unknown"),
                        db_path=str(self.db_path),
                    )
                length_data += chunk

            length = struct.unpack("!I", length_data)[0]
            data = b""
            while len(data) < length:
                chunk = sock.recv(length - len(data))
                if not chunk:
                    raise DatabaseOperationError(
                        message="Connection closed by worker",
                        operation=request.get("command", "unknown"),
                        db_path=str(self.db_path),
                    )
                data += chunk

            return json.loads(data.decode("utf-8"))

        except socket.timeout:
            raise DatabaseOperationError(
                message=f"Socket timeout after {self._socket_timeout}s",
                operation=request.get("command", "unknown"),
                db_path=str(self.db_path),
            )
        except Exception as e:
            raise DatabaseOperationError(
                message=f"Error communicating with worker: {e}",
                operation=request.get("command", "unknown"),
                db_path=str(self.db_path),
                cause=e,
            ) from e
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def _execute_operation(
        self,
        operation: str,
        sql: Optional[str] = None,
        params: Optional[Tuple[Any, ...]] = None,
        table_name: Optional[str] = None,
        transaction_id: Optional[str] = None,
    ) -> Any:
        """
        Execute database operation via worker process.

        Args:
            operation: Operation type (execute, fetchone, fetchall, commit,
                rollback, lastrowid, get_table_info)
            sql: SQL statement (for execute, fetchone, fetchall)
            params: Query parameters tuple (optional)
            table_name: Table name (for get_table_info)

        Returns:
            Operation result

        Raises:
            DatabaseOperationError: If operation fails or times out
        """
        self._ensure_worker_running()

        # Generate unique job ID
        job_id = f"{operation}_{uuid.uuid4().hex[:8]}"
        logger.debug(
            f"[SQLITE_PROXY] Executing operation '{operation}' (job_id={job_id})"
        )

        # Step 1: Submit job
        submit_request = {
            "command": "submit",
            "job_id": job_id,
            "operation": operation,
        }
        if sql is not None:
            submit_request["sql"] = sql
        if params is not None:
            submit_request["params"] = params
        if table_name is not None:
            submit_request["table_name"] = table_name
        # Pass transaction_id if provided (for transaction support)
        if transaction_id is not None:
            submit_request["transaction_id"] = transaction_id

        try:
            submit_response = self._send_request(submit_request)
            if not submit_response.get("success"):
                error = submit_response.get("error", "Unknown error")
                raise DatabaseOperationError(
                    message=f"Failed to submit job: {error}",
                    operation=operation,
                    db_path=str(self.db_path),
                    sql=sql,
                    params=params,
                    timeout=self.command_timeout,
                )
        except DatabaseOperationError:
            raise
        except Exception as e:
            raise DatabaseOperationError(
                message=f"Failed to submit job: {e}",
                operation=operation,
                db_path=str(self.db_path),
                sql=sql,
                params=params,
                timeout=self.command_timeout,
                cause=e,
            ) from e

        # Step 2: Poll for result
        max_wait = self.command_timeout
        start_time = time.time()
        poll_interval = self.poll_interval

        while time.time() - start_time < max_wait:
            try:
                # Poll for result
                poll_request = {
                    "command": "poll",
                    "job_id": job_id,
                }
                poll_response = self._send_request(poll_request)

                if not poll_response.get("success"):
                    error = poll_response.get("error", "Unknown error")
                    raise DatabaseOperationError(
                        message=f"Poll failed: {error}",
                        operation=operation,
                        db_path=str(self.db_path),
                        sql=sql,
                        params=params,
                        timeout=self.command_timeout,
                    )

                status = poll_response.get("status")
                if status == "pending":
                    # Still processing, wait and poll again
                    time.sleep(poll_interval)
                    continue
                elif status in ("completed", "failed"):
                    # Job completed, get result
                    result = poll_response.get("result")
                    error = poll_response.get("error")

                    # Step 3: Delete job from queue
                    try:
                        delete_request = {
                            "command": "delete",
                            "job_id": job_id,
                        }
                        self._send_request(delete_request)
                    except Exception as e:
                        logger.warning(f"Failed to delete job {job_id}: {e}")

                    if status == "failed" or not poll_response.get("success", False):
                        error_msg = (
                            error.get("message", str(error))
                            if isinstance(error, dict)
                            else str(error)
                        )
                        logger.error(
                            f"Database operation '{operation}' failed: {error_msg}",
                            extra={
                                "operation": operation,
                                "db_path": str(self.db_path),
                                "sql": self._truncate_sql(sql),
                                "params": params,
                            },
                        )
                        raise DatabaseOperationError(
                            message=f"Database operation failed: {error_msg}",
                            operation=operation,
                            db_path=str(self.db_path),
                            sql=sql,
                            params=params,
                            timeout=self.command_timeout,
                        )

                    logger.debug(
                        f"[SQLITE_PROXY] Operation '{operation}' completed successfully"
                    )
                    # Extract result from worker response format
                    # Worker returns: {"success": True, "result": {...}, "error": None}
                    # We need to return the actual result dict
                    if isinstance(result, dict) and "result" in result:
                        return result["result"]
                    return result
                else:
                    raise DatabaseOperationError(
                        message=f"Unknown job status: {status}",
                        operation=operation,
                        db_path=str(self.db_path),
                        sql=sql,
                        params=params,
                        timeout=self.command_timeout,
                    )

            except DatabaseOperationError:
                raise
            except Exception as e:
                logger.error(
                    f"Error polling for result: {e}",
                    extra={
                        "operation": operation,
                        "db_path": str(self.db_path),
                        "job_id": job_id,
                    },
                    exc_info=True,
                )
                raise DatabaseOperationError(
                    message=f"Error polling for result: {e}",
                    operation=operation,
                    db_path=str(self.db_path),
                    sql=sql,
                    params=params,
                    timeout=self.command_timeout,
                    cause=e,
                ) from e

        # Timeout
        logger.error(
            f"Database operation '{operation}' timed out after {max_wait}s",
            extra={
                "operation": operation,
                "db_path": str(self.db_path),
                "sql": self._truncate_sql(sql),
                "timeout": max_wait,
                "job_id": job_id,
            },
        )
        raise DatabaseOperationError(
            message=f"Database operation '{operation}' timed out after {max_wait}s",
            operation=operation,
            db_path=str(self.db_path),
            sql=sql,
            params=params,
            timeout=max_wait,
        )

    def disconnect(self) -> None:
        """Close connection to worker process."""
        # Don't stop worker here - it's managed globally and may be used by other connections
        # Worker will be stopped when server shuts down via WorkerManager or atexit handlers
        self._worker_initialized = False
        self._socket_path = None
        logger.info(
            "[SQLITE_PROXY] DB driver disconnected (worker remains running for other connections)"
        )

    def execute(
        self,
        sql: str,
        params: Optional[Tuple[Any, ...]] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute SQL statement.

        Args:
            sql: SQL statement
            params: Optional parameters tuple
            transaction_id: Optional transaction ID

        Returns:
            Dictionary with operation result
        """
        # Use provided transaction_id or fallback to instance attribute
        if transaction_id is None:
            transaction_id = getattr(self, "_transaction_id", None)
        result = self._execute_operation(
            "execute", sql=sql, params=params, transaction_id=transaction_id
        )
        # Store lastrowid from result
        try:
            if isinstance(result, dict) and "lastrowid" in result:
                val = result.get("lastrowid")
                self._lastrowid = int(val) if val is not None else None
        except Exception:
            self._lastrowid = None
        # Return result dict (matches base driver interface)
        return result if isinstance(result, dict) else {}

    def fetchone(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> Optional[Dict[str, Any]]:
        """Execute SELECT query and return first row."""
        transaction_id = getattr(self, "_transaction_id", None)
        result = self._execute_operation(
            "fetchone", sql=sql, params=params, transaction_id=transaction_id
        )
        if isinstance(result, dict):
            return result
        return None

    def fetchall(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
        """Execute SELECT query and return all rows."""
        transaction_id = getattr(self, "_transaction_id", None)
        result = self._execute_operation(
            "fetchall", sql=sql, params=params, transaction_id=transaction_id
        )
        return result if result is not None else []

    def commit(self) -> None:
        """Commit current transaction."""
        transaction_id = getattr(self, "_transaction_id", None)
        if transaction_id:
            # Commit transaction in worker
            self._execute_operation("commit_transaction", transaction_id=transaction_id)
            self._transaction_id = None
        # If no transaction_id, no-op (backward compatibility)

    def rollback(self) -> None:
        """Rollback current transaction."""
        transaction_id = getattr(self, "_transaction_id", None)
        if transaction_id:
            # Rollback transaction in worker
            self._execute_operation(
                "rollback_transaction", transaction_id=transaction_id
            )
            self._transaction_id = None
        # If no transaction_id, no-op (backward compatibility)

    def sync_schema(
        self, schema_definition: Dict[str, Any], backup_dir: Path
    ) -> Dict[str, Any]:
        """
        Synchronize database schema via worker.

        Args:
            schema_definition: Schema definition from CodeDatabase._get_schema_definition()
            backup_dir: Directory for database backups (from StoragePaths)

        Returns:
            Dict with sync results from worker:
            {
                "success": bool,
                "backup_uuid": Optional[str],
                "changes_applied": List[str],
                "error": Optional[str]
            }

        Raises:
            DatabaseOperationError: If schema sync fails
        """
        if not self._worker_initialized or not self._socket_path:
            raise RuntimeError("Worker not initialized")

        # Ensure backup_dir is passed as string for JSON serialization
        backup_dir_str = str(backup_dir)

        request = {
            "command": "sync_schema",
            "params": {
                "schema_definition": schema_definition,
                "backup_dir": backup_dir_str,
            },
        }

        response = self._send_request(request)
        if not response.get("success"):
            raise DatabaseOperationError(
                f"Schema sync failed: {response.get('error')}",
                operation="sync_schema",
            )

        return response.get("result", {})

    def lastrowid(self) -> Optional[int]:
        """Get last inserted row ID."""
        return self._lastrowid

    def create_schema(self, schema_sql: List[str]) -> None:
        """
        Create database schema.

        Args:
            schema_sql: List of SQL statements for schema creation
        """
        # Execute each statement sequentially
        for sql in schema_sql:
            self.execute(sql)
        # No explicit commit needed: worker auto-commits execute().

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get information about table columns."""
        result = self._execute_operation("get_table_info", table_name=table_name)
        return result if result is not None else []

    def _truncate_sql(self, sql: Optional[str], max_length: int = 200) -> Optional[str]:
        """
        Truncate SQL statement for logging to avoid huge payloads.

        Args:
            sql: SQL statement to truncate
            max_length: Maximum length before truncation

        Returns:
            Truncated SQL statement or None
        """
        if not sql:
            return None
        if len(sql) <= max_length:
            return sql
        return sql[:max_length] + "..."
