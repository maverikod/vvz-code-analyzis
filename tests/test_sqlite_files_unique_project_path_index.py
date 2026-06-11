"""
Regression: files table must have UNIQUE(project_id, path) index for ON CONFLICT upserts.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3

import pytest

from code_analysis.core.database.schema_definition_indexes import get_schema_indexes
from code_analysis.core.database.schema_sync_models import IndexDef
from code_analysis.core.database.schema_sync_sql import generate_create_index_sql

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


def test_schema_unique_index_enables_on_conflict_upsert(tmp_path) -> None:
    """Apply idx_files_unique_project_path from schema registry."""
    db_path = tmp_path / "no_unique.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript("""
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
            """)
        conn.commit()

        with pytest.raises(
            sqlite3.OperationalError,
            match="ON CONFLICT clause does not match",
        ):
            conn.execute(
                _PROCESSOR_QUEUE_UPSERT_SQL,
                ("/abs/a.py", 10, 1.0, 0, "proj1"),
            )
        conn.rollback()

        idx_raw = next(
            i
            for i in get_schema_indexes()
            if i["name"] == "idx_files_unique_project_path"
        )
        conn.execute(generate_create_index_sql(IndexDef(**idx_raw)))
        conn.commit()

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
