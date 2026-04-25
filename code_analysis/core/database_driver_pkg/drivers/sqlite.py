"""
SQLite driver implementation for database driver process.

Works with tables, columns, and cells (low-level operations).
This driver runs in the driver process and handles table-level operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from code_analysis.core.retry_policy import RetryPolicy

from ..exceptions import (
    DriverConnectionError,
    DriverOperationError,
    TransientDatabaseError,
)
from ..sqlite_query_journal import SQLiteQueryJournal
from .base import BaseDatabaseDriver
from .sqlite_migrations import run_all_ensure
from .sqlite_batch import expand_operations, split_batch_sql
from .sqlite_operations import SQLiteOperations
from .sqlite_run import run_execute, run_execute_batch
from .sqlite_schema import SQLiteSchemaManager
from .sqlite_tables import run_create_table, run_drop_table
from .sqlite_transactions import SQLiteTransactionManager

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def _sql_implies_write(sql: str) -> bool:
    """True if any statement in a batch is not a read-only SELECT/EXPLAIN/WITH."""
    for stmt in split_batch_sql(sql):
        s = stmt.strip()
        if not s:
            continue
        u = s.upper()
        if u.startswith("SELECT") or u.startswith("WITH") or u.startswith("EXPLAIN"):
            continue
        return True
    return False


def _execute_batch_implies_write(operations: List[Tuple[str, Optional[tuple]]]) -> bool:
    for sql, _ in expand_operations(operations):
        if _sql_implies_write(sql):
            return True
    return False


class SQLiteDriver(BaseDatabaseDriver):
    """SQLite driver for database driver process.

    Works with tables directly (insert, update, delete, select).
    All operations are table-level, not object-level.

    Batching: execute_batch recognizes multiple statements in one sql (split by ';'),
    expands to a flat list, groups consecutive same-SQL operations for executemany,
    and returns one result per statement in order.
    """

    def __init__(self) -> None:
        """Initialize SQLite driver."""
        self.conn: Optional[sqlite3.Connection] = None
        self.db_path: Optional[Path] = None
        self._transaction_manager: Optional[SQLiteTransactionManager] = None
        self._schema_manager: Optional[SQLiteSchemaManager] = None
        self._operations: Optional[SQLiteOperations] = None
        self._query_journal: Optional[SQLiteQueryJournal] = None
        self._retry_policy: RetryPolicy = RetryPolicy()
        self._qa_transient_injections_remaining: int = 0

    def qa_set_db_retry_injections(self, remaining: int) -> Dict[str, Any]:
        """QA only: next N self-managed execute/execute_batch attempts raise a synthetic busy."""
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
            sqlstate="SQLITE_BUSY",
            error_kind="busy",
            retryable=True,
            original_error=None,
            attempts=None,
            commit_outcome_unknown=False,
        )

    def connect(self, config: Dict[str, Any]) -> None:
        """Establish SQLite connection.

        Args:
            config: Configuration dict with 'path' key pointing to database file

        Raises:
            DriverConnectionError: If connection fails
        """
        if "path" not in config:
            raise DriverConnectionError("SQLite driver requires 'path' in config")

        try:
            self.db_path = Path(config["path"]).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info("SQLite driver connecting to db_path=%s", self.db_path)

            # Fix broken schema (temp_files, no files) before opening so index_file works.
            # Same logic as repair_sqlite_database(force=false); single impl in db_integrity.
            from ...db_integrity import (
                fix_entity_cross_ref_stale_fks,
                recover_files_table_if_needed,
            )

            if recover_files_table_if_needed(self.db_path):
                logger.info(
                    "Recovered files table on connect (temp_files -> files) at %s",
                    self.db_path,
                )
            if fix_entity_cross_ref_stale_fks(self.db_path):
                logger.info(
                    "Fixed entity_cross_ref stale FKs (temp_files/temp_methods) at %s",
                    self.db_path,
                )

            # Create connection
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self.conn.execute("PRAGMA foreign_keys = ON")
            # Wait up to 30s on lock instead of failing immediately
            try:
                self.conn.execute("PRAGMA busy_timeout = 30000")
            except Exception as e:
                logger.warning("Could not set busy_timeout: %s", e)
            # Enable WAL mode for better concurrency
            try:
                self.conn.execute("PRAGMA journal_mode = WAL")
            except Exception as e:
                # WAL might not be supported in some SQLite configurations
                # Log warning but continue - database will work without WAL
                logger.warning(
                    f"Failed to enable WAL mode for database {self.db_path}: {e}. "
                    "Continuing without WAL mode."
                )

            # Initialize managers
            self._transaction_manager = SQLiteTransactionManager(self.db_path)
            self._schema_manager = SQLiteSchemaManager(self.conn)
            self._operations = SQLiteOperations(self.conn)

            run_all_ensure(self.conn, self._schema_manager, self.db_path)

            self._retry_policy = RetryPolicy.from_driver_config(config)

            # Optional query journal for inspection and recovery (rotation at 100 MB by default)
            query_log_path = config.get("query_log_path")
            if query_log_path:
                from ..sqlite_query_journal import (
                    DEFAULT_JOURNAL_BACKUP_COUNT,
                    DEFAULT_JOURNAL_MAX_BYTES,
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
                logger.info(
                    "Query journal enabled: %s (max_bytes=%s)",
                    self._query_journal.path,
                    max_bytes,
                )
        except Exception as e:
            raise DriverConnectionError(f"Failed to connect to database: {e}") from e

    def commit(self) -> None:
        """Commit the main connection (used with transaction_id=LOCAL in CodeDatabase)."""
        if self.conn:
            self.conn.commit()

    def rollback(self) -> None:
        """Rollback the main connection."""
        if self.conn:
            self.conn.rollback()

    def _sleep_before_retry(self, attempt_1based: int) -> None:
        time.sleep(self._retry_policy.delay_for_attempt(attempt_1based))

    def _run_self_managed_with_retry(
        self, operation_name: str, func: Callable[[], _T]
    ) -> _T:
        max_a = self._retry_policy.attempts
        for attempt in range(1, max_a + 1):
            try:
                return func()
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
                    "[DB_RETRY] backend=sqlite layer=driver operation=%s "
                    "attempt=%s/%s sqlstate=%s error_kind=%s",
                    operation_name,
                    attempt + 1,
                    max_a,
                    e.sqlstate,
                    e.error_kind,
                )
                self._sleep_before_retry(attempt)
        raise RuntimeError("SQLite driver: retry loop exited without result")

    def disconnect(self) -> None:
        """Close SQLite connection.

        Raises:
            DriverConnectionError: If disconnection fails
        """
        try:
            if self._query_journal:
                try:
                    self._query_journal.close()
                except Exception:
                    pass
                self._query_journal = None
            # Close all transactions
            if self._transaction_manager:
                self._transaction_manager.close_all()

            if self.conn:
                self.conn.close()
                self.conn = None
        except Exception as e:
            raise DriverConnectionError(f"Failed to disconnect: {e}") from e

    def create_table(self, schema: Dict[str, Any]) -> bool:
        """Create database table from schema (name, columns, constraints)."""
        if not self.conn:
            raise DriverOperationError("Database connection not established")
        try:
            return run_create_table(self.conn, schema)
        except DriverOperationError:
            raise
        except Exception as e:
            raise DriverOperationError(f"Failed to create table: {e}") from e

    def drop_table(self, table_name: str) -> bool:
        """Drop database table."""
        if not self.conn:
            raise DriverOperationError("Database connection not established")
        try:
            return run_drop_table(self.conn, table_name)
        except Exception as e:
            raise DriverOperationError(f"Failed to drop table: {e}") from e

    def insert(self, table_name: str, data: Dict[str, Any]) -> int:
        """Insert row into table."""
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        return self._operations.insert(table_name, data)

    def update(
        self, table_name: str, where: Dict[str, Any], data: Dict[str, Any]
    ) -> int:
        """Update rows in table."""
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        return self._operations.update(table_name, where, data)

    def delete(self, table_name: str, where: Dict[str, Any]) -> int:
        """Delete rows from table."""
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        return self._operations.delete(table_name, where)

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Select rows from table."""
        if not self._operations:
            raise DriverOperationError("Operations manager not initialized")
        return self._operations.select(
            table_name, where, columns, limit, offset, order_by
        )

    def execute_batch(
        self,
        operations: List[Tuple[str, Optional[tuple]]],
        transaction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute multiple SQL statements with batch recognition and executemany."""
        if not operations:
            return []
        if transaction_id and transaction_id != "local":
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
            )
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        use_retry = _execute_batch_implies_write(operations)
        if not use_retry:
            return run_execute_batch(
                self.conn,
                operations,
                transaction_id,
                self._query_journal,
            )

        def do_run() -> List[Dict[str, Any]]:
            self._qa_maybe_inject_transient()
            return run_execute_batch(
                self.conn,
                operations,
                transaction_id,
                self._query_journal,
            )

        return self._run_self_managed_with_retry("execute_batch", do_run)

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute SQL: one or more statements in one text; return only last result."""
        if transaction_id and transaction_id != "local":
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
            )
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        use_retry = _sql_implies_write(sql)
        if not use_retry:
            return run_execute(
                self.conn,
                sql,
                params,
                transaction_id,
                self._query_journal,
            )

        def do_run() -> Dict[str, Any]:
            self._qa_maybe_inject_transient()
            return run_execute(
                self.conn,
                sql,
                params,
                transaction_id,
                self._query_journal,
            )

        return self._run_self_managed_with_retry("execute", do_run)

    def begin_transaction(self) -> str:
        """Begin database transaction.

        Returns:
            Transaction ID (string)

        Raises:
            TransactionError: If transaction cannot be started
        """
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.begin_transaction()

    def commit_transaction(self, transaction_id: str) -> bool:
        """Commit database transaction.

        Args:
            transaction_id: Transaction ID returned by begin_transaction()

        Returns:
            True if transaction was committed successfully, False otherwise

        Raises:
            TransactionError: If transaction cannot be committed
        """
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.commit_transaction(transaction_id)

    def rollback_transaction(self, transaction_id: str) -> bool:
        """Rollback database transaction.

        Args:
            transaction_id: Transaction ID returned by begin_transaction()

        Returns:
            True if transaction was rolled back successfully, False otherwise

        Raises:
            TransactionError: If transaction cannot be rolled back
        """
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.rollback_transaction(transaction_id)

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get information about table columns.

        Args:
            table_name: Name of the table

        Returns:
            List of dictionaries with column information (name, type, nullable, etc.)

        Raises:
            DriverOperationError: If operation fails
        """
        if not self._schema_manager:
            raise DriverOperationError("Schema manager not initialized")
        return self._schema_manager.get_table_info(table_name)

    def sync_schema(
        self, schema_definition: Dict[str, Any], backup_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """Synchronize database schema.

        Args:
            schema_definition: Complete schema definition (tables, columns, constraints)
            backup_dir: Optional directory for backups before schema changes

        Returns:
            Dictionary with sync results (created_tables, modified_tables, etc.)

        Raises:
            DriverOperationError: If operation fails
        """
        if not self._schema_manager:
            raise DriverOperationError("Schema manager not initialized")
        return self._schema_manager.sync_schema(
            schema_definition, backup_dir, self.create_table
        )
