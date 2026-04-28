"""
PostgreSQL driver for database driver process (psycopg3).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.retry_policy import RetryPolicy

from ..exceptions import (
    DriverConnectionError,
    DriverOperationError,
    TransientDatabaseError,
)
from .base import BaseDatabaseDriver, DbIdentity
from .postgres_migrations import ensure_postgres_schema
from .postgres_operations import PostgreSQLOperations
from .postgres_run import run_execute, run_execute_batch
from .postgres_schema import PostgreSQLSchemaManager
from .postgres_tables import run_create_table_postgres, run_drop_table_postgres
from .postgres_transactions import PostgreSQLTransactionManager

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def _is_self_managed_transaction(transaction_id: Optional[str]) -> bool:
    """True when transaction_id is missing, empty, or exactly 'local' (not external)."""
    if transaction_id is None or transaction_id == "":
        return True
    return transaction_id == "local"


def _is_connection_lost_error(exc: BaseException) -> bool:
    """True if psycopg/main connection should be reopened and retried once."""
    msg = str(exc).lower()
    if "server closed the connection" in msg or "connection closed" in msg:
        return True
    if "connection" in msg and (
        "closed" in msg or "lost" in msg or "broken" in msg or "terminated" in msg
    ):
        return True
    try:
        import psycopg

        return isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))
    except ImportError:
        return False


def _connect_kwargs_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    from code_analysis.core.env_loader import load_dotenv_best_effort

    load_dotenv_best_effort()

    dsn = config.get("dsn")
    if dsn and str(dsn).strip():
        return {"conninfo": str(dsn)}

    dbname = config.get("dbname") or config.get("database")
    if not dbname:
        raise DriverConnectionError(
            "PostgreSQL driver requires 'dbname' or 'database' (or 'dsn') in config"
        )
    password_env = config.get("password_env")
    password = str(config.get("password", "") or "")
    if password_env:
        import os

        env_name = str(password_env).strip()
        if env_name:
            from_env = os.environ.get(env_name)
            if from_env is not None:
                password = from_env
    kwargs: Dict[str, Any] = {
        "host": config.get("host", "localhost"),
        "port": int(config.get("port", 5432)),
        "dbname": str(dbname),
        "user": str(config.get("user", "postgres")),
        "password": password,
    }
    if config.get("sslmode"):
        kwargs["sslmode"] = str(config["sslmode"])
    return kwargs


class PostgreSQLDriver(BaseDatabaseDriver):
    """PostgreSQL implementation of the database driver RPC contract."""

    def __init__(self) -> None:
        self.conn: Any = None
        self._connect_kwargs: Dict[str, Any] = {}
        self._full_schema: Dict[str, Any] = {}
        self._schema_tables: Dict[str, Any] = {}
        self._transaction_manager: Optional[PostgreSQLTransactionManager] = None
        self._schema_manager: Optional[PostgreSQLSchemaManager] = None
        self._operations: Optional[PostgreSQLOperations] = None
        self._query_journal: Any = None
        self._retry_policy: RetryPolicy = RetryPolicy()
        self._qa_transient_injections_remaining: int = 0

    def qa_set_db_retry_injections(self, remaining: int) -> Dict[str, Any]:
        """QA only: next N self-managed execute/execute_batch attempts raise a synthetic deadlock."""
        n = int(remaining)
        if n < 0 or n > 20:
            raise DriverOperationError("remaining must be between 0 and 20")
        self._qa_transient_injections_remaining = n
        return {"success": True, "remaining": self._qa_transient_injections_remaining}

    def _qa_maybe_inject_transient(self) -> None:
        if self._qa_transient_injections_remaining <= 0:
            return
        self._qa_transient_injections_remaining -= 1
        raise TransientDatabaseError(
            "qa injected transient (mcp plan hook)",
            sqlstate="40P01",
            error_kind="deadlock",
            retryable=True,
            original_error=None,
            attempts=None,
            commit_outcome_unknown=False,
        )

    def connect(self, config: Dict[str, Any]) -> None:
        try:
            import psycopg
        except ImportError as e:
            raise DriverConnectionError(
                "PostgreSQL driver requires psycopg (pip install 'psycopg[binary]>=3.1' or pip install -e .)"
            ) from e

        try:
            self._connect_kwargs = _connect_kwargs_from_config(config)
            logger.info(
                "PostgreSQL driver connecting to host=%s dbname=%s",
                self._connect_kwargs.get("host")
                or self._connect_kwargs.get("conninfo", "")[:40],
                self._connect_kwargs.get("dbname", ""),
            )
            self.conn = psycopg.connect(**self._connect_kwargs)
            self.conn.autocommit = False

            self._full_schema = get_schema_definition()
            self._schema_tables = self._full_schema["tables"]

            ensure_postgres_schema(self.conn, self._full_schema)

            self._retry_policy = RetryPolicy.from_driver_config(config)
            # Canonical database driver config keys only (Step 03).
            lock_timeout_seconds = config.get("lock_timeout_seconds")
            statement_timeout_seconds = config.get("statement_timeout_seconds")
            self._transaction_manager = PostgreSQLTransactionManager(
                self._connect_kwargs,
                lock_timeout_seconds=lock_timeout_seconds,
                statement_timeout_seconds=statement_timeout_seconds,
            )
            self._schema_manager = PostgreSQLSchemaManager(self.conn)
            self._operations = PostgreSQLOperations(self.conn, self._schema_tables)

            query_log_path = config.get("query_log_path")
            if query_log_path:
                from ..sqlite_query_journal import (
                    DEFAULT_JOURNAL_BACKUP_COUNT,
                    DEFAULT_JOURNAL_MAX_BYTES,
                    SQLiteQueryJournal,
                )

                max_bytes = config.get("query_log_max_bytes", DEFAULT_JOURNAL_MAX_BYTES)
                backup_count = config.get(
                    "query_log_backup_count", DEFAULT_JOURNAL_BACKUP_COUNT
                )
                self._query_journal = SQLiteQueryJournal(
                    Path(query_log_path),
                    max_bytes=max_bytes,
                    backup_count=backup_count,
                )
                logger.info("Query journal enabled: %s", query_log_path)
        except DriverConnectionError:
            raise
        except Exception as e:
            raise DriverConnectionError(f"Failed to connect to PostgreSQL: {e}") from e

    def commit(self) -> None:
        """Commit the main connection (CodeDatabase transaction_id=local)."""
        if self.conn:
            self.conn.commit()

    def rollback(self) -> None:
        """Rollback the main connection."""
        if self.conn:
            self.conn.rollback()

    def _reconnect_main(self) -> None:
        """Rebuild main connection and dependent managers (after dropped connection)."""
        import psycopg

        logger.warning("PostgreSQLDriver: reconnecting main session")
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
        self.conn = psycopg.connect(**self._connect_kwargs)
        self.conn.autocommit = False
        ensure_postgres_schema(self.conn, self._full_schema)
        self._schema_manager = PostgreSQLSchemaManager(self.conn)
        self._operations = PostgreSQLOperations(self.conn, self._schema_tables)

    def _sleep_before_retry(self, attempt_1based: int) -> None:
        time.sleep(self._retry_policy.delay_for_attempt(attempt_1based))

    def _run_once_with_reconnect_on_lost(self, func: Callable[[], _T]) -> _T:
        try:
            return func()
        except Exception as e:
            if not _is_connection_lost_error(e):
                raise
            if not self.conn:
                raise
            try:
                self.conn.rollback()
            except Exception:
                pass
            self._reconnect_main()
            if not self.conn:
                raise DriverOperationError("Database connection not established")
            return func()

    def _run_self_managed_with_retry(
        self, operation_name: str, func: Callable[[], _T]
    ) -> _T:
        max_a = self._retry_policy.attempts
        for attempt in range(1, max_a + 1):
            try:
                return self._run_once_with_reconnect_on_lost(func)
            except TransientDatabaseError as e:
                if not (e.retryable and not e.commit_outcome_unknown):
                    raise
                if attempt >= max_a:
                    raise TransientDatabaseError(
                        e.args[0] if e.args else str(e),
                        sqlstate=e.sqlstate,
                        error_kind=e.error_kind,
                        retryable=e.retryable,
                        original_error=e.original_error,
                        attempts=max_a,
                        commit_outcome_unknown=e.commit_outcome_unknown,
                    ) from e
                if not self.conn:
                    raise DriverOperationError("Database connection not established")
                try:
                    self.conn.rollback()
                except Exception as rb:
                    raise DriverOperationError(
                        f"Rollback before database retry failed: {rb}"
                    ) from rb
                logger.info(
                    "[DB_RETRY] backend=postgres layer=driver operation=%s "
                    "attempt=%s/%s sqlstate=%s error_kind=%s",
                    operation_name,
                    attempt + 1,
                    max_a,
                    e.sqlstate,
                    e.error_kind,
                )
                self._sleep_before_retry(attempt)
        raise RuntimeError("PostgreSQL driver: retry loop exited without result")

    def disconnect(self) -> None:
        try:
            if self._query_journal:
                try:
                    self._query_journal.close()
                except Exception:
                    pass
                self._query_journal = None
            if self._transaction_manager:
                self._transaction_manager.close_all()
            if self.conn:
                self.conn.close()
                self.conn = None
        except Exception as e:
            raise DriverConnectionError(f"Failed to disconnect: {e}") from e

    def create_table(self, schema: Dict[str, Any]) -> bool:
        if not self.conn:
            raise DriverOperationError("Database connection not established")
        return run_create_table_postgres(self.conn, schema)

    def drop_table(self, table_name: str) -> bool:
        if not self.conn:
            raise DriverOperationError("Database connection not established")
        return run_drop_table_postgres(self.conn, table_name)

    def insert(self, table_name: str, data: Dict[str, Any]) -> Optional[DbIdentity]:
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        try:
            return self._operations.insert(table_name, data)
        except Exception as e:
            if _is_connection_lost_error(e):
                self._reconnect_main()
                return self._operations.insert(table_name, data)
            raise

    def update(
        self, table_name: str, where: Dict[str, Any], data: Dict[str, Any]
    ) -> int:
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        try:
            return self._operations.update(table_name, where, data)
        except Exception as e:
            if _is_connection_lost_error(e):
                self._reconnect_main()
                return self._operations.update(table_name, where, data)
            raise

    def delete(self, table_name: str, where: Dict[str, Any]) -> int:
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        try:
            return self._operations.delete(table_name, where)
        except Exception as e:
            if _is_connection_lost_error(e):
                self._reconnect_main()
                return self._operations.delete(table_name, where)
            raise

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        try:
            return self._operations.select(
                table_name, where, columns, limit, offset, order_by
            )
        except Exception as e:
            if _is_connection_lost_error(e):
                self._reconnect_main()
                return self._operations.select(
                    table_name, where, columns, limit, offset, order_by
                )
            raise

    def execute_batch(
        self,
        operations: List[Tuple[str, Optional[tuple]]],
        transaction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not operations:
            return []
        if not _is_self_managed_transaction(transaction_id):
            if not self._transaction_manager:
                raise DriverOperationError("Transaction manager not initialized")
            if transaction_id not in self._transaction_manager._transactions:
                raise DriverOperationError(f"Transaction {transaction_id} not found")
            conn = self._transaction_manager._transactions[transaction_id]
            return run_execute_batch(
                conn,
                operations,
                transaction_id,
                self._query_journal,
                self._schema_tables,
            )
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        def do_run() -> List[Dict[str, Any]]:
            self._qa_maybe_inject_transient()
            return run_execute_batch(
                self.conn,
                operations,
                transaction_id,
                self._query_journal,
                self._schema_tables,
            )

        return self._run_self_managed_with_retry("execute_batch", do_run)

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not _is_self_managed_transaction(transaction_id):
            if not self._transaction_manager:
                raise DriverOperationError("Transaction manager not initialized")
            if transaction_id not in self._transaction_manager._transactions:
                raise DriverOperationError(f"Transaction {transaction_id} not found")
            conn = self._transaction_manager._transactions[transaction_id]
            return run_execute(
                conn,
                sql,
                params,
                transaction_id,
                self._query_journal,
                self._schema_tables,
            )
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        def do_run() -> Dict[str, Any]:
            self._qa_maybe_inject_transient()
            return run_execute(
                self.conn,
                sql,
                params,
                transaction_id,
                self._query_journal,
                self._schema_tables,
            )

        return self._run_self_managed_with_retry("execute", do_run)

    def begin_transaction(self) -> str:
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.begin_transaction()

    def commit_transaction(self, transaction_id: str) -> bool:
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.commit_transaction(transaction_id)

    def rollback_transaction(self, transaction_id: str) -> bool:
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.rollback_transaction(transaction_id)

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        if not self._schema_manager:
            raise DriverOperationError("Schema manager not initialized")
        return self._schema_manager.get_table_info(table_name)

    def sync_schema(
        self, schema_definition: Dict[str, Any], backup_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self._schema_manager:
            raise DriverOperationError("Schema manager not initialized")
        return self._schema_manager.sync_schema(
            schema_definition, backup_dir, self.create_table
        )
