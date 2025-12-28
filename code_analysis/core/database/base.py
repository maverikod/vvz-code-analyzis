"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging
import threading

from ..db_driver import create_driver
from .driver_compat import DriverBackedConnection

logger = logging.getLogger(__name__)

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

    def __init__(
        self,
        db_path: Optional[Path] = None,
        driver_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize database connection and create schema.

        Args:
            db_path: Path to database file (for backward compatibility, creates SQLite driver)
            driver_config: Driver configuration dict with 'type' and 'config' keys.
                          If None and db_path provided, uses SQLite driver.
        """
        # Load driver
        if driver_config:
            driver_type = driver_config.get("type", "sqlite")
            driver_cfg = driver_config.get("config", {})
        elif db_path:
            # Backward compatibility: use SQLite driver
            driver_type = "sqlite"
            # IMPORTANT:
            # Use the direct sqlite driver by default for server stability.
            # Proxy-based access must be explicitly enabled via driver_config
            # (`{"type": "sqlite", "config": {"use_proxy": True, ...}}`) where needed.
            resolved = Path(db_path).resolve()
            driver_cfg = {"path": str(resolved)}
            self.db_path = resolved
        else:
            raise ValueError("Either db_path or driver_config must be provided")

        try:
            self.driver = create_driver(driver_type, driver_cfg)
            logger.info(f"Database driver '{driver_type}' loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load database driver '{driver_type}': {e}")
            raise

        # Backward compatibility:
        # Many legacy modules expect `self.conn.cursor().execute(...)`.
        # For proxy drivers, expose a lightweight driver-backed connection shim.
        driver_conn = getattr(self.driver, "conn", None)
        if driver_conn is not None:
            self.conn = driver_conn
        else:
            self.conn = DriverBackedConnection(self.driver)

        # Use lock only if driver is not thread-safe
        if not self.driver.is_thread_safe:
            # Use driver instance as lock key (each instance gets its own lock)
            lock_key = f"{driver_type}:{id(self.driver)}"
            self._lock = _get_db_lock(lock_key)
        else:
            self._lock = None

        self._create_schema()

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
        # Create projects table first (other tables reference it)
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    root_path TEXT UNIQUE NOT NULL,
                    name TEXT,
                    comment TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now'))
                )
            """
        )
        self._execute(
            """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    lines INTEGER,
                    last_modified REAL,
                    has_docstring BOOLEAN,
                    deleted BOOLEAN DEFAULT 0,
                    original_path TEXT,
                    version_dir TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, path)
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
                CREATE TABLE IF NOT EXISTS dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_file_id INTEGER NOT NULL,
                    target_file_id INTEGER NOT NULL,
                    dependency_type TEXT,
                    created_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (source_file_id) REFERENCES files(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_file_id) REFERENCES files(id) ON DELETE CASCADE,
                    UNIQUE(source_file_id, target_file_id)
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
        self._commit()
        self._migrate_to_uuid_projects()
        self._migrate_schema()
        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_projects_root_path ON projects(root_path)",
            "CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id)",
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
                    path TEXT NOT NULL,
                    lines INTEGER,
                    last_modified REAL,
                    has_docstring BOOLEAN,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, path)
                )
            """
            )
            self._execute(
                """
                INSERT INTO files_new (
                    id, project_id, path, lines, last_modified,
                    has_docstring, created_at, updated_at
                )
                SELECT id, project_id, path, lines, last_modified,
                       has_docstring, created_at, updated_at
                FROM files
            """
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
        files_table_info = self._get_table_info("files")
        files_columns = {col["name"]: col["type"] for col in files_table_info}
        
        if "deleted" not in files_columns:
            try:
                logger.info("Migrating files table: adding deleted column")
                self._execute("ALTER TABLE files ADD COLUMN deleted BOOLEAN DEFAULT 0")
                self._commit()
            except Exception as e:
                logger.warning(f"Could not add deleted column to files: {e}")
        
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
