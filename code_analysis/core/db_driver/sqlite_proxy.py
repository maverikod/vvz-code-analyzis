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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseDatabaseDriver
from .sqlite_proxy_execute import execute_operation_impl
from .sqlite_proxy_socket import send_request_via_socket
from .sqlite_proxy_worker import get_socket_path_for_worker
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
        self.poll_interval: float = 0.01  # 10ms default for IPC latency
        self.worker_log_path: Optional[str] = None
        self._lastrowid: Optional[int] = None
        self._socket_timeout: float = 5.0
        self._transaction_id: Optional[str] = None
        logger.debug("[SQLITE_PROXY] __init__ completed, poll_interval=%s", self.poll_interval)

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

        for attr, default in [
            ("poll_interval", 0.01),
            ("command_timeout", 30.0),
            ("_socket_timeout", 5.0),
            ("_worker_initialized", False),
            ("_lastrowid", None),
        ]:
            if not hasattr(self, attr):
                setattr(self, attr, default)

        self.db_path = Path(config["path"]).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("[SQLITE_PROXY] db_path resolved: %s", self.db_path)
        wc = config.get("worker_config", {})
        self.command_timeout = wc.get("command_timeout", self.command_timeout)
        self.poll_interval = wc.get("poll_interval", self.poll_interval)
        self.worker_log_path = wc.get("worker_log_path")
        self._start_worker()
        logger.info("[SQLITE_PROXY] Connected to database: %s", self.db_path)

    def _start_worker(self) -> None:
        """Connect to existing DB worker process via global manager."""
        if self._worker_initialized and self._socket_path:
            logger.info(
                "[SQLITE_PROXY] Worker already initialized (socket: %s)",
                self._socket_path,
            )
            return

        logger.info(
            "[SQLITE_PROXY] Connecting to DB worker via manager (db_path: %s)",
            self.db_path,
        )
        try:
            self._socket_path = get_socket_path_for_worker(
                self.db_path,
                self.worker_log_path,
            )
            self._worker_initialized = True
            logger.info(
                "[SQLITE_PROXY] Connected to DB worker (socket: %s)",
                self._socket_path,
            )
        except Exception as e:
            logger.error(
                "[SQLITE_PROXY] Failed to start worker: %s: %s",
                type(e).__name__,
                e,
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
        """Send request to worker via socket; ensure worker running and socket exists."""
        logger.debug(
            "[SQLITE_PROXY] _send_request called, socket_path=%s, initialized=%s",
            self._socket_path,
            self._worker_initialized,
        )

        if not self._worker_initialized or not self._socket_path:
            logger.warning(
                "[SQLITE_PROXY] Worker not initialized, attempting to reconnect..."
            )
            try:
                self._start_worker()
            except Exception as e:
                logger.error("Failed to reconnect worker: %s", e, exc_info=True)
                raise RuntimeError(
                    "Worker not initialized. Ensure connect() was called."
                ) from e
            if not self._worker_initialized or not self._socket_path:
                raise RuntimeError(
                    "Worker not initialized. Ensure connect() was called."
                )

        socket_file = Path(self._socket_path)
        if not socket_file.exists():
            logger.warning("Socket file does not exist, reconnecting...")
            self._worker_initialized = False
            self._start_worker()
            if not Path(self._socket_path).exists():
                raise DatabaseOperationError(
                    message=f"Socket file does not exist after reconnect: {self._socket_path}",
                    operation=request.get("command", "unknown"),
                    db_path=str(self.db_path),
                )

        return send_request_via_socket(
            self._socket_path,
            request,
            self._socket_timeout,
            str(self.db_path) if self.db_path else "",
        )

    def _execute_operation(
        self,
        operation: str,
        sql: Optional[str] = None,
        params: Optional[Tuple[Any, ...]] = None,
        table_name: Optional[str] = None,
        transaction_id: Optional[str] = None,
    ) -> Any:
        """Execute database operation via worker (submit, poll, delete)."""
        return execute_operation_impl(
            ensure_worker_running=self._ensure_worker_running,
            send_request=self._send_request,
            command_timeout=self.command_timeout,
            poll_interval=self.poll_interval,
            db_path=self.db_path,
            truncate_sql=lambda s, m=200: self._truncate_sql(s, m),
            operation=operation,
            sql=sql,
            params=params,
            table_name=table_name,
            transaction_id=transaction_id,
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
