"""
Database module for code mapper.

This module provides SQLite database functionality for storing
and querying code analysis data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sqlite3
import json
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class CodeDatabase:
    """SQLite database for code analysis data."""

    def __init__(self, db_path: Path) -> None:
        """Initialize database connection and create schema."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: sqlite3.Connection
        self._connect()
        self._create_schema()

    def _connect(self) -> None:
        """Establish database connection."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")

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
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, path)
            )
        """
        )

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
                class_id INTEGER,
                function_id INTEGER,
                method_id INTEGER,
                issue_type TEXT NOT NULL,
                line INTEGER,
                description TEXT,
                metadata TEXT,
                created_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
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
        ]

        for index_sql in indexes:
            cursor.execute(index_sql)

        self.conn.commit()

        # Migrate existing database if needed
        self._migrate_to_uuid_projects()

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
                    INSERT INTO projects_new (id, root_path, name, comment, created_at, updated_at)
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
            cursor.execute("INSERT INTO files_new SELECT * FROM files")
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
    ) -> int:
        """Add issue record. Returns issue_id."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        metadata_json = json.dumps(metadata) if metadata else None
        cursor.execute(
            """
            INSERT INTO issues
            (file_id, class_id, function_id, method_id, issue_type,
             line, description, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                file_id,
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
        """Clear all data for a file (classes, functions, imports, issues, usages, code_content)."""
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

        # Delete code content
        cursor.execute("DELETE FROM code_content WHERE file_id = ?", (file_id,))

        self.conn.commit()

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
