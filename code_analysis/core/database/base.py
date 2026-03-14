"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..db_driver import create_driver

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

logger = logging.getLogger(__name__)


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
            logger.info(f"[CodeDatabase] Calling create_driver({driver_type}, ...)")
            print(
                f"[CodeDatabase] Calling create_driver({driver_type}, ...)", flush=True
            )
            self.driver = create_driver(driver_type, driver_cfg)
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
        if not self.driver.is_thread_safe:
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
        db_path = getattr(driver, "db_path", None)
        if driver_config is None and db_path is not None:
            driver_config = {
                "type": "sqlite",
                "config": {"path": str(Path(db_path).resolve())},
            }
        elif driver_config is None:
            driver_config = {"type": "sqlite", "config": {}}
        logger.debug(
            "CodeDatabase.from_existing_driver: reusing driver (no connect, no sync_schema)"
        )
        obj = object.__new__(cls)
        obj.driver = driver
        obj._driver_type = "sqlite"
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

    def _execute(self, sql: str, params: Optional[tuple] = None) -> None:
        """Execute SQL statement with optional locking."""
        result = None
        if self._lock:
            with self._lock:
                result = self.driver.execute(sql, params)
        else:
            result = self.driver.execute(sql, params)
        if isinstance(result, dict):
            setattr(self, "_last_execute_result", result)

    def execute(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        """
        Execute SQL and return result in RPC/driver contract format.

        Callers that use database.execute() and expect result.get("data", [])
        work with both DatabaseClient (RPC) and CodeDatabase.

        Args:
            sql: SQL statement.
            params: Optional parameters for the statement.

        Returns:
            Dict with at least key "data": list of rows for SELECT,
            empty list for INSERT/UPDATE/DELETE etc.
        """
        if sql.strip().upper().startswith("SELECT"):
            rows = self._fetchall(sql, params)
            return {"data": rows}
        self._execute(sql, params)
        return {"data": []}

    def _fetchone(
        self, sql: str, params: Optional[tuple] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch one row with optional locking."""
        # Prefer execute() returning {"data": [...]} (database_driver_pkg has no fetchone)
        if self._lock:
            with self._lock:
                result = self.driver.execute(sql, params)
        else:
            result = self.driver.execute(sql, params)
        if isinstance(result, dict) and "data" in result:
            data = result.get("data", [])
            return data[0] if data else None
        # Driver with fetchone (e.g. db_driver/sqlite)
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
        if self._lock:
            with self._lock:
                result = self.driver.execute(sql, params)
        else:
            result = self.driver.execute(sql, params)
        if isinstance(result, dict) and "data" in result:
            data = result.get("data", [])
            return list(data) if data else []
        # Driver with fetchall (e.g. db_driver/sqlite)
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
            # For direct SQLite driver, use standard BEGIN TRANSACTION
            transaction_id = "local"
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
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple SQL statements in order (same transaction).

        Used by update_file_data_atomic_batch. For direct SQLite driver,
        runs each (sql, params) via _execute and returns one result per op.

        Args:
            operations: List of (sql, params) tuples.
            transaction_id: Optional; ignored for direct SQLite (uses active transaction).

        Returns:
            List of dicts with keys affected_rows, lastrowid, data (one per operation).
        """
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
        chunk_id: int,
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
