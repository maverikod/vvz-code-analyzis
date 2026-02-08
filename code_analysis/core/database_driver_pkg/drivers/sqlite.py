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
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..exceptions import DriverConnectionError, DriverOperationError
from .base import BaseDatabaseDriver
from .sqlite_operations import SQLiteOperations
from .sqlite_schema import SQLiteSchemaManager
from .sqlite_transactions import SQLiteTransactionManager

logger = logging.getLogger(__name__)

# Canonical schema for indexing_worker_stats (create and migrate).
# Must stay in sync with code_analysis.core.database.base CodeDatabase.
INDEXING_WORKER_STATS_TABLE = "indexing_worker_stats"
INDEXING_WORKER_STATS_COLUMNS: List[tuple] = [
    ("cycle_id", "TEXT PRIMARY KEY"),
    ("cycle_start_time", "REAL NOT NULL"),
    ("cycle_end_time", "REAL"),
    ("files_total_at_start", "INTEGER NOT NULL DEFAULT 0"),
    ("files_indexed", "INTEGER NOT NULL DEFAULT 0"),
    ("files_failed", "INTEGER NOT NULL DEFAULT 0"),
    ("total_processing_time_seconds", "REAL NOT NULL DEFAULT 0.0"),
    ("average_processing_time_seconds", "REAL"),
    ("last_updated", "REAL DEFAULT (julianday('now'))"),
]
INDEXING_WORKER_STATS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_indexing_worker_stats_start_time "
    f"ON {INDEXING_WORKER_STATS_TABLE}(cycle_start_time)"
)


