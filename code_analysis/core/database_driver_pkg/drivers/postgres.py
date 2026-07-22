"""
PostgreSQL driver for database driver process (psycopg3).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, cast

from code_analysis.core.database.logical_write_program import LogicalWriteProgramV1
from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.qa_mcp_hooks_policy import qa_mcp_hooks_enabled_for_driver_rpc
from code_analysis.core.retry_policy import RetryPolicy

from ..exceptions import (
    DriverConnectionError,
    DriverOperationError,
    TransientDatabaseError,
)
from .base import BaseDatabaseDriver, DbIdentity
from .postgres_connection_pool import PostgreSQLConnectionPool
from .postgres_execute_lane import (
    postgres_batch_requires_write_pool,
    postgres_execute_requires_write_pool,
)
from .postgres_migrations import ensure_postgres_schema
from .postgres_operations import PostgreSQLOperations
from .postgres_run import run_execute, run_execute_batch
from .postgres_schema import PostgreSQLSchemaManager
from .postgres_tables import run_create_table_postgres, run_drop_table_postgres
from .postgres_transactions import PostgreSQLTransactionManager

logger = logging.getLogger(__name__)

_LOCK_SCOPE_VALUES = frozenset({"none", "project_write", "project_read"})

_T = TypeVar("_T")


def _is_self_managed_transaction(transaction_id: Optional[str]) -> bool:
    """True when transaction_id is missing, empty, or exactly 'local' (not external)."""
    if transaction_id is None or transaction_id == "":
        return True
    return transaction_id == "local"


def _transient_with_attempts(
    exc: TransientDatabaseError, attempts: int
) -> TransientDatabaseError:
    """Rebuild ``exc`` with ``.attempts`` set to the current loop's ``attempt_1based``.

    The old RPC-handler retry loop always passed the *current attempt count* into
    ``ErrorResult.details`` explicitly (``e.to_details(operation_name, attempts=attempt_1based)``)
    rather than relying on whatever ``.attempts`` the raiser happened to set (usually
    unset -> ``None``). This preserves that behavior now that the loop lives on the
    driver and callers translate ``e.to_details(operation_name)`` without an explicit
    override.
    """
    return TransientDatabaseError(
        exc.args[0] if exc.args else str(exc),
        sqlstate=exc.sqlstate,
        error_kind=exc.error_kind,
        retryable=exc.retryable,
        original_error=exc.original_error,
        attempts=attempts,
        commit_outcome_unknown=exc.commit_outcome_unknown,
    )


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
    """Return connect kwargs from config."""
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
        """Initialize the instance."""
        # Stage 2 (layer collapse): widespread getattr(x, "_driver_type") call sites
        # must keep evaluating to "postgres" once callers get handed this driver
        # directly instead of a DatabaseClient wrapping it (which already sets this).
        self._driver_type: str = "postgres"
        self.conn: Any = None
        self._pool: Optional[PostgreSQLConnectionPool] = None
        self._connect_kwargs: Dict[str, Any] = {}
        self._full_schema: Dict[str, Any] = {}
        self._schema_tables: Dict[str, Any] = {}
        self._transaction_manager: Optional[PostgreSQLTransactionManager] = None
        self._schema_manager: Optional[PostgreSQLSchemaManager] = None
        self._operations: Optional[PostgreSQLOperations] = None
        self._query_journal: Any = None
        self._retry_policy: RetryPolicy = RetryPolicy()
        self._qa_transient_injections_remaining: int = 0
        self._pool_max_wait_seconds: float = 30.0
        self._pool_write_size: int = 3
        self._pool_read_size: int = 2
        self._schema_vector_dim: int = 384
        # Transaction reaper (safety net for orphaned explicit transactions).
        self._transaction_max_age_seconds: float = 300.0
        self._transaction_reaper_interval_seconds: float = 30.0
        self._reaper_stop: Optional[threading.Event] = None
        self._reaper_thread: Optional[threading.Thread] = None

    def qa_set_db_retry_injections(self, remaining: int) -> Dict[str, Any]:
        """QA only: next N self-managed execute/execute_batch attempts raise a synthetic deadlock.

        Gated on ``CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS`` at the driver level (moved down
        from the RPC handler, which still pre-checks the same gate for RPC callers —
        the two checks are idempotent; the handler's check simply becomes redundant
        once this method is also reachable directly).
        """
        if not qa_mcp_hooks_enabled_for_driver_rpc():
            raise DriverOperationError(
                "qa_set_db_retry_injections is disabled; set "
                "CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1 on the database driver process"
            )
        n = int(remaining)
        if n < 0 or n > 20:
            raise DriverOperationError("remaining must be between 0 and 20")
        self._qa_transient_injections_remaining = n
        return {"success": True, "remaining": self._qa_transient_injections_remaining}

    def _qa_maybe_inject_transient(self) -> None:
        """Return qa maybe inject transient."""
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

    def _teardown_stale_state_if_any(self) -> None:
        """Close any pre-existing connection/pool/manager/reaper before reconnect.

        ``connect()`` must be idempotent: calling it a second time on the same
        driver instance would otherwise overwrite ``self.conn`` (1 backend
        connection), ``self._pool`` (5), ``self._transaction_manager``, and the
        reaper thread *by reference*, orphaning the old objects — their backend
        connections stay open forever because nothing can reach them to close
        them. Route teardown through the existing ``disconnect()`` (pool +
        ``close_all()`` + main conn + reaper). A failure to close stale state is
        logged and swallowed so the fresh connect can still proceed.
        """
        already_initialized = (
            self.conn is not None
            or self._pool is not None
            or self._transaction_manager is not None
            or (self._reaper_thread is not None and self._reaper_thread.is_alive())
        )
        if not already_initialized:
            return
        logger.warning(
            "PostgreSQLDriver.connect() called on an already-initialized driver; "
            "tearing down stale connection/pool/reaper to avoid orphaning them"
        )
        try:
            self.disconnect()
        except Exception as e:
            logger.warning(
                "PostgreSQLDriver: failed to tear down stale state before "
                "reconnect: %s",
                e,
            )

    def connect(self, config: Dict[str, Any]) -> None:
        """Return connect."""
        try:
            import psycopg
        except ImportError as e:
            raise DriverConnectionError(
                "PostgreSQL driver requires psycopg (pip install 'psycopg[binary]>=3.1' or pip install -e .)"
            ) from e

        try:
            # Idempotency guard (Defect A): never leave two main connections /
            # two pools / two reapers behind when connect() runs twice.
            self._teardown_stale_state_if_any()
            self._connect_kwargs = _connect_kwargs_from_config(config)
            self._schema_vector_dim = int(config.get("vector_dim", 384))
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

            ensure_postgres_schema(
                self.conn, self._full_schema, vector_dim=self._schema_vector_dim
            )

            self._retry_policy = RetryPolicy.from_driver_config(config)
            # Canonical database driver config keys only (Step 03).
            lock_timeout_seconds = config.get("lock_timeout_seconds")
            statement_timeout_seconds = config.get("statement_timeout_seconds")
            self._transaction_manager = PostgreSQLTransactionManager(
                self._connect_kwargs,
                lock_timeout_seconds=lock_timeout_seconds,
                statement_timeout_seconds=statement_timeout_seconds,
            )
            self._schema_manager = PostgreSQLSchemaManager(
                self.conn, schema_vector_dim=self._schema_vector_dim
            )
            self._operations = PostgreSQLOperations(self.conn, self._schema_tables)

            # Connection topology (phase 1): one **main** ``self.conn`` for schema manager,
            # ``PostgreSQLOperations``, and ``commit``/``rollback`` on the default session;
            # a configurable number of pool connections (write_pool_size + read_pool_size,
            # defaults 3 write + 2 read) for self-managed ``execute`` / ``execute_batch``
            # only; ``begin_transaction`` / explicit ``transaction_id`` uses additional
            # connections from ``PostgreSQLTransactionManager`` (not the pool).
            self._pool_max_wait_seconds = float(
                config.get("pool_max_wait_seconds", 30.0)
            )
            self._pool_write_size = int(config.get("pool_write_size", 3))
            self._pool_read_size = int(config.get("pool_read_size", 2))
            query_log_path = config.get("query_log_path")
            if query_log_path:
                from ..query_journal import (
                    DEFAULT_JOURNAL_BACKUP_COUNT,
                    DEFAULT_JOURNAL_MAX_BYTES,
                    QueryJournal,
                )

                max_bytes = config.get("query_log_max_bytes", DEFAULT_JOURNAL_MAX_BYTES)
                backup_count = config.get(
                    "query_log_backup_count", DEFAULT_JOURNAL_BACKUP_COUNT
                )
                self._query_journal = QueryJournal(
                    Path(query_log_path),
                    max_bytes=max_bytes,
                    backup_count=backup_count,
                )
                logger.info("Query journal enabled: %s", query_log_path)
            self._pool = PostgreSQLConnectionPool(
                self._connect_kwargs,
                max_wait_seconds=self._pool_max_wait_seconds,
                write_pool_size=self._pool_write_size,
                read_pool_size=self._pool_read_size,
            )
            self._transaction_max_age_seconds = float(
                config.get("transaction_max_age_seconds", 300.0)
            )
            self._transaction_reaper_interval_seconds = float(
                config.get("transaction_reaper_interval_seconds", 30.0)
            )
            self._start_transaction_reaper()
        except DriverConnectionError:
            raise
        except Exception as e:
            raise DriverConnectionError(f"Failed to connect to PostgreSQL: {e}") from e

    def _start_transaction_reaper(self) -> None:
        """Start the background reaper unless the interval is disabled (0).

        The reaper force-closes explicit transactions older than
        ``transaction_max_age_seconds`` so a caller that fails to reach
        commit/rollback cannot orphan a backend connection indefinitely.
        """
        # Self-protect against a leaked second reaper: this is reachable directly
        # (not only via connect()), so stop any live reaper before starting a new
        # one. Guarantees at most one ``pg-transaction-reaper`` thread per driver.
        if self._reaper_thread is not None and self._reaper_thread.is_alive():
            self._stop_transaction_reaper()
        interval = self._transaction_reaper_interval_seconds
        if interval <= 0:
            logger.info(
                "PostgreSQL transaction reaper disabled (interval=%s)", interval
            )
            return
        self._reaper_stop = threading.Event()
        self._reaper_thread = threading.Thread(
            target=self._transaction_reaper_loop,
            name="pg-transaction-reaper",
            daemon=True,
        )
        self._reaper_thread.start()
        logger.info(
            "PostgreSQL transaction reaper started (interval=%ss max_age=%ss)",
            interval,
            self._transaction_max_age_seconds,
        )

    def _transaction_reaper_loop(self) -> None:
        """Periodically reap orphaned explicit transactions until stopped."""
        stop = self._reaper_stop
        if stop is None:
            return
        interval = self._transaction_reaper_interval_seconds
        max_age = self._transaction_max_age_seconds
        while not stop.wait(interval):
            manager = self._transaction_manager
            if manager is None:
                continue
            try:
                reaped = manager.reap_expired(max_age)
            except Exception as e:
                logger.warning("PostgreSQL transaction reaper sweep failed: %s", e)
                continue
            if reaped >= 1:
                logger.info(
                    "PostgreSQL transaction reaper closed %s orphaned "
                    "transaction(s) older than %ss",
                    reaped,
                    max_age,
                )

    def _stop_transaction_reaper(self) -> None:
        """Signal the reaper thread to stop and wait briefly for it to exit."""
        if self._reaper_stop is not None:
            self._reaper_stop.set()
        thread = self._reaper_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        self._reaper_thread = None
        self._reaper_stop = None

    def commit(self) -> None:
        """Commit the main connection (legacy SQL facade transaction_id=local)."""
        if self.conn:
            self.conn.commit()

    def rollback(self) -> None:
        """Rollback the main connection."""
        if self.conn:
            self.conn.rollback()

    def _reconnect_main(self) -> None:
        """Rebuild main connection and dependent managers (after dropped connection).

        Safe default: tear down and recreate the **entire** execute pool when the main
        session is lost, so no thread keeps a stale pool connection. Waiters in
        ``acquire()`` wake with ``DriverConnectionError`` if the pool was closed under them.
        """
        import psycopg

        logger.warning("PostgreSQLDriver: reconnecting main session")
        if self._pool:
            self._pool.close_all()
            self._pool = None
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
        self.conn = psycopg.connect(**self._connect_kwargs)
        self.conn.autocommit = False
        ensure_postgres_schema(
            self.conn, self._full_schema, vector_dim=self._schema_vector_dim
        )
        self._schema_manager = PostgreSQLSchemaManager(
            self.conn, schema_vector_dim=self._schema_vector_dim
        )
        self._operations = PostgreSQLOperations(self.conn, self._schema_tables)
        self._pool = PostgreSQLConnectionPool(
            self._connect_kwargs,
            max_wait_seconds=self._pool_max_wait_seconds,
            write_pool_size=self._pool_write_size,
            read_pool_size=self._pool_read_size,
        )

    def _sleep_before_retry(self, attempt_1based: int) -> None:
        """Return sleep before retry."""
        time.sleep(self._retry_policy.delay_for_attempt(attempt_1based))

    def _run_once_with_reconnect_on_lost(self, func: Callable[[], _T]) -> _T:
        """Return run once with reconnect on lost."""
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
        """Return run self managed with retry."""
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
                self._rollback_self_managed_before_retry()
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

    def _rollback_self_managed_before_retry(self) -> None:
        """Rollback before retrying self-managed execute after a transient error.

        When ``_pool`` is active, rollback of the **leased** connection is handled inside
        ``PostgreSQLConnectionPool.acquire``; this path only rolls back ``self.conn`` when
        the retry path still used the main session without a pool lease.
        """
        if self._pool is not None:
            return
        if self.conn:
            try:
                self.conn.rollback()
            except Exception as rb:
                raise DriverOperationError(
                    f"Rollback before database retry failed: {rb}"
                ) from rb

    def pool_status(self) -> Dict[str, Any]:
        """Snapshot of execute pool lanes for observability (step 6 consumers)."""
        if self._pool is None:
            return {"enabled": False}
        status = {"enabled": True}
        status.update(self._pool.snapshot())
        return status

    def disconnect(self) -> None:
        """Return disconnect."""
        try:
            self._stop_transaction_reaper()
            if self._query_journal:
                try:
                    self._query_journal.close()
                except Exception:
                    pass
                self._query_journal = None
            if self._transaction_manager:
                self._transaction_manager.close_all()
                self._transaction_manager = None
            if self._pool:
                self._pool.close_all()
                self._pool = None
            if self.conn:
                self.conn.close()
                self.conn = None
        except Exception as e:
            raise DriverConnectionError(f"Failed to disconnect: {e}") from e

    def create_table(self, schema: Dict[str, Any]) -> bool:
        """Return create table."""
        if not self.conn:
            raise DriverOperationError("Database connection not established")
        return run_create_table_postgres(self.conn, schema)

    def drop_table(self, table_name: str) -> bool:
        """Return drop table."""
        if not self.conn:
            raise DriverOperationError("Database connection not established")
        return run_drop_table_postgres(self.conn, table_name)

    def insert(self, table_name: str, data: Dict[str, Any]) -> Optional[DbIdentity]:
        """Return insert."""
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
        """Return update."""
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
        """Return delete."""
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
        """Return select."""
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
        """Run batched SQL.

        External ``transaction_id`` (from ``begin_transaction``): uses only the
        connection in ``_transaction_manager._transactions``; the 3-write/2-read pool
        is not used.

        Self-managed (``None``, ``\"\"``, or ``\"local\"``): leases from the pool;
        when all write slots are busy, acquire blocks until one frees (reads use
        their own two slots).
        """
        if not operations:
            return []
        if not _is_self_managed_transaction(transaction_id):
            # Non-self-managed => transaction_id is a real external id (the
            # helper treats None/""/"local" as self-managed), so it is a str.
            assert transaction_id is not None
            if not self._transaction_manager:
                raise DriverOperationError("Transaction manager not initialized")
            conn = self._transaction_manager.get_connection(transaction_id)
            if conn is None:
                raise DriverOperationError(f"Transaction {transaction_id} not found")
            return run_execute_batch(
                conn,
                operations,
                transaction_id,
                self._query_journal,
                self._schema_tables,
            )
        if not self.conn:
            raise DriverOperationError("Database connection not established")
        if not self._pool:
            raise DriverOperationError("Database connection pool not initialized")
        need_write = postgres_batch_requires_write_pool(operations)
        pool = self._pool

        def do_run() -> List[Dict[str, Any]]:
            """Return do run."""
            self._qa_maybe_inject_transient()
            with pool.acquire(write=need_write) as pc:
                return run_execute_batch(
                    pc,
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
        """Execute one statement.

        Same routing as ``execute_batch``: explicit RPC transaction id → dedicated
        ``_transactions`` connection only; self-managed → pool (writes may wait when
        all three write connections are busy).
        """
        if not _is_self_managed_transaction(transaction_id):
            # Non-self-managed => transaction_id is a real external id (the
            # helper treats None/""/"local" as self-managed), so it is a str.
            assert transaction_id is not None
            if not self._transaction_manager:
                raise DriverOperationError("Transaction manager not initialized")
            conn = self._transaction_manager.get_connection(transaction_id)
            if conn is None:
                raise DriverOperationError(f"Transaction {transaction_id} not found")
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
        if not self._pool:
            raise DriverOperationError("Database connection pool not initialized")
        need_write = postgres_execute_requires_write_pool(sql)
        pool = self._pool

        def do_run() -> Dict[str, Any]:
            """Return do run."""
            self._qa_maybe_inject_transient()
            with pool.acquire(write=need_write) as pc:
                return run_execute(
                    pc,
                    sql,
                    params,
                    transaction_id,
                    self._query_journal,
                    self._schema_tables,
                )

        return self._run_self_managed_with_retry("execute", do_run)

    def begin_transaction(self) -> str:
        """Return begin transaction."""
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.begin_transaction()

    def commit_transaction(self, transaction_id: str) -> bool:
        """Return commit transaction."""
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.commit_transaction(transaction_id)

    def rollback_transaction(self, transaction_id: str) -> bool:
        """Return rollback transaction."""
        if not self._transaction_manager:
            raise DriverOperationError("Transaction manager not initialized")
        return self._transaction_manager.rollback_transaction(transaction_id)

    def execute_logical_write_operation(
        self, program: LogicalWriteProgramV1
    ) -> Dict[str, Any]:
        """Run multiple execute_batch steps in one transaction, with full-tx retry.

        Formerly delegated-to by the RPC ``execute_logical_write_operation`` handler
        (``rpc_handlers_schema.handle_execute_logical_write_operation``, deleted along
        with the rest of the RPC/client stack, stage 2 layer collapse); this is now
        the sole implementation, called directly. Sources retry policy from
        ``self._retry_policy`` (set in ``connect()``), not the RPC-only
        ``_write_retry_policy`` / ``_driver_config`` lookup the old handler used to read.

        Returns the unwrapped success payload (``batch_results`` / ``transaction_id``
        / ``metadata``). Raises on failure instead of building an RPC Result envelope,
        matching every other driver method's convention (``begin_transaction``,
        ``execute_batch``, ...): ``TransientDatabaseError`` propagates (re-raised as-is
        when not retried; rebuilt with the final ``attempts`` count when retries are
        exhausted, mirroring ``_run_self_managed_with_retry``); a rollback failure
        after a transient error raises ``DriverOperationError`` chained from the
        rollback exception (same convention as ``_rollback_self_managed_before_retry``);
        any other exception propagates unchanged after a best-effort rollback attempt.

        Validates ``operation_name`` / ``project_id`` / ``lock_scope`` types up front,
        raising ``ValueError`` with the same messages the deleted RPC boundary used
        (``rpc_handlers_schema.handle_execute_logical_write_operation``), so a caller
        with a malformed program fails loud before any transaction is opened.
        """
        batches = program.get("batches")
        if not batches:
            raise ValueError("LogicalWriteProgramV1 requires non-empty batches")
        operation_name = program.get("operation_name")
        if operation_name is not None and not isinstance(operation_name, str):
            raise ValueError("operation_name must be a string or null")
        project_id = program.get("project_id")
        if project_id is not None and not isinstance(project_id, str):
            raise ValueError("project_id must be a string or null")
        lock_scope = program.get("lock_scope", "none")
        if not isinstance(lock_scope, str) or lock_scope not in _LOCK_SCOPE_VALUES:
            raise ValueError(
                "lock_scope must be one of: none, project_write, project_read"
            )
        defer_constraints = program.get("defer_constraints", False)

        policy = self._retry_policy
        max_attempts = max(1, policy.attempts)
        logger.info(
            "method=execute_logical_write_operation n_batches=%s lock_scope=%s",
            len(batches),
            lock_scope,
        )

        for attempt_1based in range(1, max_attempts + 1):
            transaction_id: Optional[str] = None
            try:
                transaction_id = self.begin_transaction()
                tid_short = (
                    (transaction_id[:8] + "…")
                    if transaction_id and len(transaction_id) > 8
                    else transaction_id
                )
                logger.debug(
                    "[CHAIN] driver execute_logical_write_operation tid=%s",
                    tid_short,
                )
                if defer_constraints:
                    self.execute("SET CONSTRAINTS ALL DEFERRED", None, transaction_id)
                batch_results: list[dict[str, Any]] = []
                for batch_ops in batches:
                    ops = cast(
                        List[Tuple[str, Optional[tuple]]], list(batch_ops)
                    )
                    results = self.execute_batch(ops, transaction_id)
                    batch_results.append({"results": results})
                self.commit_transaction(transaction_id)
                return {
                    "batch_results": batch_results,
                    "transaction_id": transaction_id,
                    "metadata": {
                        "operation_name": operation_name,
                        "project_id": project_id,
                        "lock_scope": lock_scope,
                    },
                }
            except TransientDatabaseError as e:
                if transaction_id is not None:
                    try:
                        self.rollback_transaction(transaction_id)
                    except Exception as rb_err:
                        logger.error(
                            "rollback after logical write failure: %s",
                            rb_err,
                            exc_info=True,
                        )
                        rollback_err = DriverOperationError(
                            f"rollback failed: {rb_err}"
                        )
                        # Old handler's ErrorResult.details always carried the
                        # current attempt count here; DriverOperationError has no
                        # such field, so attach it dynamically for the handler to
                        # read back (see handle_execute_logical_write_operation).
                        setattr(rollback_err, "attempts", attempt_1based)
                        raise rollback_err from rb_err
                if e.commit_outcome_unknown:
                    raise _transient_with_attempts(e, attempt_1based) from e
                if not (e.retryable and not e.commit_outcome_unknown):
                    raise _transient_with_attempts(e, attempt_1based) from e
                if attempt_1based >= max_attempts:
                    raise _transient_with_attempts(e, max_attempts) from e
                logger.info(
                    "[DB_RETRY] backend=postgres layer=driver "
                    "operation=execute_logical_write_operation "
                    "operation_name=%s attempt=%s/%s sqlstate=%s error_kind=%s",
                    operation_name if operation_name is not None else "none",
                    attempt_1based,
                    max_attempts,
                    e.sqlstate,
                    e.error_kind,
                )
                time.sleep(policy.delay_for_attempt(attempt_1based))
            except Exception as e:
                if transaction_id is not None:
                    try:
                        self.rollback_transaction(transaction_id)
                    except Exception as rb_err:
                        logger.error(
                            "rollback after logical write failure: %s",
                            rb_err,
                            exc_info=True,
                        )
                logger.error(
                    "Error in execute_logical_write_operation: %s", e, exc_info=True
                )
                raise
        raise RuntimeError(
            "PostgreSQL driver: logical write retry loop exited without result"
        )

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Return get table info."""
        if not self._schema_manager:
            raise DriverOperationError("Schema manager not initialized")
        return self._schema_manager.get_table_info(table_name)

    def sync_schema(
        self, schema_definition: Dict[str, Any], backup_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return sync schema."""
        if not self._schema_manager:
            raise DriverOperationError("Schema manager not initialized")
        return self._schema_manager.sync_schema(
            schema_definition, backup_dir, self.create_table
        )
