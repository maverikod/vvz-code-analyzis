"""
Database module for code mapper.

This module provides SQLite database functionality for storing
and querying code analysis data.

NOTE:
    A split implementation exists under `code_analysis/core/database/` (package).
    This monolithic module is kept temporarily for compatibility until the
    migration is verified by tests.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sqlite3
import json
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging
import threading

logger = logging.getLogger(__name__)


class CodeDatabase:
    """SQLite database for code analysis data."""

    def __init__(self, db_path: Path) -> None:
        """Initialize database connection and create schema."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: sqlite3.Connection
        # Mutex for all database operations
        self._lock = threading.Lock()
        self._connect()
        self._create_schema()

    def _connect(self) -> None:
        """Establish database connection."""
        with self._lock:
            # Reduce probability of "database is locked" under concurrent readers/writers.
            # - timeout: wait a bit for locks instead of failing fast
            # - WAL: allows concurrent reads during writes
            self.conn = sqlite3.connect(
                str(self.db_path),
                timeout=30,
                check_same_thread=False,
            )
            self.conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self.conn.execute("PRAGMA foreign_keys = ON")
            # Best-effort pragmas (safe defaults for a local SQLite file)
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")
            self.conn.execute("PRAGMA busy_timeout = 5000")

    def _create_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        if not self.conn:
            raise RuntimeError("Database connection not established")
        cursor = self.conn.cursor()

        # Projects table with UUID4
        cursor.execute(
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

        # Files table
        cursor.execute(
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
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_files_deleted 
                ON files(deleted) WHERE deleted = 1
                """
            )
        except Exception:
            pass  # Index might already exist

        # Classes table
        cursor.execute(
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

        # Methods table
        cursor.execute(
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

        # Functions table
        cursor.execute(
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

        # Imports table
        cursor.execute(
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

        # Issues table
        cursor.execute(
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

        # Dependencies table
        cursor.execute(
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

        # Usages table - tracks where methods/properties are used
        cursor.execute(
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

        # Code content table for full-text search
        cursor.execute(
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

        # Full-text search virtual table (FTS5)
        cursor.execute(
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

        # AST trees table - stores serialized AST trees
        cursor.execute(
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

        # Add file_mtime column if it doesn't exist (migration)
        cursor.execute("PRAGMA table_info(ast_trees)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        if "file_mtime" not in columns:
            try:
                cursor.execute(
                    "ALTER TABLE ast_trees ADD COLUMN file_mtime REAL NOT NULL DEFAULT 0"
                )
                self.conn.commit()
            except sqlite3.OperationalError:
                # Column might already exist in some cases
                pass

        # Vector index metadata table - stores FAISS index metadata
        cursor.execute(
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

        # Code chunks table - stores semantic chunks from svo_client
        cursor.execute(
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
                bm25_score REAL,  -- BM25 score from chunker
                embedding_vector TEXT,  -- JSON array of embedding vector (if available from chunker)
                -- Context binding fields
                class_id INTEGER,
                function_id INTEGER,
                method_id INTEGER,
                line INTEGER,
                ast_node_type TEXT,
                source_type TEXT,  -- 'docstring', 'comment', 'file_docstring'
                binding_level INTEGER DEFAULT 0, -- 0 ok; 1 file; 2 class; 3 method/function; 4 node; 5 line
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

        # Add bm25_score and embedding_vector columns if they don't exist (migration)
        try:
            cursor.execute("ALTER TABLE code_chunks ADD COLUMN bm25_score REAL")
            logger.info("Added bm25_score column to code_chunks table")
        except Exception:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE code_chunks ADD COLUMN embedding_vector TEXT")
            logger.info("Added embedding_vector column to code_chunks table")
        except Exception:
            pass  # Column already exists

        try:
            cursor.execute(
                "ALTER TABLE code_chunks ADD COLUMN binding_level INTEGER DEFAULT 0"
            )
            logger.info("Added binding_level column to code_chunks table")
        except Exception:
            pass  # Column already exists

        self.conn.commit()

        # Migrate existing database if needed (before creating indexes)
        self._migrate_to_uuid_projects()

        # Migrate schema (add missing columns, etc.)
        self._migrate_schema()

        # Create indexes after migration
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
            (
                "CREATE INDEX IF NOT EXISTS idx_usages_target "
                "ON usages(target_type, target_name)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_usages_class_name "
                "ON usages(target_class, target_name)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_code_content_file "
                "ON code_content(file_id)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_code_content_entity "
                "ON code_content(entity_type, entity_id)"
            ),
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
            # Index for finding non-vectorized chunks (where vector_id IS NULL)
            "CREATE INDEX IF NOT EXISTS idx_code_chunks_not_vectorized ON code_chunks(project_id, id) WHERE vector_id IS NULL",
            # Index for deleted files (partial index, only indexes deleted=1)
            "CREATE INDEX IF NOT EXISTS idx_files_deleted ON files(deleted) WHERE deleted = 1",
        ]

        for index_sql in indexes:
            cursor.execute(index_sql)

        self.conn.commit()

    def _migrate_to_uuid_projects(self) -> None:
        """Migrate projects table from INTEGER to UUID4 if needed."""
        cursor = self.conn.cursor()

        # Check if migration is needed
        cursor.execute("PRAGMA table_info(projects)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        # If id is INTEGER, we need to migrate
        if "id" in columns and columns["id"] == "INTEGER":
            logger.info("Migrating projects table to UUID4...")

            # Create new projects table with UUID
            cursor.execute(
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

            # Copy data with UUID generation
            cursor.execute(
                "SELECT id, root_path, name, created_at, updated_at FROM projects"
            )
            old_projects = cursor.fetchall()

            for old_id, root_path, name, created_at, updated_at in old_projects:
                new_id = str(uuid.uuid4())
                cursor.execute(
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

                # Update all foreign key references
                cursor.execute(
                    "UPDATE files SET project_id = ? WHERE project_id = ?",
                    (new_id, old_id),
                )

            # Drop old table and rename new one
            cursor.execute("DROP TABLE projects")
            cursor.execute("ALTER TABLE projects_new RENAME TO projects")

            # Recreate foreign key constraints
            cursor.execute("PRAGMA foreign_keys = OFF")
            cursor.execute(
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
            cursor.execute(
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
            cursor.execute("DROP TABLE files")
            cursor.execute("ALTER TABLE files_new RENAME TO files")
            cursor.execute("PRAGMA foreign_keys = ON")

            self.conn.commit()
            logger.info("Migration to UUID4 completed")

        # Add comment column if it doesn't exist
        if "comment" not in columns:
            try:
                cursor.execute("ALTER TABLE projects ADD COLUMN comment TEXT")
                self.conn.commit()
            except sqlite3.OperationalError:
                # Column might already exist in some cases
                pass

    def _migrate_schema(self) -> None:
        """
        Migrate database schema - add missing columns, update structure.

        This method is called on every database initialization to ensure
        the schema is up to date with the latest version.
        """
        cursor = self.conn.cursor()

        # Check and migrate issues table - add project_id if missing
        cursor.execute("PRAGMA table_info(issues)")
        issues_columns = {row[1]: row[2] for row in cursor.fetchall()}
        if "project_id" not in issues_columns:
            try:
                logger.info("Migrating issues table: adding project_id column")
                cursor.execute("ALTER TABLE issues ADD COLUMN project_id TEXT")

                # Update existing issues with project_id from files
                cursor.execute(
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

                # Add foreign key constraint if possible
                # Note: SQLite doesn't support adding FK constraints to existing tables
                # They are only enforced on new inserts

                self.conn.commit()
                logger.info("Migration completed: issues table now has project_id")
            except sqlite3.OperationalError as e:
                logger.warning(f"Migration issue (may already exist): {e}")

        # Add index for project_id in issues if it doesn't exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_issues_project'"
        )
        if not cursor.fetchone():
            try:
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_issues_project ON issues(project_id)"
                )
                self.conn.commit()
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not create index idx_issues_project: {e}")

        # Migrate code_chunks table - add context binding columns if missing
        cursor.execute("PRAGMA table_info(code_chunks)")
        chunks_columns = {row[1]: row[2] for row in cursor.fetchall()}

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
                    cursor.execute(
                        f"ALTER TABLE code_chunks ADD COLUMN {col_name} {col_type}"
                    )
                    self.conn.commit()
                except sqlite3.OperationalError as e:
                    logger.warning(
                        f"Could not add column {col_name} to code_chunks: {e}"
                    )
        
        # Migration: Add deleted, original_path, version_dir columns to files table if they don't exist
        cursor.execute("PRAGMA table_info(files)")
        files_columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        if "deleted" not in files_columns:
            try:
                logger.info("Migrating files table: adding deleted column")
                cursor.execute("ALTER TABLE files ADD COLUMN deleted BOOLEAN DEFAULT 0")
                self.conn.commit()
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not add deleted column to files: {e}")
        
        if "original_path" not in files_columns:
            try:
                logger.info("Migrating files table: adding original_path column")
                cursor.execute("ALTER TABLE files ADD COLUMN original_path TEXT")
                self.conn.commit()
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not add original_path column to files: {e}")
        
        if "version_dir" not in files_columns:
            try:
                logger.info("Migrating files table: adding version_dir column")
                cursor.execute("ALTER TABLE files ADD COLUMN version_dir TEXT")
                self.conn.commit()
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not add version_dir column to files: {e}")
        
        # Create index after adding deleted column
        try:
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_files_deleted 
                ON files(deleted) WHERE deleted = 1
                """
            )
            self.conn.commit()
            logger.info("Created index idx_files_deleted")
        except sqlite3.OperationalError as e:
            logger.warning(f"Could not create index idx_files_deleted: {e}")

    def get_or_create_project(
        self, root_path: str, name: Optional[str] = None, comment: Optional[str] = None
    ) -> str:
        """
        Get or create project by root path.

        Args:
            root_path: Root directory path of the project
            name: Optional project name
            comment: Optional human-readable comment/identifier

        Returns:
            Project ID (UUID4 string)
        """
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()

            # Try to get existing project
            cursor.execute("SELECT id FROM projects WHERE root_path = ?", (root_path,))
            row = cursor.fetchone()
            if row:
                return row[0]

            # Create new project with UUID4
            project_id = str(uuid.uuid4())
            project_name = name or Path(root_path).name
            cursor.execute(
                """
                INSERT INTO projects (id, root_path, name, comment, updated_at)
                VALUES (?, ?, ?, ?, julianday('now'))
            """,
                (project_id, root_path, project_name, comment),
            )
            self.conn.commit()
            return project_id

    def get_project_id(self, root_path: str) -> Optional[str]:
        """
        Get project ID by root path.

        Args:
            root_path: Root directory path of the project

        Returns:
            Project ID (UUID4 string) or None if not found
        """
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE root_path = ?", (root_path,))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Get project by ID.

        Args:
            project_id: Project ID (UUID4 string)

        Returns:
            Project record as dictionary or None if not found
        """
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_file_by_path(self, path: str, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Get file record by path and project ID.

        Args:
            path: File path
            project_id: Project ID

        Returns:
            File record as dictionary or None if not found
        """
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM files WHERE path = ? AND project_id = ?",
            (path, project_id),
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def add_file(
        self,
        path: str,
        lines: int,
        last_modified: float,
        has_docstring: bool,
        project_id: str,
    ) -> int:
        """Add or update file record. Returns file_id."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO files
            (project_id, path, lines, last_modified, has_docstring, updated_at)
            VALUES (?, ?, ?, ?, ?, julianday('now'))
        """,
            (project_id, path, lines, last_modified, has_docstring),
        )
        self.conn.commit()
        result = cursor.lastrowid
        assert result is not None
        return result

    def get_file_id(self, path: str, project_id: str) -> Optional[int]:
        """Get file ID by path and project."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id FROM files WHERE path = ? AND project_id = ?", (path, project_id)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def get_file_by_id(self, file_id: int) -> Optional[Dict[str, Any]]:
        """Get file record by ID."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def delete_file(self, file_id: int) -> None:
        """Delete file and all related records (cascade)."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
        self.conn.commit()

    def add_class(
        self,
        file_id: int,
        name: str,
        line: int,
        docstring: Optional[str],
        bases: List[str],
    ) -> int:
        """Add class record. Returns class_id."""
        cursor = self.conn.cursor()
        bases_json = json.dumps(bases) if bases else None
        cursor.execute(
            """
            INSERT OR REPLACE INTO classes (file_id, name, line, docstring, bases)
            VALUES (?, ?, ?, ?, ?)
        """,
            (file_id, name, line, docstring, bases_json),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_class_id(self, file_id: int, name: str, line: int) -> Optional[int]:
        """Get class ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id FROM classes WHERE file_id = ? AND name = ? AND line = ?",
            (file_id, name, line),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def add_method(
        self,
        class_id: int,
        name: str,
        line: int,
        args: List[str],
        docstring: Optional[str],
        is_abstract: bool = False,
        has_pass: bool = False,
        has_not_implemented: bool = False,
    ) -> int:
        """Add method record. Returns method_id."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        args_json = json.dumps(args) if args else None
        cursor.execute(
            """
            INSERT OR REPLACE INTO methods
            (class_id, name, line, args, docstring, is_abstract,
             has_pass, has_not_implemented)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                class_id,
                name,
                line,
                args_json,
                docstring,
                is_abstract,
                has_pass,
                has_not_implemented,
            ),
        )
        self.conn.commit()
        result = cursor.lastrowid
        assert result is not None
        return result

    def add_function(
        self,
        file_id: int,
        name: str,
        line: int,
        args: List[str],
        docstring: Optional[str],
    ) -> int:
        """Add function record. Returns function_id."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        args_json = json.dumps(args) if args else None
        cursor.execute(
            """
            INSERT OR REPLACE INTO functions (file_id, name, line, args, docstring)
            VALUES (?, ?, ?, ?, ?)
        """,
            (file_id, name, line, args_json, docstring),
        )
        self.conn.commit()
        result = cursor.lastrowid
        assert result is not None
        return result

    def add_import(
        self,
        file_id: int,
        name: str,
        module: Optional[str],
        import_type: str,
        line: int,
    ) -> int:
        """Add import record. Returns import_id."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO imports (file_id, name, module, import_type, line)
            VALUES (?, ?, ?, ?, ?)
        """,
            (file_id, name, module, import_type, line),
        )
        self.conn.commit()
        result = cursor.lastrowid
        assert result is not None
        return result

    def add_issue(
        self,
        issue_type: str,
        description: str,
        line: Optional[int] = None,
        file_id: Optional[int] = None,
        class_id: Optional[int] = None,
        function_id: Optional[int] = None,
        method_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
    ) -> int:
        """
        Add issue record. Returns issue_id.

        If project_id is not provided, it will be retrieved from file_id.
        """
        assert self.conn is not None
        cursor = self.conn.cursor()

        # Get project_id from file_id if not provided
        if project_id is None and file_id is not None:
            cursor.execute("SELECT project_id FROM files WHERE id = ?", (file_id,))
            result = cursor.fetchone()
            if result:
                project_id = result[0]

        metadata_json = json.dumps(metadata) if metadata else None
        cursor.execute(
            """
            INSERT INTO issues
            (file_id, project_id, class_id, function_id, method_id, issue_type,
             line, description, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                file_id,
                project_id,
                class_id,
                function_id,
                method_id,
                issue_type,
                line,
                description,
                metadata_json,
            ),
        )
        self.conn.commit()
        result = cursor.lastrowid
        assert result is not None
        return result

    def clear_file_data(self, file_id: int) -> None:
        """
        Clear all data for a file.

        Removes all related data including:
        - classes and their methods
        - functions
        - imports
        - issues
        - usages
        - dependencies (both as source and target)
        - code_content and FTS index
        - AST trees
        - code chunks
        - vector index entries

        NOTE: When FAISS is implemented, this method should:
        1. Get all vector_ids from code_chunks for this file_id
        2. Remove these vectors from FAISS index
        3. Then delete from database
        This ensures FAISS stays in sync when files are updated.
        """
        assert self.conn is not None
        cursor = self.conn.cursor()
        # Get class IDs first
        cursor.execute("SELECT id FROM classes WHERE file_id = ?", (file_id,))
        class_ids = [row[0] for row in cursor.fetchall()]

        # Get content IDs for FTS cleanup
        cursor.execute("SELECT id FROM code_content WHERE file_id = ?", (file_id,))
        content_ids = [row[0] for row in cursor.fetchall()]

        # Delete from FTS index
        if content_ids:
            placeholders = ",".join("?" * len(content_ids))
            cursor.execute(
                f"DELETE FROM code_content_fts WHERE rowid IN ({placeholders})",
                content_ids,
            )

        # Delete methods for these classes
        if class_ids:
            placeholders = ",".join("?" * len(class_ids))
            cursor.execute(
                f"DELETE FROM methods WHERE class_id IN ({placeholders})", class_ids
            )

        # Delete classes
        cursor.execute("DELETE FROM classes WHERE file_id = ?", (file_id,))

        # Delete functions
        cursor.execute("DELETE FROM functions WHERE file_id = ?", (file_id,))

        # Delete imports
        cursor.execute("DELETE FROM imports WHERE file_id = ?", (file_id,))

        # Delete issues
        cursor.execute("DELETE FROM issues WHERE file_id = ?", (file_id,))

        # Delete usages
        cursor.execute("DELETE FROM usages WHERE file_id = ?", (file_id,))

        # Delete dependencies (both as source and target)
        cursor.execute(
            "DELETE FROM dependencies WHERE source_file_id = ? OR target_file_id = ?",
            (file_id, file_id),
        )

        # Delete code content
        cursor.execute("DELETE FROM code_content WHERE file_id = ?", (file_id,))

        # Delete AST trees
        cursor.execute("DELETE FROM ast_trees WHERE file_id = ?", (file_id,))

        # Delete code chunks
        # Get vector_ids before deletion to remove from FAISS index
        cursor.execute(
            "SELECT vector_id FROM code_chunks WHERE file_id = ? AND vector_id IS NOT NULL",
            (file_id,),
        )
        [row[0] for row in cursor.fetchall()]

        # Delete chunks from database
        cursor.execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))

        # NOTE: vector_ids are collected but not removed from FAISS here
        # FAISS doesn't support direct removal. Vectors will be cleaned up
        # on next rebuild_from_database call (on server restart).
        # This is acceptable as per requirements - garbage is OK until restart.

        # Delete vector index entries (need to get entity IDs first)
        cursor.execute(
            """
            SELECT id FROM classes WHERE file_id = ?
            UNION
            SELECT id FROM functions WHERE file_id = ?
        """,
            (file_id, file_id),
        )
        entity_ids = [row[0] for row in cursor.fetchall()]

        # Delete vector index for file itself
        cursor.execute(
            "DELETE FROM vector_index WHERE entity_type = 'file' AND entity_id = ?",
            (file_id,),
        )

        # Delete vector index for classes and functions
        if entity_ids:
            placeholders = ",".join("?" * len(entity_ids))
            cursor.execute(
                f"""
                DELETE FROM vector_index
                WHERE entity_type IN ('class', 'function', 'method')
                AND entity_id IN ({placeholders})
            """,
                entity_ids,
            )

        self.conn.commit()

    async def clear_project_data(self, project_id: str) -> None:
        """
        Clear all data for a project and remove the project itself.

        Removes all files, classes, functions, imports, issues, usages,
        dependencies, code_content, ast_trees, code_chunks, vector_index entries,
        and the project record itself from the database.

        Args:
            project_id: Project ID (UUID4 string)
        """
        assert self.conn is not None
        cursor = self.conn.cursor()

        # Get all file IDs for this project
        cursor.execute("SELECT id FROM files WHERE project_id = ?", (project_id,))
        file_ids = [row[0] for row in cursor.fetchall()]

        if not file_ids:
            # No files to clean, but still clean project-level data
            cursor.execute(
                "DELETE FROM vector_index WHERE project_id = ?", (project_id,)
            )
            self.conn.commit()
            return

        # Get class IDs for these files
        placeholders = ",".join("?" * len(file_ids))
        cursor.execute(
            f"SELECT id FROM classes WHERE file_id IN ({placeholders})", file_ids
        )
        class_ids = [row[0] for row in cursor.fetchall()]

        # Get content IDs for FTS cleanup
        cursor.execute(
            f"SELECT id FROM code_content WHERE file_id IN ({placeholders})", file_ids
        )
        content_ids = [row[0] for row in cursor.fetchall()]

        # Delete from FTS index
        if content_ids:
            content_placeholders = ",".join("?" * len(content_ids))
            cursor.execute(
                f"DELETE FROM code_content_fts WHERE rowid IN ({content_placeholders})",
                content_ids,
            )

        # Delete methods for these classes
        if class_ids:
            method_placeholders = ",".join("?" * len(class_ids))
            cursor.execute(
                f"DELETE FROM methods WHERE class_id IN ({method_placeholders})",
                class_ids,
            )

        # Delete classes
        if file_ids:
            cursor.execute(
                f"DELETE FROM classes WHERE file_id IN ({placeholders})", file_ids
            )

        # Delete functions
        if file_ids:
            cursor.execute(
                f"DELETE FROM functions WHERE file_id IN ({placeholders})", file_ids
            )

        # Delete imports
        if file_ids:
            cursor.execute(
                f"DELETE FROM imports WHERE file_id IN ({placeholders})", file_ids
            )

        # Delete issues
        if file_ids:
            cursor.execute(
                f"DELETE FROM issues WHERE file_id IN ({placeholders})", file_ids
            )

        # Delete usages
        if file_ids:
            cursor.execute(
                f"DELETE FROM usages WHERE file_id IN ({placeholders})", file_ids
            )

        # Delete dependencies (both as source and target)
        if file_ids:
            cursor.execute(
                f"""
                DELETE FROM dependencies
                WHERE source_file_id IN ({placeholders})
                OR target_file_id IN ({placeholders})
            """,
                file_ids + file_ids,
            )

        # Delete code content
        if file_ids:
            cursor.execute(
                f"DELETE FROM code_content WHERE file_id IN ({placeholders})", file_ids
            )

        # Delete AST trees
        if file_ids:
            cursor.execute(
                f"DELETE FROM ast_trees WHERE file_id IN ({placeholders})", file_ids
            )

        # Delete code chunks
        if file_ids:
            cursor.execute(
                f"DELETE FROM code_chunks WHERE file_id IN ({placeholders})", file_ids
            )

        # Delete vector index entries for this project
        cursor.execute("DELETE FROM vector_index WHERE project_id = ?", (project_id,))

        # Delete files
        cursor.execute("DELETE FROM files WHERE project_id = ?", (project_id,))

        # Delete the project itself
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))

        self.conn.commit()
        logger.info(f"Cleared all data and removed project {project_id}")

    def get_project_files(self, project_id: str) -> List[Dict[str, Any]]:
        """
        Get all files for a project.

        Args:
            project_id: Project ID (UUID4 string)

        Returns:
            List of file records as dictionaries
        """
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, path, lines, last_modified, has_docstring FROM files WHERE project_id = ?",
            (project_id,),
        )
        rows = cursor.fetchall()
        # Convert rows to dictionaries manually
        result = []
        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "path": row[1],
                    "lines": row[2],
                    "last_modified": row[3],
                    "has_docstring": row[4],
                }
            )
        return result

    async def remove_missing_files(
        self, project_id: str, root_path: Path
    ) -> Dict[str, Any]:
        """
        Remove files from database that no longer exist on disk.

        Args:
            project_id: Project ID (UUID4 string)
            root_path: Root directory path of the project

        Returns:
            Dictionary with removal statistics:
            - removed_count: Number of files removed
            - removed_files: List of removed file paths
        """
        assert self.conn is not None
        cursor = self.conn.cursor()

        # Get all files for this project
        files = self.get_project_files(project_id)
        removed_files = []
        removed_count = 0

        for file_record in files:
            file_path = Path(file_record["path"])

            # Check if file exists on disk
            if not file_path.exists():
                file_id = file_record["id"]
                logger.info(
                    f"File not found on disk, removing from database: {file_path}"
                )

                # Use clear_file_data to remove all related data
                self.clear_file_data(file_id)

                # Delete the file record itself
                cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))

                removed_files.append(str(file_path))
                removed_count += 1

        if removed_count > 0:
            self.conn.commit()
            logger.info(
                f"Removed {removed_count} missing files from database for project {project_id}"
            )

        return {
            "removed_count": removed_count,
            "removed_files": removed_files,
        }

    def search_classes(
        self, name_pattern: Optional[str] = None, project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search classes by name pattern."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        if name_pattern:
            if project_id:
                cursor.execute(
                    """
                    SELECT c.*, f.path as file_path
                    FROM classes c
                    JOIN files f ON c.file_id = f.id
                    WHERE c.name LIKE ? AND f.project_id = ?
                    ORDER BY c.name, c.line
                """,
                    (f"%{name_pattern}%", project_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT c.*, f.path as file_path
                    FROM classes c
                    JOIN files f ON c.file_id = f.id
                    WHERE c.name LIKE ?
                    ORDER BY c.name, c.line
                """,
                    (f"%{name_pattern}%",),
                )
        else:
            if project_id:
                cursor.execute(
                    """
                    SELECT c.*, f.path as file_path
                    FROM classes c
                    JOIN files f ON c.file_id = f.id
                    WHERE f.project_id = ?
                    ORDER BY c.name, c.line
                """,
                    (project_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT c.*, f.path as file_path
                    FROM classes c
                    JOIN files f ON c.file_id = f.id
                    ORDER BY c.name, c.line
                """
                )
        return [dict(row) for row in cursor.fetchall()]

    def search_functions(
        self, name_pattern: Optional[str] = None, project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search functions by name pattern.

        Args:
            name_pattern: Name pattern to search (optional)
            project_id: Project ID to filter by (optional)

        Returns:
            List of function records
        """
        assert self.conn is not None
        cursor = self.conn.cursor()
        if name_pattern:
            if project_id:
                cursor.execute(
                    """
                    SELECT func.*, f.path as file_path
                    FROM functions func
                    JOIN files f ON func.file_id = f.id
                    WHERE func.name LIKE ? AND f.project_id = ?
                    ORDER BY func.name, func.line
                """,
                    (f"%{name_pattern}%", project_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT func.*, f.path as file_path
                    FROM functions func
                    JOIN files f ON func.file_id = f.id
                    WHERE func.name LIKE ?
                    ORDER BY func.name, func.line
                """,
                    (f"%{name_pattern}%",),
                )
        else:
            if project_id:
                cursor.execute(
                    """
                    SELECT func.*, f.path as file_path
                    FROM functions func
                    JOIN files f ON func.file_id = f.id
                    WHERE f.project_id = ?
                    ORDER BY func.name, func.line
                """,
                    (project_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT func.*, f.path as file_path
                    FROM functions func
                    JOIN files f ON func.file_id = f.id
                    ORDER BY func.name, func.line
                """
                )
        return [dict(row) for row in cursor.fetchall()]

    def search_methods(
        self, name_pattern: Optional[str] = None, project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search methods by name pattern."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        if name_pattern:
            if project_id:
                cursor.execute(
                    """
                    SELECT m.*, c.name as class_name, f.path as file_path
                    FROM methods m
                    JOIN classes c ON m.class_id = c.id
                    JOIN files f ON c.file_id = f.id
                    WHERE m.name LIKE ? AND f.project_id = ?
                    ORDER BY c.name, m.name, m.line
                """,
                    (f"%{name_pattern}%", project_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT m.*, c.name as class_name, f.path as file_path
                    FROM methods m
                    JOIN classes c ON m.class_id = c.id
                    JOIN files f ON c.file_id = f.id
                    WHERE m.name LIKE ?
                    ORDER BY c.name, m.name, m.line
                """,
                    (f"%{name_pattern}%",),
                )
        else:
            if project_id:
                cursor.execute(
                    """
                    SELECT m.*, c.name as class_name, f.path as file_path
                    FROM methods m
                    JOIN classes c ON m.class_id = c.id
                    JOIN files f ON c.file_id = f.id
                    WHERE f.project_id = ?
                    ORDER BY c.name, m.name, m.line
                """,
                    (project_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT m.*, c.name as class_name, f.path as file_path
                    FROM methods m
                    JOIN classes c ON m.class_id = c.id
                    JOIN files f ON c.file_id = f.id
                    ORDER BY c.name, m.name, m.line
                """
                )
        return [dict(row) for row in cursor.fetchall()]

    def get_issues_by_type(
        self, issue_type: str, project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all issues of a specific type."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        if project_id:
            cursor.execute(
                """
                SELECT i.*, f.path as file_path
                FROM issues i
                LEFT JOIN files f ON i.file_id = f.id
                WHERE i.issue_type = ? AND (f.project_id = ? OR f.project_id IS NULL)
                ORDER BY f.path, i.line
            """,
                (issue_type, project_id),
            )
        else:
            cursor.execute(
                """
                SELECT i.*, f.path as file_path
                FROM issues i
                LEFT JOIN files f ON i.file_id = f.id
                WHERE i.issue_type = ?
                ORDER BY f.path, i.line
            """,
                (issue_type,),
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_file_summary(
        self, file_path: str, project_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get summary for a file."""
        file_id = self.get_file_id(file_path, project_id)
        if not file_id:
            return None

        assert self.conn is not None
        cursor = self.conn.cursor()

        # Get file info
        cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        file_info = dict(cursor.fetchone())

        # Count classes
        cursor.execute("SELECT COUNT(*) FROM classes WHERE file_id = ?", (file_id,))
        file_info["class_count"] = cursor.fetchone()[0]

        # Count functions
        cursor.execute("SELECT COUNT(*) FROM functions WHERE file_id = ?", (file_id,))
        file_info["function_count"] = cursor.fetchone()[0]

        # Count issues
        cursor.execute("SELECT COUNT(*) FROM issues WHERE file_id = ?", (file_id,))
        file_info["issue_count"] = cursor.fetchone()[0]

        return file_info

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall statistics."""
        assert self.conn is not None
        cursor = self.conn.cursor()

        stats = {}

        cursor.execute("SELECT COUNT(*) FROM files")
        stats["total_files"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM classes")
        stats["total_classes"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM functions")
        stats["total_functions"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM methods")
        stats["total_methods"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM issues")
        stats["total_issues"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT issue_type) FROM issues")
        stats["issue_types"] = cursor.fetchone()[0]

        # Count issues by type
        cursor.execute(
            """
            SELECT issue_type, COUNT(*) as count
            FROM issues
            GROUP BY issue_type
            ORDER BY count DESC
        """
        )
        stats["issues_by_type"] = {row[0]: row[1] for row in cursor.fetchall()}

        return stats

    def add_usage(
        self,
        file_id: int,
        line: int,
        usage_type: str,
        target_type: str,
        target_name: str,
        target_class: Optional[str] = None,
        context: Optional[str] = None,
    ) -> int:
        """
        Add usage record.

        Args:
            file_id: File ID where usage occurs
            line: Line number
            usage_type: Type of usage (method_call, attribute_access, etc.)
            target_type: Type of target (method, property, class, etc.)
            target_name: Name of target
            target_class: Class name if target is a method/property
            context: Additional context

        Returns:
            Usage ID
        """
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO usages
            (file_id, line, usage_type, target_type, target_class, target_name, context)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                file_id,
                line,
                usage_type,
                target_type,
                target_class,
                target_name,
                context,
            ),
        )
        self.conn.commit()
        result = cursor.lastrowid
        assert result is not None
        return result

    def find_usages(
        self,
        target_name: str,
        project_id: str,
        target_type: Optional[str] = None,
        target_class: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find all usages of a method or property.

        Args:
            target_name: Name of method/property to find
            project_id: Project ID to filter by
            target_type: Type filter (method, property, etc.)
            target_class: Class name filter

        Returns:
            List of usage records with file paths
        """
        assert self.conn is not None
        cursor = self.conn.cursor()

        query = """
            SELECT u.*, f.path as file_path
            FROM usages u
            JOIN files f ON u.file_id = f.id
            WHERE u.target_name = ? AND f.project_id = ?
        """
        params = [target_name, project_id]

        if target_type:
            query += " AND u.target_type = ?"
            params.append(target_type)

        if target_class:
            query += " AND u.target_class = ?"
            params.append(target_class)

        query += " ORDER BY f.path, u.line"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def add_code_content(
        self,
        file_id: int,
        entity_type: str,
        entity_name: str,
        content: str,
        docstring: Optional[str] = None,
        entity_id: Optional[int] = None,
    ) -> int:
        """
        Add code content for full-text search.

        Args:
            file_id: File ID
            entity_type: Type (class, method, function)
            entity_name: Name of entity
            content: Code content
            docstring: Docstring if available
            entity_id: ID of related entity (class_id, method_id, etc.)

        Returns:
            Content ID
        """
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO code_content
            (file_id, entity_type, entity_id, entity_name, content, docstring)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (file_id, entity_type, entity_id, entity_name, content, docstring),
        )
        self.conn.commit()
        content_id = cursor.lastrowid
        assert content_id is not None

        # Update FTS index
        cursor.execute(
            """
            INSERT INTO code_content_fts
            (rowid, entity_type, entity_name, content, docstring)
            VALUES (?, ?, ?, ?, ?)
        """,
            (content_id, entity_type, entity_name, content, docstring or ""),
        )
        self.conn.commit()

        return content_id

    def full_text_search(
        self,
        query: str,
        project_id: str,
        entity_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Perform full-text search in code content.

        Args:
            query: Search query
            project_id: Project ID to filter by
            entity_type: Filter by entity type
            limit: Maximum results

        Returns:
            List of matching records with file paths
        """
        assert self.conn is not None
        cursor = self.conn.cursor()

        fts_query = """
            SELECT c.*, f.path as file_path
            FROM code_content_fts fts
            JOIN code_content c ON fts.rowid = c.id
            JOIN files f ON c.file_id = f.id
            WHERE code_content_fts MATCH ? AND f.project_id = ?
        """
        params = [query, project_id]

        if entity_type:
            fts_query += " AND c.entity_type = ?"
            params.append(entity_type)

        fts_query += " ORDER BY rank LIMIT ?"
        params.append(limit)

        cursor.execute(fts_query, params)
        return [dict(row) for row in cursor.fetchall()]

    def is_ast_outdated(self, file_id: int, file_mtime: float) -> bool:
        """
        Check if AST tree is outdated compared to file modification time.

        Args:
            file_id: File ID
            file_mtime: File modification time

        Returns:
            True if AST is outdated or doesn't exist, False otherwise
        """
        assert self.conn is not None
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT file_mtime FROM ast_trees
            WHERE file_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
        """,
            (file_id,),
        )
        row = cursor.fetchone()

        if not row:
            # AST doesn't exist
            return True

        db_mtime = row[0]
        # Consider outdated if file is newer than stored AST
        return file_mtime > db_mtime

    async def save_ast_tree(
        self,
        file_id: int,
        project_id: str,
        ast_json: str,
        ast_hash: str,
        file_mtime: float,
        overwrite: bool = False,
    ) -> int:
        """
        Save AST tree for a file.

        Args:
            file_id: File ID
            project_id: Project ID
            ast_json: Serialized AST as JSON string
            ast_hash: Hash of AST for change detection
            file_mtime: File modification time
            overwrite: If True, delete all old AST trees for this file before saving

        Returns:
            AST tree ID
        """
        assert self.conn is not None
        cursor = self.conn.cursor()

        if overwrite:
            # Delete all existing AST trees for this file
            cursor.execute(
                """
                DELETE FROM ast_trees
                WHERE file_id = ?
            """,
                (file_id,),
            )

        # Check if AST already exists with same hash (if not overwriting)
        if not overwrite:
            cursor.execute(
                """
                SELECT id FROM ast_trees
                WHERE file_id = ? AND ast_hash = ?
            """,
                (file_id, ast_hash),
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing record with new mtime
                cursor.execute(
                    """
                    UPDATE ast_trees
                    SET ast_json = ?, file_mtime = ?, updated_at = julianday('now')
                    WHERE id = ?
                """,
                    (ast_json, file_mtime, existing[0]),
                )
                self.conn.commit()
                return existing[0]

        # Insert new record
        cursor.execute(
            """
            INSERT INTO ast_trees
            (file_id, project_id, ast_json, ast_hash, file_mtime)
            VALUES (?, ?, ?, ?, ?)
        """,
            (file_id, project_id, ast_json, ast_hash, file_mtime),
        )
        self.conn.commit()
        result = cursor.lastrowid
        assert result is not None
        return result

    async def overwrite_ast_tree(
        self,
        file_id: int,
        project_id: str,
        ast_json: str,
        ast_hash: str,
        file_mtime: float,
    ) -> int:
        """
        Overwrite AST tree for a file (delete old, insert new).

        Args:
            file_id: File ID
            project_id: Project ID
            ast_json: Serialized AST as JSON string
            ast_hash: Hash of AST for change detection
            file_mtime: File modification time

        Returns:
            AST tree ID
        """
        return await self.save_ast_tree(
            file_id, project_id, ast_json, ast_hash, file_mtime, overwrite=True
        )

    async def get_ast_tree(self, file_id: int) -> Optional[Dict[str, Any]]:
        """
        Get AST tree for a file.

        Args:
            file_id: File ID

        Returns:
            AST tree record with JSON or None
        """
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, file_id, project_id, ast_json, ast_hash, file_mtime, created_at, updated_at
            FROM ast_trees
            WHERE file_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
        """,
            (file_id,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "file_id": row[1],
                "project_id": row[2],
                "ast_json": row[3],
                "ast_hash": row[4],
                "file_mtime": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
        return None

    async def add_vector_index(
        self,
        project_id: str,
        entity_type: str,
        entity_id: int,
        vector_id: int,
        vector_dim: int,
        embedding_model: Optional[str] = None,
    ) -> int:
        """
        Add vector index metadata.

        Args:
            project_id: Project ID
            entity_type: Type of entity (file, class, method, function, chunk)
            entity_id: ID of the entity
            vector_id: FAISS vector index ID
            vector_dim: Vector dimension
            embedding_model: Model used for embedding

        Returns:
            Vector index record ID
        """
        assert self.conn is not None
        cursor = self.conn.cursor()

        # Check if vector index already exists
        cursor.execute(
            """
            SELECT id FROM vector_index
            WHERE project_id = ? AND entity_type = ? AND entity_id = ?
        """,
            (project_id, entity_type, entity_id),
        )
        existing = cursor.fetchone()

        if existing:
            # Update existing record
            cursor.execute(
                """
                UPDATE vector_index
                SET vector_id = ?, vector_dim = ?, embedding_model = ?
                WHERE id = ?
            """,
                (vector_id, vector_dim, embedding_model, existing[0]),
            )
            self.conn.commit()
            return existing[0]
        else:
            # Insert new record
            cursor.execute(
                """
                INSERT INTO vector_index
                (project_id, entity_type, entity_id, vector_id, vector_dim, embedding_model)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    project_id,
                    entity_type,
                    entity_id,
                    vector_id,
                    vector_dim,
                    embedding_model,
                ),
            )
            self.conn.commit()
            result = cursor.lastrowid
            assert result is not None
            return result

    async def get_vector_index(
        self,
        project_id: str,
        entity_type: str,
        entity_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Get vector index metadata.

        Args:
            project_id: Project ID
            entity_type: Type of entity
            entity_id: ID of the entity

        Returns:
            Vector index record or None
        """
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM vector_index
            WHERE project_id = ? AND entity_type = ? AND entity_id = ?
        """,
            (project_id, entity_type, entity_id),
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def add_code_chunk(
        self,
        file_id: int,
        project_id: str,
        chunk_uuid: str,
        chunk_type: str,
        chunk_text: str,
        chunk_ordinal: Optional[int] = None,
        vector_id: Optional[int] = None,
        embedding_model: Optional[str] = None,
        bm25_score: Optional[float] = None,
        embedding_vector: Optional[str] = None,  # JSON array as string
        class_id: Optional[int] = None,
        function_id: Optional[int] = None,
        method_id: Optional[int] = None,
        line: Optional[int] = None,
        ast_node_type: Optional[str] = None,
        source_type: Optional[str] = None,
        binding_level: int = 0,
    ) -> int:
        """
        Add code chunk from semantic chunker with AST node binding.

        Args:
            file_id: File ID
            project_id: Project ID
            chunk_uuid: UUID of the chunk
            chunk_type: Type of chunk (DocBlock, CodeBlock, etc.)
            chunk_text: Chunk text content
            chunk_ordinal: Order of chunk in original text
            vector_id: FAISS vector index ID
            embedding_model: Model used for embedding
            class_id: Class ID if chunk is bound to a class
            function_id: Function ID if chunk is bound to a function
            method_id: Method ID if chunk is bound to a method
            line: Line number in file
            ast_node_type: Type of AST node (ClassDef, FunctionDef, etc.)
            source_type: Source type ('docstring', 'comment', 'file_docstring')

        Returns:
            Chunk ID
        """
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()

            # Check if chunk already exists
            cursor.execute(
                """
                SELECT id FROM code_chunks
                WHERE chunk_uuid = ?
            """,
                (chunk_uuid,),
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing chunk
                cursor.execute(
                    """
                    UPDATE code_chunks
                    SET chunk_text = ?, chunk_type = ?, chunk_ordinal = ?,
                        vector_id = ?, embedding_model = ?,
                        bm25_score = ?, embedding_vector = ?,
                        class_id = ?, function_id = ?, method_id = ?,
                        line = ?, ast_node_type = ?, source_type = ?,
                        binding_level = ?
                    WHERE id = ?
                """,
                    (
                        chunk_text,
                        chunk_type,
                        chunk_ordinal,
                        vector_id,
                        embedding_model,
                        bm25_score,
                        embedding_vector,
                        class_id,
                        function_id,
                        method_id,
                        line,
                        ast_node_type,
                        source_type,
                        binding_level,
                        existing[0],
                    ),
                )
                self.conn.commit()
                return existing[0]
            else:
                # Insert new chunk
                cursor.execute(
                    """
                    INSERT INTO code_chunks
                    (file_id, project_id, chunk_uuid, chunk_type, chunk_text,
                     chunk_ordinal, vector_id, embedding_model, bm25_score, embedding_vector,
                     class_id, function_id, method_id, line, ast_node_type, source_type, binding_level)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        file_id,
                        project_id,
                        chunk_uuid,
                        chunk_type,
                        chunk_text,
                        chunk_ordinal,
                        vector_id,
                        embedding_model,
                        bm25_score,
                        embedding_vector,
                        class_id,
                        function_id,
                        method_id,
                        line,
                        ast_node_type,
                        source_type,
                        binding_level,
                    ),
                )
                self.conn.commit()
                result = cursor.lastrowid
                assert result is not None
                return result

    async def get_code_chunks(
        self,
        file_id: Optional[int] = None,
        project_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get code chunks.

        Args:
            file_id: Filter by file ID (optional)
            project_id: Filter by project ID (optional)
            limit: Maximum results

        Returns:
            List of chunk records
        """
        assert self.conn is not None
        cursor = self.conn.cursor()

        query = "SELECT * FROM code_chunks WHERE 1=1"
        params = []

        if file_id:
            query += " AND file_id = ?"
            params.append(file_id)

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY chunk_ordinal, id LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_all_chunks_for_faiss_rebuild(self) -> List[Dict[str, Any]]:
        """
        Get all code chunks with embeddings for FAISS index rebuild.

        Returns chunks that have vector_id and embedding_model.
        Used on server startup to rebuild FAISS index from database.

        NOTE: This method should be called when FaissIndexManager initializes.
        It will:
        1. Get all chunks with vector_id and embedding_model
        2. For each chunk, get embedding from SVO service (if not cached)
        3. Add to FAISS index with corresponding vector_id

        Returns:
            List of chunk records with vector_id and embedding_model
        """
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()

            cursor.execute(
                """
                SELECT id, file_id, project_id, chunk_uuid, chunk_text,
                       vector_id, embedding_model, chunk_type, embedding_vector
                FROM code_chunks
                WHERE vector_id IS NOT NULL AND embedding_model IS NOT NULL
                ORDER BY id
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    async def get_non_vectorized_chunks(
        self,
        project_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get code chunks that are not yet vectorized (vector_id IS NULL).

        Uses index idx_code_chunks_not_vectorized for fast lookup.

        Args:
            project_id: Filter by project ID (optional)
            limit: Maximum number of chunks to return

        Returns:
            List of chunk records without vector_id
        """
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()

            if project_id:
                cursor.execute(
                    """
                    SELECT id, file_id, project_id, chunk_uuid, chunk_text,
                           chunk_type, chunk_ordinal, embedding_model,
                           class_id, function_id, method_id, line, ast_node_type, source_type
                    FROM code_chunks
                    WHERE vector_id IS NULL AND project_id = ?
                    ORDER BY (embedding_vector IS NOT NULL) DESC, id
                    LIMIT ?
                    """,
                    (project_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, file_id, project_id, chunk_uuid, chunk_text,
                           chunk_type, chunk_ordinal, embedding_model,
                           class_id, function_id, method_id, line, ast_node_type, source_type
                    FROM code_chunks
                    WHERE vector_id IS NULL
                    ORDER BY (embedding_vector IS NOT NULL) DESC, id
                    LIMIT ?
                    """,
                    (limit,),
                )
            return [dict(row) for row in cursor.fetchall()]

    async def update_chunk_vector_id(
        self,
        chunk_id: int,
        vector_id: int,
        embedding_model: Optional[str] = None,
    ) -> None:
        """
        Update vector_id for a chunk after vectorization.

        After this update, the chunk will automatically be excluded from
        the partial index idx_code_chunks_not_vectorized (WHERE vector_id IS NULL).

        Args:
            chunk_id: Chunk ID
            vector_id: FAISS vector index ID
            embedding_model: Optional embedding model name
        """
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()
            if embedding_model:
                cursor.execute(
                    """
                    UPDATE code_chunks
                    SET vector_id = ?, embedding_model = ?
                    WHERE id = ?
                    """,
                    (vector_id, embedding_model, chunk_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE code_chunks
                    SET vector_id = ?
                    WHERE id = ?
                    """,
                    (vector_id, chunk_id),
                )
            self.conn.commit()

    def get_files_needing_chunking(
        self, project_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get files that need chunking (have docstrings but no chunks).

        Files are considered needing chunking if:
        - They have docstrings (has_docstring = 1) OR
        - They have classes/functions/methods with docstrings
        - AND they have no chunks in code_chunks table

        Args:
            project_id: Project ID
            limit: Maximum number of files to return

        Returns:
            List of file records that need chunking
        """
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()

            # Find files with docstrings that have no chunks
            cursor.execute(
                """
                SELECT DISTINCT f.id, f.project_id, f.path, f.has_docstring
                FROM files f
                WHERE f.project_id = ?
                AND (
                    f.has_docstring = 1
                    OR EXISTS (
                        SELECT 1 FROM classes c
                        WHERE c.file_id = f.id AND c.docstring IS NOT NULL AND c.docstring != ''
                    )
                    OR EXISTS (
                        SELECT 1 FROM functions fn
                        WHERE fn.file_id = f.id AND fn.docstring IS NOT NULL AND fn.docstring != ''
                    )
                    OR EXISTS (
                        SELECT 1 FROM methods m
                        JOIN classes c ON m.class_id = c.id
                        WHERE c.file_id = f.id AND m.docstring IS NOT NULL AND m.docstring != ''
                    )
                )
                AND NOT EXISTS (
                    SELECT 1 FROM code_chunks cc
                    WHERE cc.file_id = f.id
                )
                ORDER BY f.updated_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            )

            return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> "CodeDatabase":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
