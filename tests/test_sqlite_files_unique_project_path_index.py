"""
Regression: legacy files tables without UNIQUE(project_id, path) must gain a unique
index so processor_queue file-delta upserts (ON CONFLICT) succeed.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3

import pytest

from code_analysis.core.database_driver_pkg.drivers.sqlite_migrations import (
    ensure_files_table_migrations,
)
from code_analysis.core.database_driver_pkg.drivers.sqlite_schema import (
    SQLiteSchemaManager,
)

# Same shape as ProcessorQueueOps._queue_project_delta batch upsert.
_PROCESSOR_QUEUE_UPSERT_SQL = (
    "INSERT INTO files "
    "(path, lines, last_modified, has_docstring, project_id, created_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, julianday('now'), julianday('now')) "
    "ON CONFLICT(project_id, path) DO UPDATE SET "
    "lines = excluded.lines, "
    "last_modified = excluded.last_modified, "
    "has_docstring = excluded.has_docstring, "
    "deleted = 0, "
    "updated_at = julianday('now')"
)


def test_ensure_files_migration_adds_unique_index_for_on_conflict_upsert(
    tmp_path,
) -> None:
    """Without UNIQUE(project_id, path), SQLite rejects ON CONFLICT(project_id, path)."""
    db_path = tmp_path / "legacy_no_unique.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                root_path TEXT NOT NULL,
                name TEXT,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now'))
            );
            INSERT INTO projects(id, root_path) VALUES ('proj1', '/r');
            CREATE TABLE files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                path TEXT NOT NULL,
                lines INTEGER,
                last_modified REAL,
                has_docstring INTEGER,
                deleted INTEGER DEFAULT 0,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );
            """
        )
        conn.commit()

        cur = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='files'"
        )
        row = cur.fetchone()
        assert row is not None
        assert "UNIQUE" not in (row[0] or "").upper()

        with pytest.raises(
            sqlite3.OperationalError,
            match="ON CONFLICT clause does not match",
        ):
            conn.execute(
                _PROCESSOR_QUEUE_UPSERT_SQL,
                ("/abs/a.py", 10, 1.0, 0, "proj1"),
            )
        conn.rollback()

        sm = SQLiteSchemaManager(conn)
        ensure_files_table_migrations(conn, sm)

        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_files_unique_project_path'"
        ).fetchone()
        assert idx is not None

        conn.execute(
            _PROCESSOR_QUEUE_UPSERT_SQL,
            ("/abs/a.py", 10, 1.0, 0, "proj1"),
        )
        conn.execute(
            _PROCESSOR_QUEUE_UPSERT_SQL,
            ("/abs/a.py", 11, 2.0, 1, "proj1"),
        )
        conn.commit()

        row = conn.execute(
            "SELECT lines, last_modified, has_docstring, deleted FROM files "
            "WHERE project_id = ? AND path = ?",
            ("proj1", "/abs/a.py"),
        ).fetchone()
        assert row is not None
        assert row["lines"] == 11
        assert row["has_docstring"] == 1
        assert row["deleted"] == 0
    finally:
        conn.close()
