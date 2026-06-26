"""
Fresh DB: skip driver migrations before base tables; catalog probe without noisy SELECT.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from code_analysis.commands.base_mcp_command_open_db import _sqlite_master_has_table
from code_analysis.core.database_driver_pkg.drivers.sqlite_migrations import (
    _SqliteConnMigrateAdapter,
    _sqlite_table_exists,
    run_all_ensure,
)
from code_analysis.core.database_driver_pkg.drivers.sqlite_schema import (
    SQLiteSchemaManager,
)
from code_analysis.core.database.schema_creation_migrate import run_migrate_schema

_CORE_SCHEMA_TABLES = frozenset(
    {
        "projects",
        "files",
        "code_chunks",
        "issues",
        "functions",
        "methods",
        "classes",
    }
)

_CONNECTION_TIME_TABLES = frozenset(
    {
        "runtime_lock_sessions",
        "file_advisory_lock_leases",
        "entity_cross_ref",
        "indexing_worker_stats",
        "indexing_errors",
        "client_sessions",
        "session_file_locks",
        "roles",
        "role_permissions",
        "session_roles",
        "subordinate_sessions",
    }
)


def _user_table_names(conn: sqlite3.Connection) -> set[str]:
    """Return user table names."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return {r[0] for r in cur.fetchall()}


def test_sqlite_table_exists_false_on_empty_db() -> None:
    """Verify test sqlite table exists false on empty db."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "e.db"
        conn = sqlite3.connect(str(p))
        try:
            assert _sqlite_table_exists(conn, "projects") is False
        finally:
            conn.close()


def test_run_all_ensure_skips_core_schema_on_empty_db() -> None:
    """Connection-time ensure_* tables are created; core schema is not bootstrapped."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "e.db"
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        try:
            sm = SQLiteSchemaManager(conn)
            run_all_ensure(conn, sm, p)
            names = _user_table_names(conn)
            assert _CORE_SCHEMA_TABLES.isdisjoint(names)
            assert _CONNECTION_TIME_TABLES <= names
        finally:
            conn.close()


def test_run_migrate_schema_probes_without_creating_core_schema() -> None:
    """run_migrate_schema inspects missing tables but only creates connection-time DDL."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "e.db"
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        try:
            sm = SQLiteSchemaManager(conn)
            run_migrate_schema(_SqliteConnMigrateAdapter(conn, sm))
            names = _user_table_names(conn)
            assert _CORE_SCHEMA_TABLES.isdisjoint(names)
            assert {
                "runtime_lock_sessions",
                "file_advisory_lock_leases",
                "entity_cross_ref",
            } <= names
            assert "client_sessions" not in names
        finally:
            conn.close()


def test_sqlite_master_has_table_uses_execute_data_shape() -> None:
    """Verify test sqlite master has table uses execute data shape."""
    db = MagicMock()
    db.execute.return_value = {"data": [{"ok": 1}]}
    assert _sqlite_master_has_table(db, "projects") is True
    db.execute.return_value = {"data": []}
    assert _sqlite_master_has_table(db, "projects") is False
