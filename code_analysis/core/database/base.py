"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from contextlib import contextmanager
import logging
import threading

from ..db_driver import create_driver

logger = logging.getLogger(__name__)

# Schema version constant
SCHEMA_VERSION = "1.3.0"  # Current schema version (added files_total_at_start and files_vectorized to vectorization_stats)

# Migration methods registry: version -> migration function
# Each migration function receives driver instance and performs version-specific migrations
# Migration functions are called in order when upgrading from old version to new version
# Example usage:
#   MIGRATION_METHODS["1.0.0"] = lambda driver: driver._migrate_to_uuid_projects()
#   MIGRATION_METHODS["1.1.0"] = lambda driver: driver._migrate_add_datasets_table()
MIGRATION_METHODS: Dict[str, Callable[[Any], None]] = {
    # Register migration methods here
    # Format: "version": lambda driver: driver._migration_method_name()
    # Note: Methods are defined in SQLiteDriver, registry is here for centralization
}


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
            "poll_interval": 0.1,  # Polling interval in seconds (100ms default)
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

        # Connect driver before schema sync (required for SQLiteDriverProxy to initialize worker)
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

        # Sync schema after connection (replaces _create_schema() call)
        try:
            sync_result = self.sync_schema()
            if sync_result.get("changes_applied"):
                logger.info(
                    f"Schema synchronized: {len(sync_result['changes_applied'])} changes applied"
                )
        except RuntimeError as e:
            # Schema sync failed - connection is blocked
            logger.error(f"Schema sync failed, connection blocked: {e}")
            raise  # Re-raise to prevent database usage

    def __getattr__(self, name: str) -> Any:
        """
        Dynamic method support for mypy/static analysis.

        The `code_analysis.core.database` package attaches many module-level functions
        to this class at import time (facade pattern). Declaring `__getattr__`
        prevents `attr-defined` errors for those dynamically-injected methods.
        """
        raise AttributeError(name)

    def _execute(self, sql: str, params: Optional[tuple] = None) -> None:
        """Execute SQL statement with optional locking."""
        if self._lock:
            with self._lock:
                self.driver.execute(sql, params)
        else:
            self.driver.execute(sql, params)

    def _fetchone(
        self, sql: str, params: Optional[tuple] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch one row with optional locking."""
        if self._lock:
            with self._lock:
                return self.driver.fetchone(sql, params)
        else:
            return self.driver.fetchone(sql, params)

    def _fetchall(
        self, sql: str, params: Optional[tuple] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all rows with optional locking."""
        if self._lock:
            with self._lock:
                return self.driver.fetchall(sql, params)
        else:
            return self.driver.fetchall(sql, params)

    def _commit(self) -> None:
        """Commit transaction with optional locking."""
        if self._lock:
            with self._lock:
                self.driver.commit()
        else:
            self.driver.commit()

    def _rollback(self) -> None:
        """Rollback transaction with optional locking."""
        if self._lock:
            with self._lock:
                self.driver.rollback()
        else:
            self.driver.rollback()

    def begin_transaction(self) -> None:
        """
        Begin database transaction.

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
            self._execute("BEGIN TRANSACTION")

        self._transaction_active = True
        logger.debug("Transaction started")

    def commit_transaction(self) -> None:
        """
        Commit database transaction.

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

    def rollback_transaction(self) -> None:
        """
        Rollback database transaction.

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
        if self._lock:
            with self._lock:
                return self.driver.lastrowid()
        else:
            return self.driver.lastrowid()

    def _get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get table information with optional locking."""
        if self._lock:
            with self._lock:
                return self.driver.get_table_info(table_name)
        else:
            return self.driver.get_table_info(table_name)

    def _create_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        # All operations use driver interface - no direct connection access

        # Create watch_dirs table first (projects reference it)
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS watch_dirs (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now'))
                )
            """
        )

        # Create watch_dir_paths table (maps watch_dir_id to absolute path)
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS watch_dir_paths (
                    watch_dir_id TEXT PRIMARY KEY,
                    absolute_path TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (watch_dir_id) REFERENCES watch_dirs(id) ON DELETE CASCADE
                )
            """
        )

        # Create projects table (references watch_dirs)
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    root_path TEXT UNIQUE NOT NULL,
                    name TEXT,
                    comment TEXT,
                    watch_dir_id TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (watch_dir_id) REFERENCES watch_dirs(id) ON DELETE SET NULL
                )
            """
        )
        # Create index on watch_dir_id for performance
        try:
            self._execute(
                """
                CREATE INDEX IF NOT EXISTS idx_projects_watch_dir_id 
                ON projects(watch_dir_id)
                """
            )
        except Exception:
            pass  # Index might already exist
        # Create datasets table (Step 1.1 of refactor plan)
        # datasets table supports multi-root indexing within a project
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    name TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, root_path)
                )
            """
        )
        # Update files table to include dataset_id, watch_dir_id, and relative_path
        # Files now store relative_path from project root, not absolute path
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    watch_dir_id TEXT,
                    path TEXT NOT NULL,
                    relative_path TEXT,
                    lines INTEGER,
                    last_modified REAL,
                    has_docstring BOOLEAN,
                    deleted BOOLEAN DEFAULT 0,
                    original_path TEXT,
                    version_dir TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                    FOREIGN KEY (watch_dir_id) REFERENCES watch_dirs(id) ON DELETE SET NULL,
                    UNIQUE(project_id, dataset_id, path)
                )
            """
        )
        # Create partial index for deleted files (only indexes deleted=1)
        try:
            self._execute(
                """
                CREATE INDEX IF NOT EXISTS idx_files_deleted 
                ON files(deleted) WHERE deleted = 1
                """
            )
        except Exception:
            pass  # Index might already exist
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS classes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    docstring TEXT,
                    bases TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    UNIQUE(file_id, name, line)
                )
            """
        )
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS methods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    class_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    args TEXT,
                    docstring TEXT,
                    is_abstract BOOLEAN DEFAULT 0,
                    has_pass BOOLEAN DEFAULT 0,
                    has_not_implemented BOOLEAN DEFAULT 0,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                    UNIQUE(class_id, name, line)
                )
            """
        )
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS functions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    args TEXT,
                    docstring TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    UNIQUE(file_id, name, line)
                )
            """
        )
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    module TEXT,
                    import_type TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                )
            """
        )
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER,
                    project_id TEXT,
                    class_id INTEGER,
                    function_id INTEGER,
                    method_id INTEGER,
                    issue_type TEXT NOT NULL,
                    line INTEGER,
                    description TEXT,
                    metadata TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                    FOREIGN KEY (function_id) REFERENCES functions(id) ON DELETE CASCADE,
                    FOREIGN KEY (method_id) REFERENCES methods(id) ON DELETE CASCADE
                )
            """
        )
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS usages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    line INTEGER NOT NULL,
                    usage_type TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_class TEXT,
                    target_name TEXT NOT NULL,
                    context TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                )
            """
        )
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS code_content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER,
                    entity_name TEXT,
                    content TEXT NOT NULL,
                    docstring TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                )
            """
        )
        self._execute(
            """
                CREATE VIRTUAL TABLE IF NOT EXISTS code_content_fts USING fts5(
                    entity_type,
                    entity_name,
                    content,
                    docstring,
                    content_rowid='rowid',
                    content='code_content'
                )
            """
        )
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS ast_trees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    project_id TEXT NOT NULL,
                    ast_json TEXT NOT NULL,
                    ast_hash TEXT NOT NULL,
                    file_mtime REAL NOT NULL,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(file_id, ast_hash)
                )
            """
        )
        # Check if file_mtime column exists using driver interface
        table_info = self._get_table_info("ast_trees")
        columns = {col["name"]: col["type"] for col in table_info}
        if "file_mtime" not in columns:
            try:
                self._execute(
                    "ALTER TABLE ast_trees ADD COLUMN file_mtime REAL NOT NULL DEFAULT 0"
                )
                self._commit()
            except Exception:
                pass  # Column might already exist

        # Create CST trees table for source code storage
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS cst_trees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    project_id TEXT NOT NULL,
                    cst_code TEXT NOT NULL,
                    cst_hash TEXT NOT NULL,
                    file_mtime REAL NOT NULL,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(file_id, cst_hash)
                )
            """
        )
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS vector_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    vector_id INTEGER NOT NULL,
                    vector_dim INTEGER NOT NULL,
                    embedding_model TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, entity_type, entity_id)
                )
            """
        )
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS code_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    project_id TEXT NOT NULL,
                    chunk_uuid TEXT NOT NULL,
                    chunk_type TEXT NOT NULL,
                    chunk_text TEXT NOT NULL,
                    chunk_ordinal INTEGER,
                    vector_id INTEGER,
                    embedding_model TEXT,
                    bm25_score REAL,
                    embedding_vector TEXT,
                    class_id INTEGER,
                    function_id INTEGER,
                    method_id INTEGER,
                    line INTEGER,
                    ast_node_type TEXT,
                    source_type TEXT,
                    binding_level INTEGER DEFAULT 0,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                    FOREIGN KEY (function_id) REFERENCES functions(id) ON DELETE CASCADE,
                    FOREIGN KEY (method_id) REFERENCES methods(id) ON DELETE CASCADE,
                    UNIQUE(chunk_uuid)
                )
            """
        )
        # Try to add missing columns (if table already exists)
        try:
            self._execute("ALTER TABLE code_chunks ADD COLUMN bm25_score REAL")
            logger.info("Added bm25_score column to code_chunks table")
        except Exception:
            pass
        try:
            self._execute("ALTER TABLE code_chunks ADD COLUMN embedding_vector TEXT")
            logger.info("Added embedding_vector column to code_chunks table")
        except Exception:
            pass
        try:
            self._execute(
                "ALTER TABLE code_chunks ADD COLUMN binding_level INTEGER DEFAULT 0"
            )
            logger.info("Added binding_level column to code_chunks table")
        except Exception:
            pass
        try:
            self._execute(
                "ALTER TABLE code_chunks ADD COLUMN updated_at REAL DEFAULT (julianday('now'))"
            )
            logger.info("Added updated_at column to code_chunks table")
        except Exception:
            pass
        # Create code_duplicates table
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS code_duplicates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    duplicate_hash TEXT NOT NULL,
                    similarity REAL NOT NULL,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, duplicate_hash)
                )
            """
        )
        # Create duplicate_occurrences table
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS duplicate_occurrences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    duplicate_id INTEGER NOT NULL,
                    file_id INTEGER NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    code_snippet TEXT,
                    ast_node_id INTEGER,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (duplicate_id) REFERENCES code_duplicates(id) ON DELETE CASCADE,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                )
            """
        )
        # Create comprehensive_analysis_results table
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS comprehensive_analysis_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    project_id TEXT NOT NULL,
                    file_mtime REAL NOT NULL,
                    results_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(file_id, file_mtime)
                )
            """
        )
        # Create file_watcher_stats table for tracking file watcher cycle statistics
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS file_watcher_stats (
                    cycle_id TEXT PRIMARY KEY,
                    cycle_start_time REAL NOT NULL,
                    cycle_end_time REAL,
                    files_total_at_start INTEGER NOT NULL DEFAULT 0,
                    files_added INTEGER NOT NULL DEFAULT 0,
                    files_processed INTEGER NOT NULL DEFAULT 0,
                    files_skipped INTEGER NOT NULL DEFAULT 0,
                    files_failed INTEGER NOT NULL DEFAULT 0,
                    files_changed INTEGER NOT NULL DEFAULT 0,
                    files_deleted INTEGER NOT NULL DEFAULT 0,
                    total_processing_time_seconds REAL NOT NULL DEFAULT 0.0,
                    average_processing_time_seconds REAL,
                    current_project_id TEXT,
                    last_updated REAL DEFAULT (julianday('now'))
                )
            """
        )
        # Create vectorization_stats table for tracking vectorization cycle statistics
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS vectorization_stats (
                    cycle_id TEXT PRIMARY KEY,
                    cycle_start_time REAL NOT NULL,
                    cycle_end_time REAL,
                    chunks_total_at_start INTEGER NOT NULL DEFAULT 0,
                    chunks_processed INTEGER NOT NULL DEFAULT 0,
                    chunks_skipped INTEGER NOT NULL DEFAULT 0,
                    chunks_failed INTEGER NOT NULL DEFAULT 0,
                    files_total_at_start INTEGER NOT NULL DEFAULT 0,
                    files_vectorized INTEGER NOT NULL DEFAULT 0,
                    total_processing_time_seconds REAL NOT NULL DEFAULT 0.0,
                    average_processing_time_seconds REAL,
                    last_updated REAL DEFAULT (julianday('now'))
                )
            """
        )
        self._commit()
        self._migrate_to_uuid_projects()
        self._migrate_schema()
        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_projects_root_path ON projects(root_path)",
            "CREATE INDEX IF NOT EXISTS idx_datasets_project ON datasets(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_datasets_root_path ON datasets(root_path)",
            "CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_files_dataset ON files(dataset_id)",
            "CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)",
            "CREATE INDEX IF NOT EXISTS idx_classes_name ON classes(name)",
            "CREATE INDEX IF NOT EXISTS idx_classes_file ON classes(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_methods_name ON methods(name)",
            "CREATE INDEX IF NOT EXISTS idx_methods_class ON methods(class_id)",
            "CREATE INDEX IF NOT EXISTS idx_functions_name ON functions(name)",
            "CREATE INDEX IF NOT EXISTS idx_functions_file ON functions(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_imports_file ON imports(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_imports_name ON imports(name)",
            "CREATE INDEX IF NOT EXISTS idx_issues_type ON issues(issue_type)",
            "CREATE INDEX IF NOT EXISTS idx_issues_file ON issues(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_usages_file ON usages(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_usages_target ON usages(target_type, target_name)",
            "CREATE INDEX IF NOT EXISTS idx_usages_class_name ON usages(target_class, target_name)",
            "CREATE INDEX IF NOT EXISTS idx_code_content_file ON code_content(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_code_content_entity ON code_content(entity_type, entity_id)",
            "CREATE INDEX IF NOT EXISTS idx_ast_trees_file ON ast_trees(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_ast_trees_project ON ast_trees(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_ast_trees_hash ON ast_trees(ast_hash)",
            "CREATE INDEX IF NOT EXISTS idx_vector_index_project ON vector_index(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_vector_index_entity ON vector_index(entity_type, entity_id)",
            "CREATE INDEX IF NOT EXISTS idx_vector_index_vector_id ON vector_index(vector_id)",
            "CREATE INDEX IF NOT EXISTS idx_code_chunks_file ON code_chunks(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_code_chunks_project ON code_chunks(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_code_chunks_uuid ON code_chunks(chunk_uuid)",
            "CREATE INDEX IF NOT EXISTS idx_code_chunks_vector ON code_chunks(vector_id)",
            "CREATE INDEX IF NOT EXISTS idx_code_chunks_not_vectorized ON code_chunks(project_id, id) WHERE vector_id IS NULL",
            "CREATE INDEX IF NOT EXISTS idx_files_deleted ON files(deleted) WHERE deleted = 1",
            "CREATE INDEX IF NOT EXISTS idx_code_duplicates_project ON code_duplicates(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_code_duplicates_hash ON code_duplicates(duplicate_hash)",
            "CREATE INDEX IF NOT EXISTS idx_duplicate_occurrences_duplicate ON duplicate_occurrences(duplicate_id)",
            "CREATE INDEX IF NOT EXISTS idx_duplicate_occurrences_file ON duplicate_occurrences(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_file_watcher_stats_start_time ON file_watcher_stats(cycle_start_time)",
            "CREATE INDEX IF NOT EXISTS idx_vectorization_stats_start_time ON vectorization_stats(cycle_start_time)",
        ]
        for index_sql in indexes:
            self._execute(index_sql)
        self._commit()

    def _migrate_to_uuid_projects(self) -> None:
        """Migrate projects table from INTEGER to UUID4 if needed."""
        # Use driver interface to get table info
        table_info = self._get_table_info("projects")
        columns = {col["name"]: col["type"] for col in table_info}
        if "id" in columns and columns["id"] == "INTEGER":
            logger.info("Migrating projects table to UUID4...")
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS projects_new (
                    id TEXT PRIMARY KEY,
                    root_path TEXT UNIQUE NOT NULL,
                    name TEXT,
                    comment TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now'))
                )
            """
            )
            old_projects = self._fetchall(
                "SELECT id, root_path, name, created_at, updated_at FROM projects"
            )
            for row in old_projects:
                old_id = row["id"]
                root_path = row["root_path"]
                name = row["name"]
                created_at = row["created_at"]
                updated_at = row["updated_at"]
                new_id = str(uuid.uuid4())
                self._execute(
                    """
                    INSERT INTO projects_new (
                        id, root_path, name, comment, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        new_id,
                        root_path,
                        name,
                        f"Migrated from project_id {old_id}",
                        created_at,
                        updated_at,
                    ),
                )
                self._execute(
                    "UPDATE files SET project_id = ? WHERE project_id = ?",
                    (new_id, old_id),
                )
            self._execute("DROP TABLE projects")
            self._execute("ALTER TABLE projects_new RENAME TO projects")
            self._execute("PRAGMA foreign_keys = OFF")
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS files_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    lines INTEGER,
                    last_modified REAL,
                    has_docstring BOOLEAN,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, dataset_id, path)
                )
            """
            )
            self._execute(
                """
                INSERT INTO files_new (
                    id, project_id, dataset_id, path, lines, last_modified,
                    has_docstring, created_at, updated_at
                )
                SELECT id, project_id, ?, path, lines, last_modified,
                       has_docstring, created_at, updated_at
                FROM files
            """,
                (str(uuid.uuid4()),),  # Create default dataset_id for migration
            )
            self._execute("DROP TABLE files")
            self._execute("ALTER TABLE files_new RENAME TO files")
            self._execute("PRAGMA foreign_keys = ON")
            self._commit()
            logger.info("Migration to UUID4 completed")
        if "comment" not in columns:
            try:
                self._execute("ALTER TABLE projects ADD COLUMN comment TEXT")
                self._commit()
            except Exception:
                pass

    def _migrate_schema(self) -> None:
        """
        Migrate database schema - add missing columns, update structure.

        This method is called on every database initialization to ensure
        the schema is up to date with the latest version.
        """
        # Check if datasets table exists, if not create it
        try:
            self._get_table_info("datasets")
            datasets_exists = True
        except Exception:
            datasets_exists = False

        if not datasets_exists:
            logger.info("Creating datasets table...")
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    name TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, root_path)
                )
            """
            )
            self._commit()

        # Check if files table has dataset_id column
        files_table_info = self._get_table_info("files")
        files_columns = {col["name"]: col["type"] for col in files_table_info}

        if "dataset_id" not in files_columns:
            logger.info("Migrating files table: adding dataset_id column")
            # This is a complex migration - we need to:
            # 1. Create default datasets for existing projects
            # 2. Add dataset_id column to files
            # 3. Update all files to have a dataset_id
            try:
                # Get all projects
                projects = self._fetchall("SELECT id, root_path FROM projects")
                for project in projects:
                    project_id = project["id"]
                    root_path = project["root_path"]
                    # Create default dataset for this project
                    dataset_id = str(uuid.uuid4())
                    self._execute(
                        """
                        INSERT OR IGNORE INTO datasets (id, project_id, root_path, name)
                        VALUES (?, ?, ?, ?)
                    """,
                        (
                            dataset_id,
                            project_id,
                            root_path,
                            f"Default dataset for {root_path}",
                        ),
                    )

                # Add dataset_id column
                self._execute("ALTER TABLE files ADD COLUMN dataset_id TEXT")
                # Update all files to have dataset_id (use first dataset for each project)
                for project in projects:
                    project_id = project["id"]
                    dataset = self._fetchone(
                        "SELECT id FROM datasets WHERE project_id = ? LIMIT 1",
                        (project_id,),
                    )
                    if dataset:
                        dataset_id = dataset["id"]
                        self._execute(
                            "UPDATE files SET dataset_id = ? WHERE project_id = ? AND dataset_id IS NULL",
                            (dataset_id, project_id),
                        )

                # Make dataset_id NOT NULL (requires recreating table in SQLite)
                # For now, we'll just ensure it's set for all rows
                self._commit()
                logger.info("Migration completed: files table now has dataset_id")
            except Exception as e:
                logger.warning(f"Migration issue (may already exist): {e}")

        # Use driver interface to get table info
        issues_table_info = self._get_table_info("issues")
        issues_columns = {col["name"]: col["type"] for col in issues_table_info}
        if "project_id" not in issues_columns:
            try:
                logger.info("Migrating issues table: adding project_id column")
                self._execute("ALTER TABLE issues ADD COLUMN project_id TEXT")
                self._execute(
                    """
                    UPDATE issues
                    SET project_id = (
                        SELECT f.project_id
                        FROM files f
                        WHERE f.id = issues.file_id
                    )
                    WHERE file_id IS NOT NULL
                """
                )
                self._commit()
                logger.info("Migration completed: issues table now has project_id")
            except Exception as e:
                logger.warning(f"Migration issue (may already exist): {e}")
        # Check if index exists using driver interface
        index_check = self._fetchone(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_issues_project'"
        )
        if not index_check:
            try:
                self._execute(
                    "CREATE INDEX IF NOT EXISTS idx_issues_project ON issues(project_id)"
                )
                self._commit()
            except Exception as e:
                logger.warning(f"Could not create index idx_issues_project: {e}")
        chunks_table_info = self._get_table_info("code_chunks")
        chunks_columns = {col["name"]: col["type"] for col in chunks_table_info}
        new_columns = {
            "class_id": "INTEGER",
            "function_id": "INTEGER",
            "method_id": "INTEGER",
            "line": "INTEGER",
            "ast_node_type": "TEXT",
            "source_type": "TEXT",
            "bm25_score": "REAL",
            "embedding_vector": "TEXT",
            "binding_level": "INTEGER DEFAULT 0",
        }
        for col_name, col_type in new_columns.items():
            if col_name not in chunks_columns:
                try:
                    logger.info(
                        f"Migrating code_chunks table: adding {col_name} column"
                    )
                    self._execute(
                        f"ALTER TABLE code_chunks ADD COLUMN {col_name} {col_type}"
                    )
                    self._commit()
                except Exception as e:
                    logger.warning(
                        f"Could not add column {col_name} to code_chunks: {e}"
                    )

        # Migration: Add deleted, original_path, version_dir columns to files table if they don't exist
        if "deleted" not in files_columns:
            try:
                logger.info("Migrating files table: adding deleted column")
                self._execute("ALTER TABLE files ADD COLUMN deleted BOOLEAN DEFAULT 0")
                self._commit()
            except Exception as e:
                logger.warning(f"Could not add deleted column to files: {e}")

        # Migration: Add current_project_id column to file_watcher_stats table if it doesn't exist
        try:
            file_watcher_stats_table_info = self._get_table_info("file_watcher_stats")
            file_watcher_stats_columns = {
                col["name"]: col["type"] for col in file_watcher_stats_table_info
            }
            if "current_project_id" not in file_watcher_stats_columns:
                logger.info(
                    "Migrating file_watcher_stats table: adding current_project_id column"
                )
                self._execute(
                    "ALTER TABLE file_watcher_stats ADD COLUMN current_project_id TEXT"
                )
                self._commit()
        except Exception as e:
            # Table might not exist yet, that's OK
            logger.debug(
                f"Could not check/add current_project_id to file_watcher_stats: {e}"
            )

        # Migration: Add files_total_at_start and files_vectorized columns to vectorization_stats table
        try:
            vectorization_stats_table_info = self._get_table_info("vectorization_stats")
            vectorization_stats_columns = {
                col["name"]: col["type"] for col in vectorization_stats_table_info
            }
            if "files_total_at_start" not in vectorization_stats_columns:
                logger.info(
                    "Migrating vectorization_stats table: adding files_total_at_start column"
                )
                self._execute(
                    "ALTER TABLE vectorization_stats ADD COLUMN files_total_at_start INTEGER NOT NULL DEFAULT 0"
                )
                self._commit()
            if "files_vectorized" not in vectorization_stats_columns:
                logger.info(
                    "Migrating vectorization_stats table: adding files_vectorized column"
                )
                self._execute(
                    "ALTER TABLE vectorization_stats ADD COLUMN files_vectorized INTEGER NOT NULL DEFAULT 0"
                )
                self._commit()
        except Exception as e:
            # Table might not exist yet, that's OK
            logger.debug(
                f"Could not check/add files columns to vectorization_stats: {e}"
            )

        if "original_path" not in files_columns:
            try:
                logger.info("Migrating files table: adding original_path column")
                self._execute("ALTER TABLE files ADD COLUMN original_path TEXT")
                self._commit()
            except Exception as e:
                logger.warning(f"Could not add original_path column to files: {e}")

        if "version_dir" not in files_columns:
            try:
                logger.info("Migrating files table: adding version_dir column")
                self._execute("ALTER TABLE files ADD COLUMN version_dir TEXT")
                self._commit()
            except Exception as e:
                logger.warning(f"Could not add version_dir column to files: {e}")

        # Create index after adding deleted column
        if "deleted" in files_columns or "deleted" not in files_columns:
            try:
                self._execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_files_deleted 
                    ON files(deleted) WHERE deleted = 1
                    """
                )
                self._commit()
                logger.info("Created index idx_files_deleted")
            except Exception as e:
                logger.warning(f"Could not create index idx_files_deleted: {e}")

        # Migration: Add complexity column to functions table if it doesn't exist
        functions_table_info = self._get_table_info("functions")
        functions_columns = {col["name"]: col["type"] for col in functions_table_info}
        if "complexity" not in functions_columns:
            try:
                logger.info("Migrating functions table: adding complexity column")
                self._execute("ALTER TABLE functions ADD COLUMN complexity INTEGER")
                self._commit()
            except Exception as e:
                logger.warning(f"Could not add complexity column to functions: {e}")

        # Migration: Add complexity column to methods table if it doesn't exist
        methods_table_info = self._get_table_info("methods")
        methods_columns = {col["name"]: col["type"] for col in methods_table_info}
        if "complexity" not in methods_columns:
            try:
                logger.info("Migrating methods table: adding complexity column")
                self._execute("ALTER TABLE methods ADD COLUMN complexity INTEGER")
                self._commit()
            except Exception as e:
                logger.warning(f"Could not add complexity column to methods: {e}")

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
        self, project_id: Optional[str] = None, dataset_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all code chunks with embeddings for FAISS index rebuild.

        Implements dataset-scoped FAISS (Step 2 of refactor plan).
        If project_id and dataset_id are provided, filters chunks for that dataset only.
        If only project_id is provided, returns chunks for all datasets in the project.
        If neither is provided, returns chunks for all projects (legacy mode).

        Args:
            project_id: Optional project ID to filter by.
            dataset_id: Optional dataset ID to filter by (requires project_id).

        Returns:
            List of chunk records with embeddings.
        """
        if dataset_id and not project_id:
            raise ValueError("dataset_id requires project_id")

        if project_id and dataset_id:
            # Dataset-scoped: get chunks only for this dataset
            return self._fetchall(
                """
                SELECT 
                    cc.id,
                    cc.file_id,
                    cc.project_id,
                    cc.chunk_uuid,
                    cc.chunk_type,
                    cc.chunk_text,
                    cc.chunk_ordinal,
                    cc.vector_id,
                    cc.embedding_model,
                    cc.embedding_vector,
                    cc.class_id,
                    cc.function_id,
                    cc.method_id,
                    cc.line,
                    cc.ast_node_type,
                    cc.source_type
                FROM code_chunks cc
                INNER JOIN files f ON cc.file_id = f.id
                WHERE cc.project_id = ?
                  AND f.dataset_id = ?
                  AND cc.embedding_model IS NOT NULL
                  AND cc.embedding_vector IS NOT NULL
                ORDER BY cc.id
                """,
                (project_id, dataset_id),
            )
        elif project_id:
            # Project-scoped: get chunks for all datasets in project
            return self._fetchall(
                """
                SELECT 
                    cc.id,
                    cc.file_id,
                    cc.project_id,
                    cc.chunk_uuid,
                    cc.chunk_type,
                    cc.chunk_text,
                    cc.chunk_ordinal,
                    cc.vector_id,
                    cc.embedding_model,
                    cc.embedding_vector,
                    cc.class_id,
                    cc.function_id,
                    cc.method_id,
                    cc.line,
                    cc.ast_node_type,
                    cc.source_type
                FROM code_chunks cc
                WHERE cc.project_id = ?
                  AND cc.embedding_model IS NOT NULL
                  AND cc.embedding_vector IS NOT NULL
                ORDER BY cc.id
                """,
                (project_id,),
            )
        else:
            # Legacy mode: all chunks (for backward compatibility)
            return self._fetchall(
                """
                SELECT 
                    cc.id,
                    cc.file_id,
                    cc.project_id,
                    cc.chunk_uuid,
                    cc.chunk_type,
                    cc.chunk_text,
                    cc.chunk_ordinal,
                    cc.vector_id,
                    cc.embedding_model,
                    cc.embedding_vector,
                    cc.class_id,
                    cc.function_id,
                    cc.method_id,
                    cc.line,
                    cc.ast_node_type,
                    cc.source_type
                FROM code_chunks cc
                WHERE cc.embedding_model IS NOT NULL
                  AND cc.embedding_vector IS NOT NULL
                ORDER BY cc.id
                """
            )

    def get_non_vectorized_chunks(
        self,
        project_id: str,
        dataset_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get chunks that have embeddings but need vector_id assignment.

        Implements dataset-scoped vectorization (Step 2 of refactor plan).
        If dataset_id is provided, returns chunks only for that dataset.
        If dataset_id is None, returns chunks for all datasets in project.

        Args:
            project_id: Project ID (REQUIRED for write operations).
            dataset_id: Optional dataset ID to filter by.
            limit: Maximum number of chunks to return.

        Returns:
            List of chunk records that need vector_id assignment.
        """
        if dataset_id:
            # Dataset-scoped: get chunks only for this dataset
            return self._fetchall(
                """
                SELECT 
                    cc.id,
                    cc.file_id,
                    cc.project_id,
                    cc.chunk_uuid,
                    cc.chunk_type,
                    cc.chunk_text,
                    cc.chunk_ordinal,
                    cc.vector_id,
                    cc.embedding_model,
                    cc.embedding_vector,
                    cc.class_id,
                    cc.function_id,
                    cc.method_id,
                    cc.line,
                    cc.ast_node_type,
                    cc.source_type,
                    f.dataset_id
                FROM code_chunks cc
                INNER JOIN files f ON cc.file_id = f.id
                WHERE cc.project_id = ?
                  AND f.dataset_id = ?
                  AND (f.deleted = 0 OR f.deleted IS NULL)
                  AND cc.embedding_vector IS NOT NULL
                  AND cc.vector_id IS NULL
                ORDER BY cc.id
                LIMIT ?
                """,
                (project_id, dataset_id, limit),
            )
        else:
            # Project-scoped: get chunks for all datasets in project
            return self._fetchall(
                """
                SELECT 
                    cc.id,
                    cc.file_id,
                    cc.project_id,
                    cc.chunk_uuid,
                    cc.chunk_type,
                    cc.chunk_text,
                    cc.chunk_ordinal,
                    cc.vector_id,
                    cc.embedding_model,
                    cc.embedding_vector,
                    cc.class_id,
                    cc.function_id,
                    cc.method_id,
                    cc.line,
                    cc.ast_node_type,
                    cc.source_type,
                    f.dataset_id
                FROM code_chunks cc
                INNER JOIN files f ON cc.file_id = f.id
                WHERE cc.project_id = ?
                  AND (f.deleted = 0 OR f.deleted IS NULL)
                  AND cc.embedding_vector IS NOT NULL
                  AND cc.vector_id IS NULL
                ORDER BY cc.id
                LIMIT ?
                """,
                (project_id, limit),
            )

    async def update_chunk_vector_id(
        self,
        chunk_id: int,
        vector_id: int,
        embedding_model: Optional[str] = None,
    ) -> None:
        """
        Update chunk with vector_id and embedding_model.

        This method is called after adding vector to FAISS index.
        After update, chunk is automatically excluded from get_non_vectorized_chunks query.

        Args:
            chunk_id: Chunk ID.
            vector_id: FAISS index position (vector ID).
            embedding_model: Optional embedding model name.

        Returns:
            None
        """
        if embedding_model:
            self._execute(
                """
                UPDATE code_chunks
                SET vector_id = ?, embedding_model = ?
                WHERE id = ?
                """,
                (vector_id, embedding_model, chunk_id),
            )
        else:
            self._execute(
                """
                UPDATE code_chunks
                SET vector_id = ?
                WHERE id = ?
                """,
                (vector_id, chunk_id),
            )
        self._commit()

    def _get_schema_definition(self) -> Dict[str, Any]:
        """
        Get structured schema definition for synchronization.

        This method returns a structured dictionary representation of the schema,
        not SQL statements. This is used by SchemaComparator to compare and migrate schemas.

        Returns:
            Dictionary with schema definition containing:
            - version: Schema version string
            - tables: Dict of table definitions with columns, foreign keys, constraints
            - indexes: List of index definitions
            - virtual_tables: List of virtual table definitions (FTS5)
            - migration_methods: Registry of migration methods
        """
        return {
            "version": SCHEMA_VERSION,
            "tables": {
                "db_settings": {
                    "columns": [
                        {
                            "name": "key",
                            "type": "TEXT",
                            "not_null": True,
                            "primary_key": True,
                        },
                        {"name": "value", "type": "TEXT", "not_null": True},
                        {
                            "name": "updated_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [],
                    "unique_constraints": [],
                    "check_constraints": [],
                },
                "watch_dirs": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "TEXT",
                            "not_null": True,
                            "primary_key": True,
                        },
                        {"name": "name", "type": "TEXT", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                        {
                            "name": "updated_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [],
                    "unique_constraints": [],
                    "check_constraints": [],
                },
                "watch_dir_paths": {
                    "columns": [
                        {
                            "name": "watch_dir_id",
                            "type": "TEXT",
                            "not_null": True,
                            "primary_key": True,
                        },
                        {"name": "absolute_path", "type": "TEXT", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                        {
                            "name": "updated_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["watch_dir_id"],
                            "references_table": "watch_dirs",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        }
                    ],
                    "unique_constraints": [],
                    "check_constraints": [],
                },
                "projects": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "TEXT",
                            "not_null": True,
                            "primary_key": True,
                        },
                        {"name": "root_path", "type": "TEXT", "not_null": True},
                        {"name": "name", "type": "TEXT", "not_null": False},
                        {"name": "comment", "type": "TEXT", "not_null": False},
                        {"name": "watch_dir_id", "type": "TEXT", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                        {
                            "name": "updated_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["watch_dir_id"],
                            "references_table": "watch_dirs",
                            "references_columns": ["id"],
                            "on_delete": "SET NULL",
                        }
                    ],
                    "unique_constraints": [{"columns": ["root_path"]}],
                    "check_constraints": [],
                },
                "datasets": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "TEXT",
                            "not_null": True,
                            "primary_key": True,
                        },
                        {"name": "project_id", "type": "TEXT", "not_null": True},
                        {"name": "root_path", "type": "TEXT", "not_null": True},
                        {"name": "name", "type": "TEXT", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                        {
                            "name": "updated_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["project_id"],
                            "references_table": "projects",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        }
                    ],
                    "unique_constraints": [{"columns": ["project_id", "root_path"]}],
                    "check_constraints": [],
                },
                "files": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "project_id", "type": "TEXT", "not_null": True},
                        {"name": "dataset_id", "type": "TEXT", "not_null": True},
                        {"name": "watch_dir_id", "type": "TEXT", "not_null": False},
                        {"name": "path", "type": "TEXT", "not_null": True},
                        {"name": "relative_path", "type": "TEXT", "not_null": False},
                        {"name": "lines", "type": "INTEGER", "not_null": False},
                        {"name": "last_modified", "type": "REAL", "not_null": False},
                        {"name": "has_docstring", "type": "BOOLEAN", "not_null": False},
                        {
                            "name": "deleted",
                            "type": "BOOLEAN",
                            "not_null": False,
                            "default": "0",
                        },
                        {"name": "original_path", "type": "TEXT", "not_null": False},
                        {"name": "version_dir", "type": "TEXT", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                        {
                            "name": "updated_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["project_id"],
                            "references_table": "projects",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["dataset_id"],
                            "references_table": "datasets",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["watch_dir_id"],
                            "references_table": "watch_dirs",
                            "references_columns": ["id"],
                            "on_delete": "SET NULL",
                        },
                    ],
                    "unique_constraints": [
                        {"columns": ["project_id", "dataset_id", "path"]}
                    ],
                    "check_constraints": [],
                },
                "classes": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "file_id", "type": "INTEGER", "not_null": True},
                        {"name": "name", "type": "TEXT", "not_null": True},
                        {"name": "line", "type": "INTEGER", "not_null": True},
                        {"name": "docstring", "type": "TEXT", "not_null": False},
                        {"name": "bases", "type": "TEXT", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["file_id"],
                            "references_table": "files",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        }
                    ],
                    "unique_constraints": [{"columns": ["file_id", "name", "line"]}],
                    "check_constraints": [],
                },
                "methods": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "class_id", "type": "INTEGER", "not_null": True},
                        {"name": "name", "type": "TEXT", "not_null": True},
                        {"name": "line", "type": "INTEGER", "not_null": True},
                        {"name": "args", "type": "TEXT", "not_null": False},
                        {"name": "docstring", "type": "TEXT", "not_null": False},
                        {
                            "name": "is_abstract",
                            "type": "BOOLEAN",
                            "not_null": False,
                            "default": "0",
                        },
                        {
                            "name": "has_pass",
                            "type": "BOOLEAN",
                            "not_null": False,
                            "default": "0",
                        },
                        {
                            "name": "has_not_implemented",
                            "type": "BOOLEAN",
                            "not_null": False,
                            "default": "0",
                        },
                        {"name": "complexity", "type": "INTEGER", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["class_id"],
                            "references_table": "classes",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        }
                    ],
                    "unique_constraints": [{"columns": ["class_id", "name", "line"]}],
                    "check_constraints": [],
                },
                "functions": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "file_id", "type": "INTEGER", "not_null": True},
                        {"name": "name", "type": "TEXT", "not_null": True},
                        {"name": "line", "type": "INTEGER", "not_null": True},
                        {"name": "args", "type": "TEXT", "not_null": False},
                        {"name": "docstring", "type": "TEXT", "not_null": False},
                        {"name": "complexity", "type": "INTEGER", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["file_id"],
                            "references_table": "files",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        }
                    ],
                    "unique_constraints": [{"columns": ["file_id", "name", "line"]}],
                    "check_constraints": [],
                },
                "imports": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "file_id", "type": "INTEGER", "not_null": True},
                        {"name": "name", "type": "TEXT", "not_null": True},
                        {"name": "module", "type": "TEXT", "not_null": False},
                        {"name": "import_type", "type": "TEXT", "not_null": True},
                        {"name": "line", "type": "INTEGER", "not_null": True},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["file_id"],
                            "references_table": "files",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        }
                    ],
                    "unique_constraints": [],
                    "check_constraints": [],
                },
                "issues": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "file_id", "type": "INTEGER", "not_null": False},
                        {"name": "project_id", "type": "TEXT", "not_null": False},
                        {"name": "class_id", "type": "INTEGER", "not_null": False},
                        {"name": "function_id", "type": "INTEGER", "not_null": False},
                        {"name": "method_id", "type": "INTEGER", "not_null": False},
                        {"name": "issue_type", "type": "TEXT", "not_null": True},
                        {"name": "line", "type": "INTEGER", "not_null": False},
                        {"name": "description", "type": "TEXT", "not_null": False},
                        {"name": "metadata", "type": "TEXT", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["file_id"],
                            "references_table": "files",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["project_id"],
                            "references_table": "projects",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["class_id"],
                            "references_table": "classes",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["function_id"],
                            "references_table": "functions",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["method_id"],
                            "references_table": "methods",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                    ],
                    "unique_constraints": [],
                    "check_constraints": [],
                },
                "usages": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "file_id", "type": "INTEGER", "not_null": True},
                        {"name": "line", "type": "INTEGER", "not_null": True},
                        {"name": "usage_type", "type": "TEXT", "not_null": True},
                        {"name": "target_type", "type": "TEXT", "not_null": True},
                        {"name": "target_class", "type": "TEXT", "not_null": False},
                        {"name": "target_name", "type": "TEXT", "not_null": True},
                        {"name": "context", "type": "TEXT", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["file_id"],
                            "references_table": "files",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        }
                    ],
                    "unique_constraints": [],
                    "check_constraints": [],
                },
                "code_content": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "file_id", "type": "INTEGER", "not_null": True},
                        {"name": "entity_type", "type": "TEXT", "not_null": True},
                        {"name": "entity_id", "type": "INTEGER", "not_null": False},
                        {"name": "entity_name", "type": "TEXT", "not_null": False},
                        {"name": "content", "type": "TEXT", "not_null": True},
                        {"name": "docstring", "type": "TEXT", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["file_id"],
                            "references_table": "files",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        }
                    ],
                    "unique_constraints": [],
                    "check_constraints": [],
                },
                "ast_trees": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "file_id", "type": "INTEGER", "not_null": True},
                        {"name": "project_id", "type": "TEXT", "not_null": True},
                        {"name": "ast_json", "type": "TEXT", "not_null": True},
                        {"name": "ast_hash", "type": "TEXT", "not_null": True},
                        {"name": "file_mtime", "type": "REAL", "not_null": True},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                        {
                            "name": "updated_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["file_id"],
                            "references_table": "files",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["project_id"],
                            "references_table": "projects",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                    ],
                    "unique_constraints": [{"columns": ["file_id", "ast_hash"]}],
                    "check_constraints": [],
                },
                "cst_trees": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "file_id", "type": "INTEGER", "not_null": True},
                        {"name": "project_id", "type": "TEXT", "not_null": True},
                        {"name": "cst_code", "type": "TEXT", "not_null": True},
                        {"name": "cst_hash", "type": "TEXT", "not_null": True},
                        {"name": "file_mtime", "type": "REAL", "not_null": True},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                        {
                            "name": "updated_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["file_id"],
                            "references_table": "files",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["project_id"],
                            "references_table": "projects",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                    ],
                    "unique_constraints": [{"columns": ["file_id", "cst_hash"]}],
                    "check_constraints": [],
                },
                "vector_index": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "project_id", "type": "TEXT", "not_null": True},
                        {"name": "entity_type", "type": "TEXT", "not_null": True},
                        {"name": "entity_id", "type": "INTEGER", "not_null": True},
                        {"name": "vector_id", "type": "INTEGER", "not_null": True},
                        {"name": "vector_dim", "type": "INTEGER", "not_null": True},
                        {"name": "embedding_model", "type": "TEXT", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["project_id"],
                            "references_table": "projects",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        }
                    ],
                    "unique_constraints": [
                        {"columns": ["project_id", "entity_type", "entity_id"]}
                    ],
                    "check_constraints": [],
                },
                "code_chunks": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "file_id", "type": "INTEGER", "not_null": True},
                        {"name": "project_id", "type": "TEXT", "not_null": True},
                        {"name": "chunk_uuid", "type": "TEXT", "not_null": True},
                        {"name": "chunk_type", "type": "TEXT", "not_null": True},
                        {"name": "chunk_text", "type": "TEXT", "not_null": True},
                        {"name": "chunk_ordinal", "type": "INTEGER", "not_null": False},
                        {"name": "vector_id", "type": "INTEGER", "not_null": False},
                        {"name": "embedding_model", "type": "TEXT", "not_null": False},
                        {"name": "bm25_score", "type": "REAL", "not_null": False},
                        {"name": "embedding_vector", "type": "TEXT", "not_null": False},
                        {"name": "class_id", "type": "INTEGER", "not_null": False},
                        {"name": "function_id", "type": "INTEGER", "not_null": False},
                        {"name": "method_id", "type": "INTEGER", "not_null": False},
                        {"name": "line", "type": "INTEGER", "not_null": False},
                        {"name": "ast_node_type", "type": "TEXT", "not_null": False},
                        {"name": "source_type", "type": "TEXT", "not_null": False},
                        {
                            "name": "binding_level",
                            "type": "INTEGER",
                            "not_null": False,
                            "default": "0",
                        },
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                        {
                            "name": "updated_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["file_id"],
                            "references_table": "files",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["project_id"],
                            "references_table": "projects",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["class_id"],
                            "references_table": "classes",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["function_id"],
                            "references_table": "functions",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["method_id"],
                            "references_table": "methods",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                    ],
                    "unique_constraints": [{"columns": ["chunk_uuid"]}],
                    "check_constraints": [],
                },
                "code_duplicates": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "project_id", "type": "TEXT", "not_null": True},
                        {"name": "duplicate_hash", "type": "TEXT", "not_null": True},
                        {"name": "similarity", "type": "REAL", "not_null": True},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["project_id"],
                            "references_table": "projects",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        }
                    ],
                    "unique_constraints": [
                        {"columns": ["project_id", "duplicate_hash"]}
                    ],
                    "check_constraints": [],
                },
                "duplicate_occurrences": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "duplicate_id", "type": "INTEGER", "not_null": True},
                        {"name": "file_id", "type": "INTEGER", "not_null": True},
                        {"name": "start_line", "type": "INTEGER", "not_null": True},
                        {"name": "end_line", "type": "INTEGER", "not_null": True},
                        {"name": "code_snippet", "type": "TEXT", "not_null": False},
                        {"name": "ast_node_id", "type": "INTEGER", "not_null": False},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["duplicate_id"],
                            "references_table": "code_duplicates",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["file_id"],
                            "references_table": "files",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                    ],
                    "unique_constraints": [],
                    "check_constraints": [],
                },
                "comprehensive_analysis_results": {
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "not_null": True,
                            "primary_key": True,
                            "autoincrement": True,
                        },
                        {"name": "file_id", "type": "INTEGER", "not_null": True},
                        {"name": "project_id", "type": "TEXT", "not_null": True},
                        {"name": "file_mtime", "type": "REAL", "not_null": True},
                        {"name": "results_json", "type": "TEXT", "not_null": True},
                        {"name": "summary_json", "type": "TEXT", "not_null": True},
                        {
                            "name": "created_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                        {
                            "name": "updated_at",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [
                        {
                            "columns": ["file_id"],
                            "references_table": "files",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                        {
                            "columns": ["project_id"],
                            "references_table": "projects",
                            "references_columns": ["id"],
                            "on_delete": "CASCADE",
                        },
                    ],
                    "unique_constraints": [{"columns": ["file_id", "file_mtime"]}],
                    "check_constraints": [],
                },
                "file_watcher_stats": {
                    "columns": [
                        {
                            "name": "cycle_id",
                            "type": "TEXT",
                            "not_null": True,
                            "primary_key": True,
                        },
                        {
                            "name": "cycle_start_time",
                            "type": "REAL",
                            "not_null": True,
                        },
                        {"name": "cycle_end_time", "type": "REAL", "not_null": False},
                        {
                            "name": "files_total_at_start",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "files_added",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "files_processed",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "files_skipped",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "files_failed",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "files_changed",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "files_deleted",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "total_processing_time_seconds",
                            "type": "REAL",
                            "not_null": True,
                            "default": "0.0",
                        },
                        {
                            "name": "average_processing_time_seconds",
                            "type": "REAL",
                            "not_null": False,
                        },
                        {
                            "name": "last_updated",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                        {
                            "name": "current_project_id",
                            "type": "TEXT",
                            "not_null": False,
                        },
                    ],
                    "foreign_keys": [],
                    "unique_constraints": [],
                    "check_constraints": [],
                },
                "vectorization_stats": {
                    "columns": [
                        {
                            "name": "cycle_id",
                            "type": "TEXT",
                            "not_null": True,
                            "primary_key": True,
                        },
                        {
                            "name": "cycle_start_time",
                            "type": "REAL",
                            "not_null": True,
                        },
                        {"name": "cycle_end_time", "type": "REAL", "not_null": False},
                        {
                            "name": "chunks_total_at_start",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "chunks_processed",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "chunks_skipped",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "chunks_failed",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "files_total_at_start",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "files_vectorized",
                            "type": "INTEGER",
                            "not_null": True,
                            "default": "0",
                        },
                        {
                            "name": "total_processing_time_seconds",
                            "type": "REAL",
                            "not_null": True,
                            "default": "0.0",
                        },
                        {
                            "name": "average_processing_time_seconds",
                            "type": "REAL",
                            "not_null": False,
                        },
                        {
                            "name": "last_updated",
                            "type": "REAL",
                            "not_null": False,
                            "default": "julianday('now')",
                        },
                    ],
                    "foreign_keys": [],
                    "unique_constraints": [],
                    "check_constraints": [],
                },
            },
            "indexes": [
                {
                    "name": "idx_projects_root_path",
                    "table": "projects",
                    "columns": ["root_path"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_datasets_project",
                    "table": "datasets",
                    "columns": ["project_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_datasets_root_path",
                    "table": "datasets",
                    "columns": ["root_path"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_files_project",
                    "table": "files",
                    "columns": ["project_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_files_dataset",
                    "table": "files",
                    "columns": ["dataset_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_files_path",
                    "table": "files",
                    "columns": ["path"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_files_deleted",
                    "table": "files",
                    "columns": ["deleted"],
                    "unique": False,
                    "where_clause": "deleted = 1",
                },
                {
                    "name": "idx_classes_name",
                    "table": "classes",
                    "columns": ["name"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_classes_file",
                    "table": "classes",
                    "columns": ["file_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_methods_name",
                    "table": "methods",
                    "columns": ["name"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_methods_class",
                    "table": "methods",
                    "columns": ["class_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_functions_name",
                    "table": "functions",
                    "columns": ["name"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_functions_file",
                    "table": "functions",
                    "columns": ["file_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_imports_file",
                    "table": "imports",
                    "columns": ["file_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_imports_name",
                    "table": "imports",
                    "columns": ["name"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_issues_type",
                    "table": "issues",
                    "columns": ["issue_type"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_issues_file",
                    "table": "issues",
                    "columns": ["file_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_issues_project",
                    "table": "issues",
                    "columns": ["project_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_usages_file",
                    "table": "usages",
                    "columns": ["file_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_usages_target",
                    "table": "usages",
                    "columns": ["target_type", "target_name"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_usages_class_name",
                    "table": "usages",
                    "columns": ["target_class", "target_name"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_code_content_file",
                    "table": "code_content",
                    "columns": ["file_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_code_content_entity",
                    "table": "code_content",
                    "columns": ["entity_type", "entity_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_ast_trees_file",
                    "table": "ast_trees",
                    "columns": ["file_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_ast_trees_project",
                    "table": "ast_trees",
                    "columns": ["project_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_ast_trees_hash",
                    "table": "ast_trees",
                    "columns": ["ast_hash"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_vector_index_project",
                    "table": "vector_index",
                    "columns": ["project_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_vector_index_entity",
                    "table": "vector_index",
                    "columns": ["entity_type", "entity_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_vector_index_vector_id",
                    "table": "vector_index",
                    "columns": ["vector_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_code_chunks_file",
                    "table": "code_chunks",
                    "columns": ["file_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_code_chunks_project",
                    "table": "code_chunks",
                    "columns": ["project_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_code_chunks_uuid",
                    "table": "code_chunks",
                    "columns": ["chunk_uuid"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_code_chunks_vector",
                    "table": "code_chunks",
                    "columns": ["vector_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_code_chunks_not_vectorized",
                    "table": "code_chunks",
                    "columns": ["project_id", "id"],
                    "unique": False,
                    "where_clause": "vector_id IS NULL",
                },
                {
                    "name": "idx_code_duplicates_project",
                    "table": "code_duplicates",
                    "columns": ["project_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_code_duplicates_hash",
                    "table": "code_duplicates",
                    "columns": ["duplicate_hash"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_duplicate_occurrences_duplicate",
                    "table": "duplicate_occurrences",
                    "columns": ["duplicate_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_duplicate_occurrences_file",
                    "table": "duplicate_occurrences",
                    "columns": ["file_id"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_file_watcher_stats_start_time",
                    "table": "file_watcher_stats",
                    "columns": ["cycle_start_time"],
                    "unique": False,
                    "where_clause": None,
                },
                {
                    "name": "idx_vectorization_stats_start_time",
                    "table": "vectorization_stats",
                    "columns": ["cycle_start_time"],
                    "unique": False,
                    "where_clause": None,
                },
            ],
            "virtual_tables": [
                {
                    "name": "code_content_fts",
                    "type": "fts5",
                    "columns": ["entity_type", "entity_name", "content", "docstring"],
                    "options": {"content_rowid": "rowid", "content": "code_content"},
                }
            ],
            "migration_methods": MIGRATION_METHODS,
        }

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
        schema_definition = self._get_schema_definition()

        # Get backup_dir from driver config (should be set from StoragePaths)
        backup_dir = self.driver_config.get("config", {}).get("backup_dir")
        if not backup_dir:
            # Fallback: infer from db_path
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
