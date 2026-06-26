"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import re
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base_chunks import (
    get_all_chunks_for_faiss_rebuild as _get_all_chunks_for_faiss_rebuild,
    get_non_vectorized_chunks as _get_non_vectorized_chunks,
    update_chunk_vector_id as _update_chunk_vector_id,
)
from .schema_creation import (
    run_create_schema,
    run_migrate_schema,
    run_migrate_to_uuid_projects,
)
from .schema_definition import (
    MIGRATION_METHODS,
    SCHEMA_VERSION,
    get_schema_definition,
)

from .code_chunk_sql import build_code_chunk_upsert_batch

logger = logging.getLogger(__name__)

# Passed to database_driver_pkg execute/execute_batch so run_* skips per-statement commit
# (same idea as SQLite named transactions); CodeDatabase then calls driver.commit().
LOCAL_DRIVER_TRANSACTION_ID = "local"


def create_driver_config_for_worker(
    db_path: Path, driver_type: str = "sqlite_proxy", backup_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Create driver configuration for worker processes.

    Args:
        db_path: Path to database file
        driver_type: Driver type (default: "sqlite_proxy")
        backup_dir: Optional backup directory path (if None, will be inferred from db_path in sync_schema)

    Returns:
        Driver configuration dict with 'type' and 'config' keys
    """
    resolved_path = Path(db_path).resolve()

    config_dict: Dict[str, Any] = {
        "path": str(resolved_path),
    }

    # Add backup_dir if provided
    if backup_dir:
        config_dict["backup_dir"] = str(Path(backup_dir).resolve())

    if driver_type == "sqlite_proxy":
        config_dict["worker_config"] = {
            # Default worker config - can be overridden by caller
            "command_timeout": 30.0,
            "poll_interval": 0.01,  # Polling interval in seconds (10ms; reduced for IPC latency)
        }
        return {
            "type": "sqlite_proxy",
            "config": config_dict,
        }
    else:
        # For other driver types (mysql, postgres, etc.), use provided type
        # Config structure depends on driver type
        return {
            "type": driver_type,
            "config": config_dict,
        }


# One lock per database (by driver instance or path)
# This allows concurrent access to different databases while serializing access to the same database
_db_locks: Dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()  # Protects _db_locks dictionary


def _get_db_lock(lock_key: str) -> threading.Lock:
    """Get or create a lock for a specific database."""
    with _locks_lock:
        if lock_key not in _db_locks:
            _db_locks[lock_key] = threading.Lock()
        return _db_locks[lock_key]


class CodeDatabase:
    """Database for code analysis data using pluggable drivers."""

    def __init__(self, driver_config: Dict[str, Any]) -> None:
        """
        Initialize database connection and create schema.

        Args:
            driver_config: Driver configuration dict with 'type' and 'config' keys.
                          Required. No backward compatibility - must specify driver.

        Raises:
            ValueError: If driver_config is missing or invalid.
        """
        logger.info(
            f"[CodeDatabase] __init__ called with driver_config type={driver_config.get('type') if driver_config else None}"
        )
        if not driver_config:
            raise ValueError("driver_config is required. No backward compatibility.")

        driver_type = driver_config.get("type")
        if not driver_type:
            raise ValueError("driver_config must contain 'type' key")

        driver_cfg = driver_config.get("config", {})
        logger.info(
            f"[CodeDatabase] Creating driver: type={driver_type}, config_keys={list(driver_cfg.keys())}"
        )
        print(
            f"[CodeDatabase] Creating driver: type={driver_type}, config_keys={list(driver_cfg.keys())}",
            flush=True,
        )

        try:
            from ..database_driver_pkg.driver_factory import (
                create_driver as _create_database_driver,
            )

            logger.info(f"[CodeDatabase] Calling create_driver({driver_type}, ...)")
            print(
                f"[CodeDatabase] Calling create_driver({driver_type}, ...)", flush=True
            )
            self.driver = _create_database_driver(
                driver_type, driver_cfg, connect=False
            )
            logger.info(
                f"[CodeDatabase] Database driver '{driver_type}' loaded successfully"
            )
            print(
                f"[CodeDatabase] Database driver '{driver_type}' loaded successfully",
                flush=True,
            )
        except Exception as e:
            logger.error(
                f"[CodeDatabase] Failed to load database driver '{driver_type}': {e}",
                exc_info=True,
            )
            raise

        # Store driver type for logging
        self._driver_type = driver_type

        # Use lock only if driver is not thread-safe
        # Universal drivers (database_driver_pkg) omit is_thread_safe; treat as False.
        if not getattr(self.driver, "is_thread_safe", False):
            # Use driver instance as lock key (each instance gets its own lock)
            lock_key = f"{driver_type}:{id(self.driver)}"
            self._lock = _get_db_lock(lock_key)
        else:
            self._lock = None

        # Transaction state tracking
        self._transaction_active: bool = False

        # Store driver_config for sync_schema()
        self.driver_config = driver_config

        # DO NOT call _create_schema() here
        # Schema creation happens via sync_schema() in driver

        # Connect driver then sync schema so DB is ready to use
        try:
            logger.info(f"[CodeDatabase] Connecting driver: type={driver_type}")
            self.driver.connect(driver_cfg)
            logger.info("[CodeDatabase] Driver connected successfully")
        except Exception as e:
            logger.error(
                f"[CodeDatabase] Failed to connect driver '{driver_type}': {e}",
                exc_info=True,
            )
            raise
        try:
            self._do_sync_schema()
        except Exception as e:
            logger.error(
                f"[CodeDatabase] Schema sync failed after connect: {e}",
                exc_info=True,
            )
            raise

    @classmethod
    def from_existing_driver(
        cls,
        driver: Any,
        driver_config: Optional[Dict[str, Any]] = None,
    ) -> "CodeDatabase":
        """
        Build CodeDatabase that reuses an already-connected driver (no connect, no sync_schema).

        Use in the database driver process when handling index_file RPC: the process
        already has a single driver connection; creating a second CodeDatabase(driver_config)
        would open a second connection and call sync_schema(), causing lock contention
        (e.g. "Schema synchronization failed: disk I/O error"). This factory avoids
        that by reusing the existing driver.

        Args:
            driver: Already-connected driver instance (e.g. from RPCServer).
            driver_config: Optional config for backup_dir inference. If None, built from
                           driver.db_path when present.

        Returns:
            CodeDatabase instance using the given driver. Do not call sync_schema on it.
        """
        from code_analysis.core.database_driver_pkg.drivers.postgres import (
            PostgreSQLDriver,
        )
        from code_analysis.core.database_driver_pkg.drivers.sqlite import (
            SQLiteDriver as RpcSQLiteDriver,
        )

        db_path = getattr(driver, "db_path", None)
        if driver_config is None:
            if isinstance(driver, PostgreSQLDriver):
                driver_config = {"type": "postgres", "config": {}}
            elif db_path is not None:
                driver_config = {
                    "type": "sqlite",
                    "config": {"path": str(Path(db_path).resolve())},
                }
            else:
                driver_config = {"type": "sqlite", "config": {}}

        if isinstance(driver, PostgreSQLDriver):
            resolved_driver_type = "postgres"
        elif isinstance(driver, RpcSQLiteDriver) or db_path is not None:
            resolved_driver_type = "sqlite"
        else:
            resolved_driver_type = str(driver_config.get("type") or "sqlite")

        logger.debug(
            "CodeDatabase.from_existing_driver: reusing driver (no connect, no sync_schema)"
        )
        obj = object.__new__(cls)
        obj.driver = driver
        obj._driver_type = resolved_driver_type
        obj._lock = None
        obj._transaction_active = False
        obj.driver_config = driver_config
        return obj

    def _do_sync_schema(self) -> Dict[str, Any]:
        """
        Synchronize database schema via driver (implementation).

        Used by sync_schema() and by __getattr__ when sync_schema is requested
        before the full class is visible (e.g. in some test import orders).
        """
        schema_definition = self._get_schema_definition()
        backup_dir = self.driver_config.get("config", {}).get("backup_dir")
        if not backup_dir:
            db_path = self.driver_config.get("config", {}).get("path")
            if db_path:
                db_path_obj = Path(db_path)
                if db_path_obj.parent.name == "data":
                    backup_dir = str(db_path_obj.parent.parent / "backups")
                else:
                    backup_dir = str(db_path_obj.parent / "backups")
            else:
                raise RuntimeError("Cannot determine backup_dir for schema sync")
        return self.driver.sync_schema(schema_definition, Path(backup_dir))

    def __getattr__(self, name: str) -> Any:
        """
        Dynamic method support for mypy/static analysis.

        The `code_analysis.core.database` package attaches many module-level functions
        to this class at import time (facade pattern). Declaring `__getattr__`
        prevents `attr-defined` errors for those dynamically-injected methods.
        Fallback: if sync_schema is requested (e.g. before class is fully bound),
        return _do_sync_schema so __init__ can complete.
        """
        if name == "sync_schema":
            return getattr(self, "_do_sync_schema")
        raise AttributeError(name)

    def _driver_transaction_id(self) -> Optional[str]:
        """transaction_id for RPC drivers: set while CodeDatabase transaction is active.

        sqlite_proxy keeps transaction id on the driver; other drivers use
        :data:`LOCAL_DRIVER_TRANSACTION_ID` so sqlite_run/postgres_run skip commit
        until :meth:`driver.commit`.
        """
        if not getattr(self, "_transaction_active", False):
            return None
        if self._driver_type == "sqlite_proxy":
            return None
        return LOCAL_DRIVER_TRANSACTION_ID

    def _invoke_driver_execute(
        self, sql: str, params: Optional[tuple], tid: Optional[str]
    ) -> Any:
        """Call driver.execute; some drivers omit transaction_id (TypeError fallback)."""
        try:
            return self.driver.execute(sql, params, tid)
        except TypeError:
            return self.driver.execute(sql, params)

    def _execute(self, sql: str, params: Optional[tuple] = None) -> None:
        """Execute SQL statement with optional locking."""
        tid = self._driver_transaction_id()
        result = None
        if self._lock:
            with self._lock:
                result = self._invoke_driver_execute(sql, params, tid)
        else:
            result = self._invoke_driver_execute(sql, params, tid)
        if isinstance(result, dict):
            setattr(self, "_last_execute_result", result)

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
        *,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute SQL and return result in RPC/driver contract format.

        Callers that use database.execute() and expect result.get("data", [])
        work with both DatabaseClient (RPC) and CodeDatabase.

        Args:
            sql: SQL statement.
            params: Optional parameters for the statement.
            transaction_id: Accepted for API parity with drivers and
                :func:`worker_project_activity` (local DB uses active CodeDatabase tx).
            priority: Accepted for API parity with :class:`DatabaseClient` RPC path;
                ignored for direct driver execution.

        Returns:
            Dict with at least key "data": list of rows for SELECT,
            empty list for INSERT/UPDATE/DELETE etc.
        """
        del transaction_id  # local path uses :meth:`_driver_transaction_id` via _execute
        del priority  # RPC hint only; no queue on direct driver
        if sql.strip().upper().startswith("SELECT"):
            rows = self._fetchall(sql, params)
            return {"data": rows}
        self._execute(sql, params)
        last = getattr(self, "_last_execute_result", None)
        if isinstance(last, dict):
            return last
        # Legacy void execute(); use rowcount for DML (worker_project_activity)
        drc = getattr(self.driver, "_rowcount", None)
        if isinstance(drc, int) and drc >= 0:
            return {"affected_rows": drc, "data": None}
        return {"data": []}

    @staticmethod
    def _valid_sql_ident(name: str) -> str:
        """Return valid sql ident."""
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            raise ValueError(f"invalid SQL identifier: {name!r}")
        return name

    def _select_table_via_sql(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """``SELECT`` for :mod:`worker_project_activity` when the driver has no ``select``."""
        t = self._valid_sql_ident(table_name)
        if columns:
            cs = ", ".join(self._valid_sql_ident(c) for c in columns)
        else:
            cs = "*"
        sql = f"SELECT {cs} FROM {t}"
        params: List[Any] = []
        if where:
            parts: List[str] = []
            for k, v in where.items():
                parts.append(f"{self._valid_sql_ident(k)} = ?")
                params.append(v)
            sql += " WHERE " + " AND ".join(parts)
        if order_by:
            obs = ", ".join(self._valid_sql_ident(x) for x in order_by)
            sql += f" ORDER BY {obs}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        if offset is not None:
            sql += f" OFFSET {int(offset)}"
        return self._fetchall(sql, tuple(params))

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[str]] = None,
        *,
        priority: int = 0,
    ) -> List[Dict[str, Any]]:
        """Table read (used by :mod:`worker_project_activity` lock reads)."""
        del priority  # Parity with :class:`DatabaseClient.select`; direct driver ignores it.
        dselect = getattr(self.driver, "select", None)
        if callable(dselect):
            if self._lock:
                with self._lock:
                    return dselect(
                        table_name,
                        where=where,
                        columns=columns,
                        limit=limit,
                        offset=offset,
                        order_by=order_by,
                    )
            return dselect(
                table_name,
                where=where,
                columns=columns,
                limit=limit,
                offset=offset,
                order_by=order_by,
            )
        return self._select_table_via_sql(
            table_name, where, columns, limit, offset, order_by
        )

    def _fetchone(
        self, sql: str, params: Optional[tuple] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch one row with optional locking."""
        # Prefer execute() returning {"data": [...]} (database_driver_pkg has no fetchone)
        tid = self._driver_transaction_id()
        if self._lock:
            with self._lock:
                result = self._invoke_driver_execute(sql, params, tid)
        else:
            result = self._invoke_driver_execute(sql, params, tid)
        if isinstance(result, dict) and "data" in result:
            data = result.get("data", [])
            return data[0] if data else None
        # Driver with fetchone (e.g. in-process sqlite stack)
        if hasattr(self.driver, "fetchone"):
            if self._lock:
                with self._lock:
                    return self.driver.fetchone(sql, params)
            return self.driver.fetchone(sql, params)
        return None

    def _fetchall(
        self, sql: str, params: Optional[tuple] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all rows with optional locking."""
        # Prefer execute() returning {"data": [...]} (database_driver_pkg has no fetchall)
        tid = self._driver_transaction_id()
        if self._lock:
            with self._lock:
                result = self._invoke_driver_execute(sql, params, tid)
        else:
            result = self._invoke_driver_execute(sql, params, tid)
        if isinstance(result, dict) and "data" in result:
            data = result.get("data", [])
            return list(data) if data else []
        # Driver with fetchall (e.g. in-process sqlite stack)
        if hasattr(self.driver, "fetchall"):
            if self._lock:
                with self._lock:
                    return self.driver.fetchall(sql, params)
            return self.driver.fetchall(sql, params)
        return []

    def _commit(self) -> None:
        """Commit transaction with optional locking."""
        if not hasattr(self.driver, "commit"):
            # Driver auto-commits in execute() (e.g. database_driver_pkg)
            return
        if self._lock:
            with self._lock:
                self.driver.commit()
        else:
            self.driver.commit()

    def _rollback(self) -> None:
        """Rollback transaction with optional locking."""
        if not hasattr(self.driver, "rollback"):
            return
        if self._lock:
            with self._lock:
                self.driver.rollback()
        else:
            self.driver.rollback()

    def begin_transaction(self) -> str:
        """
        Begin database transaction.

        Returns:
            Transaction ID (for use with execute_batch, commit_transaction, rollback_transaction).

        Raises:
            RuntimeError: If transaction is already active.
        """
        if self._transaction_active:
            raise RuntimeError("Transaction already active")

        # For SQLite Proxy driver, create transaction_id and set it in driver
        if self._driver_type == "sqlite_proxy":
            transaction_id = str(uuid.uuid4())
            if hasattr(self.driver, "_transaction_id"):
                self.driver._transaction_id = transaction_id
            # Send begin_transaction command to worker
            self.driver._execute_operation(
                "begin_transaction", transaction_id=transaction_id
            )
        else:
            # database_driver_pkg SQLite/Postgres: defer commit in run_* until driver.commit()
            transaction_id = LOCAL_DRIVER_TRANSACTION_ID
            self._transaction_active = True
            self._execute("BEGIN TRANSACTION")

        self._transaction_active = True
        logger.debug("Transaction started")
        return transaction_id

    def commit_transaction(self, transaction_id: Optional[str] = None) -> None:
        """
        Commit database transaction.

        Args:
            transaction_id: Optional; ignored for direct SQLite, used by proxy driver.

        Raises:
            RuntimeError: If no active transaction.
        """
        if not self._transaction_active:
            raise RuntimeError("No active transaction")

        # For SQLite Proxy driver, commit is handled by driver.commit()
        # which uses transaction_id
        self._commit()

        # Clear transaction_id in proxy driver if exists
        if self._driver_type == "sqlite_proxy" and hasattr(
            self.driver, "_transaction_id"
        ):
            self.driver._transaction_id = None

        self._transaction_active = False
        logger.debug("Transaction committed")

    def rollback_transaction(self, transaction_id: Optional[str] = None) -> None:
        """
        Rollback database transaction.

        Args:
            transaction_id: Optional; ignored for direct SQLite, used by proxy driver.

        Raises:
            RuntimeError: If no active transaction.
        """
        if not self._transaction_active:
            raise RuntimeError("No active transaction")

        # For SQLite Proxy driver, rollback is handled by driver.rollback()
        # which uses transaction_id
        self._rollback()

        # Clear transaction_id in proxy driver if exists
        if self._driver_type == "sqlite_proxy" and hasattr(
            self.driver, "_transaction_id"
        ):
            self.driver._transaction_id = None

        self._transaction_active = False
        logger.debug("Transaction rolled back")

    def execute_batch(
        self,
        operations: List[Tuple[str, Optional[tuple]]],
        transaction_id: Optional[str] = None,
        *,
        priority: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple SQL statements in order (same transaction).

        Used by update_file_data_atomic_batch. For direct SQLite driver,
        runs each (sql, params) via _execute and returns one result per op.

        Args:
            operations: List of (sql, params) tuples.
            transaction_id: Optional; ignored for direct SQLite (uses active transaction).
            priority: Accepted for API parity with :class:`DatabaseClient` RPC path;
                ignored for direct driver execution.

        Returns:
            List of dicts with keys affected_rows, lastrowid, data (one per operation).
        """
        del priority  # RPC hint only; no queue on direct driver
        effective_tid = transaction_id
        if effective_tid is None:
            effective_tid = self._driver_transaction_id()
        if hasattr(self.driver, "execute_batch"):
            try:
                if self._lock:
                    with self._lock:
                        return self.driver.execute_batch(operations, effective_tid)
                return self.driver.execute_batch(operations, effective_tid)
            except TypeError:
                if self._lock:
                    with self._lock:
                        return self.driver.execute_batch(operations)
                return self.driver.execute_batch(operations)

        results: List[Dict[str, Any]] = []
        for sql, params in operations:
            self._execute(sql, tuple(params) if params else None)
            lastrowid = self._lastrowid()
            data = None
            if sql.strip().upper().startswith("SELECT"):
                res = getattr(self, "_last_execute_result", None)
                if isinstance(res, dict) and "data" in res:
                    data = res.get("data")
                elif hasattr(self.driver, "fetchall") and data is None:
                    bind = tuple(params) if params else None
                    if self._lock:
                        with self._lock:
                            data = self.driver.fetchall(
                                sql, bind  # type: ignore[arg-type]
                            )
                    else:
                        data = self.driver.fetchall(sql, bind)  # type: ignore[arg-type]
            results.append(
                {
                    "affected_rows": 0,
                    "lastrowid": lastrowid,
                    "data": data,
                }
            )
        return results

    def upsert_code_chunks_batch(
        self,
        param_rows: List[Tuple[Any, ...]],
        transaction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Batch upsert ``code_chunks`` using portable SQL (same as RPC client's
        :meth:`code_analysis.core.database_client.client_operations._ClientOperationsMixin.upsert_code_chunks_batch`).

        Rows must match :mod:`code_analysis.core.database.code_chunk_sql`
        ``CODE_CHUNK_UPSERT_PARAM_COUNT`` / ``CODE_CHUNK_UPSERT_PARAM_ORDER``.
        """
        return self.execute_batch(
            build_code_chunk_upsert_batch(param_rows),
            transaction_id=transaction_id,
        )

    def execute_logical_write_operation(
        self, program: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run all batches in program under one transaction (in-process SQLite).

        Mirrors DatabaseClient.execute_logical_write_operation result shape.

        If a transaction is already active (e.g. ``restore_backup_file`` /
        ``replace_file_lines`` opened one before ``update_file_data_atomic_batch``),
        batches run in that outer transaction: no nested ``BEGIN``, and this
        method does not ``COMMIT`` / ``ROLLBACK`` (caller owns the transaction).
        ``sqlite_proxy`` keeps the previous behaviour (single outer RPC tx).
        """
        batches = program.get("batches")
        if not batches or not isinstance(batches, list):
            raise ValueError("LogicalWriteProgramV1 requires non-empty batches")
        outer_active = self._transaction_active
        nested = outer_active and self._driver_type != "sqlite_proxy"
        if nested:
            tid = self._driver_transaction_id()
        else:
            tid = self.begin_transaction()
        try:
            if program.get("defer_constraints") and not nested:
                self._execute("PRAGMA defer_foreign_keys=ON", None)
            batch_results: list[dict[str, Any]] = []
            for batch_ops in batches:
                results = self.execute_batch(batch_ops, tid)
                batch_results.append({"results": results})
            if not nested:
                self.commit_transaction(tid)
            return {
                "success": True,
                "data": {
                    "batch_results": batch_results,
                    "transaction_id": tid,
                },
            }
        except Exception:
            if not nested:
                try:
                    self.rollback_transaction(tid)
                except Exception:
                    pass
            raise

    def _in_transaction(self) -> bool:
        """
        Check if transaction is currently active.

        Returns:
            True if transaction is active, False otherwise.
        """
        return getattr(self, "_transaction_active", False)

    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions.

        Automatically commits on success and rolls back on exception.

        Example:
            with database.transaction():
                database._execute("INSERT INTO ...")
                database._execute("UPDATE ...")
        """
        self.begin_transaction()
        try:
            yield
            self.commit_transaction()
        except Exception:
            self.rollback_transaction()
            raise

    def _lastrowid(self) -> Optional[int]:
        """Get last row ID with optional locking."""
        if hasattr(self.driver, "lastrowid"):
            lastrowid = self.driver.lastrowid
            val = lastrowid() if callable(lastrowid) else lastrowid
            if self._lock:
                with self._lock:
                    val = lastrowid() if callable(lastrowid) else lastrowid
            return val
        # Driver returns lastrowid in execute() result (e.g. database_driver_pkg)
        res = getattr(self, "_last_execute_result", None)
        return res.get("lastrowid") if isinstance(res, dict) else None

    def _get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get table information with optional locking."""
        if self._lock:
            with self._lock:
                return self.driver.get_table_info(table_name)
        else:
            return self.driver.get_table_info(table_name)

    def _create_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        run_create_schema(self)

    def _migrate_to_uuid_projects(self) -> None:
        """Migrate projects table from INTEGER to UUID4 if needed."""
        run_migrate_to_uuid_projects(self)

    def _migrate_schema(self) -> None:
        """
        Migrate database schema - add missing columns, update structure.
        Called on every database initialization to ensure schema is up to date.
        """
        run_migrate_schema(self)

    def close(self) -> None:
        """Close database connection."""
        if self.driver:
            self.driver.disconnect()

    def __enter__(self) -> "CodeDatabase":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def get_all_chunks_for_faiss_rebuild(
        self, project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all code chunks with embeddings for FAISS index rebuild."""
        return _get_all_chunks_for_faiss_rebuild(self, project_id)

    def get_non_vectorized_chunks(
        self,
        project_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get chunks that have embeddings but need vector_id assignment."""
        return _get_non_vectorized_chunks(self, project_id, limit)

    async def update_chunk_vector_id(
        self,
        chunk_id: str,
        vector_id: int,
        embedding_model: Optional[str] = None,
    ) -> None:
        """Update chunk with vector_id and embedding_model (after FAISS add)."""
        await _update_chunk_vector_id(self, chunk_id, vector_id, embedding_model)

    def _get_schema_definition(self) -> Dict[str, Any]:
        """Return structured schema definition (delegates to get_schema_definition)."""
        return get_schema_definition()

    def sync_schema(self) -> Dict[str, Any]:
        """
        Synchronize database schema via driver.

        Gets schema definition and backup_dir from config, delegates to driver.
        This method should be called after driver connection is established.

        Returns:
            Dict with sync results from driver:
            {
                "success": bool,
                "backup_uuid": Optional[str],
                "changes_applied": List[str],
                "error": Optional[str]
            }

        Raises:
            RuntimeError: If schema sync fails (connection is blocked)
        """
        return self._do_sync_schema()