class SQLiteDriver(BaseDatabaseDriver):
    """SQLite driver for database driver process.

    Works with tables directly (insert, update, delete, select).
    All operations are table-level, not object-level.

    Batching: execute_batch is inherited from BaseDatabaseDriver; the default
    implementation runs each (sql, params) via execute() using the same
    connection/transaction when transaction_id is set. No SQLite-specific
    override unless native batch optimization (e.g. executemany) is added later.
    """

    def __init__(self) -> None:
        """Initialize SQLite driver."""
        self.conn: Optional[sqlite3.Connection] = None
        self.db_path: Optional[Path] = None
        self._transaction_manager: Optional[SQLiteTransactionManager] = None
        self._schema_manager: Optional[SQLiteSchemaManager] = None
        self._operations: Optional[SQLiteOperations] = None

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

            # Recover from failed schema migration: if "files" is missing but "temp_files" exists, rename back.
            # Runs on every connect() so any leftover temp_files (e.g. from aborted migration in another process)
            # is restored to "files" before index_file or other operations run.
            self._recover_files_table_if_needed()
            # Ensure migrations for columns used by workers (e.g. needs_chunking)
            self._ensure_files_table_migrations()
            self._ensure_code_chunks_migrations()
            self._ensure_indexing_worker_stats_table()
            self._ensure_indexing_errors_table()
        except Exception as e:
            raise DriverConnectionError(f"Failed to connect to database: {e}") from e

    def _ensure_indexing_errors_table(self) -> None:
        """Create indexing_errors table if missing (file_path + error when indexing fails)."""
        if not self.conn:
            return
        try:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='indexing_errors'"
            )
            if cur.fetchone() is not None:
                return
            logger.info("Creating indexing_errors table (driver)")
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS indexing_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    error_type TEXT,
                    error_message TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    UNIQUE(project_id, file_path)
                )
                """
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_indexing_errors_project_path "
                "ON indexing_errors(project_id, file_path)"
            )
            self.conn.commit()
        except Exception as e:
            logger.warning("Could not create indexing_errors table: %s", e)
            try:
                self.conn.rollback()
            except Exception:
                pass

    def _ensure_code_chunks_migrations(self) -> None:
        """Add code_chunks.token_count if missing (worker add_code_chunk needs it)."""
        if not self._schema_manager:
            return
        try:
            info = self._schema_manager.get_table_info("code_chunks")
            columns = {row["name"] for row in info}
            if "token_count" not in columns:
                logger.info(
                    "Migrating code_chunks table: adding token_count column (driver)"
                )
                self.conn.execute(
                    "ALTER TABLE code_chunks ADD COLUMN token_count INTEGER"
                )
                self.conn.commit()
        except Exception as e:
            logger.warning("Could not add token_count to code_chunks in driver: %s", e)
            try:
                self.conn.rollback()
            except Exception:
                pass

    def _ensure_indexing_worker_stats_table(self) -> None:
        """Create indexing_worker_stats if missing and add any missing columns (canonical structure)."""
        if not self.conn or not self._schema_manager:
            return
        table = INDEXING_WORKER_STATS_TABLE
        try:
            info = self._schema_manager.get_table_info(table)
        except Exception:
            info = []
        existing = {row["name"] for row in info} if info else set()

        if not existing:
            # Table missing: create with full canonical schema
            try:
                logger.info(
                    "Creating %s table in driver (required by indexing worker)",
                    table,
                )
                cols = ", ".join(
                    f"{name} {spec}" for name, spec in INDEXING_WORKER_STATS_COLUMNS
                )
                self.conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({cols})")
                self.conn.execute(INDEXING_WORKER_STATS_INDEX)
                self.conn.commit()
                return
            except Exception as e:
                logger.warning("Could not create %s in driver: %s", table, e)
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                return

        # Table exists: add any missing columns (keep structure in sync)
        for name, spec in INDEXING_WORKER_STATS_COLUMNS:
            if name in existing:
                continue
            if "PRIMARY KEY" in spec:
                continue  # PK cannot be added via ALTER
            try:
                logger.info(
                    "Migrating %s: adding column %s (driver)",
                    table,
                    name,
                )
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")
                self.conn.commit()
                existing.add(name)
            except Exception as e:
                logger.warning(
                    "Could not add column %s to %s in driver: %s",
                    name,
                    table,
                    e,
                )
                try:
                    self.conn.rollback()
                except Exception:
                    pass

        # Ensure index exists
        try:
            self.conn.execute(INDEXING_WORKER_STATS_INDEX)
            self.conn.commit()
        except Exception as e:
            logger.debug("Index for %s may already exist: %s", table, e)
            try:
                self.conn.rollback()
            except Exception:
                pass

    def _recover_files_table_if_needed(self) -> None:
        """Recover from failed schema migration: if table 'files' is missing but 'temp_files' exists, rename back.

        A partial schema sync (e.g. ALTER TABLE files RENAME TO temp_files then crash) can leave
        only temp_files. This restores the 'files' table so index_file and other operations succeed.
        """
        if not self.conn:
            return
        try:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
            )
            if cur.fetchone() is not None:
                return
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='temp_files'"
            )
            if cur.fetchone() is None:
                return
            logger.info(
                "Recovering from failed migration: renaming temp_files back to files"
            )
            self.conn.execute("ALTER TABLE temp_files RENAME TO files")
            self.conn.commit()
        except Exception as e:
            logger.warning("Could not recover files table: %s", e)
            try:
                self.conn.rollback()
            except Exception:
                pass

    def _ensure_files_table_migrations(self) -> None:
        """Run migrations on files table (e.g. needs_chunking) if column is missing.

        Workers (file_watcher, vectorization) use raw SQL that references these columns.
        This ensures the column exists when driver opens the DB (sync_schema may not run).
        """
        if not self._schema_manager:
            return
        try:
            info = self._schema_manager.get_table_info("files")
            columns = {row["name"] for row in info}
            if "needs_chunking" not in columns:
                logger.info(
                    "Migrating files table: adding needs_chunking column (driver)"
                )
                self.conn.execute(
                    "ALTER TABLE files ADD COLUMN needs_chunking INTEGER DEFAULT 0"
                )
                self.conn.commit()
            if "dataset_id" in columns:
                logger.info(
                    "Migrating files table: dropping dataset_id column (driver)"
                )
                try:
                    self.conn.execute("ALTER TABLE files DROP COLUMN dataset_id")
                    self.conn.commit()
                except Exception as drop_e:
                    logger.warning(
                        "Could not drop dataset_id (SQLite 3.35+ required): %s",
                        drop_e,
                    )
                    try:
                        self.conn.rollback()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(
                "Could not add needs_chunking column to files in driver: %s", e
            )
            try:
                self.conn.rollback()
            except Exception:
                pass

    def disconnect(self) -> None:
        """Close SQLite connection.

        Raises:
            DriverConnectionError: If disconnection fails
        """
        try:
            # Close all transactions
            if self._transaction_manager:
                self._transaction_manager.close_all()

            if self.conn:
                self.conn.close()
                self.conn = None
        except Exception as e:
            raise DriverConnectionError(f"Failed to disconnect: {e}") from e

    def create_table(self, schema: Dict[str, Any]) -> bool:
        """Create database table.

        Args:
            schema: Table schema definition with keys:
                - name: Table name
                - columns: List of column definitions (name, type, nullable, default, etc.)
                - constraints: Optional list of constraints (primary_key, foreign_key, etc.)

        Returns:
            True if table was created successfully, False otherwise

        Raises:
            DriverOperationError: If operation fails
        """
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        try:
            table_name = schema.get("name")
            if not table_name:
                raise DriverOperationError("Table name is required in schema")

            columns = schema.get("columns", [])
            if not columns:
                raise DriverOperationError("At least one column is required")

            # Build CREATE TABLE SQL
            column_defs = []
            for col in columns:
                col_name = col.get("name")
                col_type = col.get("type", "TEXT")
                nullable = col.get("nullable", True)
                default = col.get("default")
                primary_key = col.get("primary_key", False)

                col_def = f"{col_name} {col_type}"
                if not nullable:
                    col_def += " NOT NULL"
                if default is not None:
                    if isinstance(default, str) and "(" not in default:
                        col_def += f" DEFAULT '{default}'"
                    else:
                        col_def += (
                            f" DEFAULT ({default})"
                            if isinstance(default, str)
                            else f" DEFAULT {default}"
                        )
                if primary_key:
                    col_def += " PRIMARY KEY"

                column_defs.append(col_def)

            # Add constraints
            constraints = schema.get("constraints", [])
            for constraint in constraints:
                if constraint.get("type") == "primary_key":
                    cols = constraint.get("columns", [])
                    if cols:
                        column_defs.append(f"PRIMARY KEY ({', '.join(cols)})")
                elif constraint.get("type") == "foreign_key":
                    cols = constraint.get("columns", [])
                    ref_table = constraint.get("references_table")
                    ref_cols = constraint.get("references_columns", [])
                    if cols and ref_table and ref_cols:
                        column_defs.append(
                            f"FOREIGN KEY ({', '.join(cols)}) "
                            f"REFERENCES {ref_table} ({', '.join(ref_cols)})"
                        )

            sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(column_defs)})"
            self.conn.execute(sql)
            self.conn.commit()
            return True
        except Exception as e:
            raise DriverOperationError(f"Failed to create table: {e}") from e

    def drop_table(self, table_name: str) -> bool:
        """Drop database table.

        Args:
            table_name: Name of the table to drop

        Returns:
            True if table was dropped successfully, False otherwise

        Raises:
            DriverOperationError: If operation fails
        """
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        try:
            sql = f"DROP TABLE IF EXISTS {table_name}"
            self.conn.execute(sql)
            self.conn.commit()
            return True
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

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute raw SQL statement.

        Args:
            sql: SQL statement
            params: Optional tuple of parameters for parameterized query
            transaction_id: Optional transaction ID. If provided, uses transaction connection.

        Returns:
            Dictionary with operation result (affected_rows, lastrowid, data, etc.)

        Raises:
            DriverOperationError: If operation fails
        """
        # Use transaction connection if transaction_id is provided
        sql_preview = (sql.strip()[:60] + "…") if len(sql.strip()) > 60 else sql.strip()
        logger.info(
            "[CHAIN] sqlite driver execute sql_preview=%s tid=%s",
            sql_preview,
            (transaction_id[:8] + "…") if transaction_id else None,
        )
        if transaction_id:
            if not self._transaction_manager:
                raise DriverOperationError("Transaction manager not initialized")
            if transaction_id not in self._transaction_manager._transactions:
                logger.warning(
                    "[CHAIN] sqlite driver execute transaction_id not in _transactions"
                )
                raise DriverOperationError(f"Transaction {transaction_id} not found")
            conn = self._transaction_manager._transactions[transaction_id]
        else:
            if not self.conn:
                raise DriverOperationError("Database connection not established")
            conn = self.conn

        # Normalize params: sqlite3 expects tuple/list (for ?) or dict (for :name).
        # RPC may send list (JSON); avoid passing str or other invalid types.
        bind_params: Optional[tuple | dict] = None
        if params is not None:
            if isinstance(params, dict):
                bind_params = params
            elif isinstance(params, (list, tuple)):
                bind_params = tuple(params) if params else ()
            else:
                raise DriverOperationError(
                    f"execute params must be tuple, list, or dict; got {type(params).__name__}"
                )

        try:
            cursor = conn.cursor()
            try:
                if bind_params is not None and bind_params != ():
                    cursor.execute(sql, bind_params)
                else:
                    cursor.execute(sql)

                result: Dict[str, Any] = {
                    "affected_rows": cursor.rowcount,
                    "lastrowid": cursor.lastrowid,
                }

                # If it's a SELECT statement, fetch data
                if sql.strip().upper().startswith("SELECT"):
                    rows = cursor.fetchall()
                    result["data"] = [dict(row) for row in rows]

                # Only commit if not in transaction (writes are persisted)
                if not transaction_id:
                    try:
                        conn.commit()
                    except Exception as commit_err:
                        msg = str(commit_err).lower()
                        # SQLite can raise when no transaction is active (e.g. autocommit or implicit commit)
                        if "no transaction" in msg or "cannot commit" in msg:
                            logger.debug(
                                "Commit skipped (no active transaction): %s",
                                commit_err,
                            )
                        else:
                            raise DriverOperationError(
                                f"Failed to commit: {commit_err}"
                            ) from commit_err
                return result
            finally:
                cursor.close()
        except Exception as e:
            # Only rollback if not in transaction (transaction rollback is handled separately)
            if not transaction_id:
                try:
                    conn.rollback()
                except Exception:
                    pass  # Ignore rollback errors (e.g. no transaction)
            raise DriverOperationError(f"Failed to execute SQL: {e}") from e

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
