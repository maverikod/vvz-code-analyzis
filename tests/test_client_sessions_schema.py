"""
Client session table migration: ensure_client_session_tables on SQLite.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from code_analysis.core.client_sessions import ensure_client_session_tables

_CLIENT_SESSION_TABLES = (
    "client_sessions",
    "session_file_locks",
    "roles",
    "role_permissions",
    "session_roles",
)


def _stub_fk_parents(conn: sqlite3.Connection) -> None:
    """Return stub fk parents."""
    conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY)")
    conn.execute(
        "CREATE TABLE files (id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id))"
    )
    conn.commit()


def test_ensure_client_session_tables_falsy_conn_returns_immediately() -> None:
    """Verify test ensure client session tables falsy conn returns immediately."""
    ensure_client_session_tables(None)


def test_ensure_client_session_tables_idempotent_on_sqlite() -> None:
    """Verify test ensure client session tables idempotent on sqlite."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.db"
        conn = sqlite3.connect(str(p))
        try:
            _stub_fk_parents(conn)
            ensure_client_session_tables(conn)
            for table in _CLIENT_SESSION_TABLES:
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                assert row is not None, table
            idx = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' "
                "AND name='idx_client_sessions_last_active'"
            ).fetchone()
            assert idx is not None
            ensure_client_session_tables(conn)
        finally:
            conn.close()
