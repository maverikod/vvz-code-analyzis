"""
Database module for code mapper.

This module provides SQLite database functionality for storing
and querying code analysis data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sqlite3
import json
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

        # Files table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                lines INTEGER,
                last_modified REAL,
                has_docstring BOOLEAN,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now'))
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

        # Create indexes
        indexes = [
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
        ]

        for index_sql in indexes:
            cursor.execute(index_sql)

        self.conn.commit()

    def add_file(
        self, path: str, lines: int, last_modified: float, has_docstring: bool
    ) -> int:
        """Add or update file record. Returns file_id."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO files
            (path, lines, last_modified, has_docstring, updated_at)
            VALUES (?, ?, ?, ?, julianday('now'))
        """,
            (path, lines, last_modified, has_docstring),
        )
        self.conn.commit()
        result = cursor.lastrowid
        assert result is not None
        return result

    def get_file_id(self, path: str) -> Optional[int]:
        """Get file ID by path."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM files WHERE path = ?", (path,))
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
        """Clear all data for a file (classes, functions, imports, issues)."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        # Get class IDs first
        cursor.execute("SELECT id FROM classes WHERE file_id = ?", (file_id,))
        class_ids = [row[0] for row in cursor.fetchall()]

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

        self.conn.commit()

    def search_classes(
        self, name_pattern: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search classes by name pattern."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        if name_pattern:
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
        self, name_pattern: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search functions by name pattern."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        if name_pattern:
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
        self, name_pattern: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search methods by name pattern."""
        assert self.conn is not None
        cursor = self.conn.cursor()
        if name_pattern:
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

    def get_issues_by_type(self, issue_type: str) -> List[Dict[str, Any]]:
        """Get all issues of a specific type."""
        assert self.conn is not None
        cursor = self.conn.cursor()
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

    def get_file_summary(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get summary for a file."""
        file_id = self.get_file_id(file_path)
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
