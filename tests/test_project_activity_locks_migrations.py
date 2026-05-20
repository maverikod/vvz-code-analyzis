"""
Migrations and schema for project_activity_locks (Steps 11–12).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database.schema_sync_sql_postgres import (
    generate_create_table_sql_postgres,
)
from code_analysis.core.database_driver_pkg.drivers.postgres_migrations import (
    idempotent_ensure_client_session_tables,
    idempotent_ensure_project_activity_locks_table,
)
from code_analysis.core.database_driver_pkg.drivers.sqlite_migrations import (
    ensure_project_activity_locks_table,
    ensure_runtime_file_lock_tables,
)


def test_schema_definition_includes_project_activity_locks() -> None:
    sd = get_schema_definition()
    assert "project_activity_locks" in sd["tables"]
    cols = {c["name"] for c in sd["tables"]["project_activity_locks"]["columns"]}
    assert cols == {
        "project_id",
        "owner_type",
        "owner_id",
        "activity",
        "acquired_at",
        "heartbeat_at",
        "lease_until",
    }
    assert any(
        i.get("name") == "idx_project_activity_locks_lease_until" for i in sd["indexes"]
    )
    assert "runtime_lock_sessions" in sd["tables"]
    assert "file_advisory_lock_leases" in sd["tables"]
    lease_cols = {
        c["name"] for c in sd["tables"]["file_advisory_lock_leases"]["columns"]
    }
    assert {
        "session_id",
        "project_id",
        "file_path",
        "lock_mode",
        "refcount",
    }.issubset(lease_cols)
    for table in (
        "client_sessions",
        "session_file_locks",
        "roles",
        "role_permissions",
        "session_roles",
    ):
        assert table in sd["tables"]
    assert any(
        i.get("name") == "idx_client_sessions_last_active" for i in sd["indexes"]
    )


def test_postgres_ddl_uses_create_if_not_exists() -> None:
    sd = get_schema_definition()
    ddl = generate_create_table_sql_postgres(sd, "project_activity_locks")
    assert "CREATE TABLE IF NOT EXISTS project_activity_locks" in ddl
    assert "lease_until" in ddl


def test_ensure_sqlite_project_activity_locks_idempotent() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.db"
        conn = sqlite3.connect(str(p))
        try:
            conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY)")
            conn.commit()
            ensure_project_activity_locks_table(conn)
            one = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_activity_locks'"
            ).fetchone()
            assert one is not None
            one_idx = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_project_activity_locks_lease_until'"
            ).fetchone()
            assert one_idx is not None
            ensure_project_activity_locks_table(conn)
        finally:
            conn.close()


def test_ensure_sqlite_runtime_file_lock_tables_idempotent() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.db"
        conn = sqlite3.connect(str(p))
        try:
            conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY)")
            conn.commit()
            ensure_runtime_file_lock_tables(conn)
            for table in ("runtime_lock_sessions", "file_advisory_lock_leases"):
                one = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                assert one is not None
            ensure_runtime_file_lock_tables(conn)
        finally:
            conn.close()


def test_ensure_sqlite_skips_without_projects_table() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.db"
        conn = sqlite3.connect(str(p))
        try:
            ensure_project_activity_locks_table(conn)
            one = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_activity_locks'"
            ).fetchone()
            assert one is None
        finally:
            conn.close()


def test_idempotent_ensure_postgres_runs_table_and_index() -> None:
    cur = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = lambda *a, **k: cur
    ctx.__exit__ = lambda *a, **k: None
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=ctx)
    idempotent_ensure_project_activity_locks_table(conn, get_schema_definition())
    assert cur.execute.call_count >= 2
    assert "CREATE TABLE IF NOT EXISTS" in cur.execute.call_args_list[0][0][0]
    statements = [call[0][0] for call in cur.execute.call_args_list]
    assert any("idx_project_activity_locks_lease_until" in stmt for stmt in statements)
    assert any("runtime_lock_sessions" in stmt for stmt in statements)
    assert any("file_advisory_lock_leases" in stmt for stmt in statements)
    conn.commit.assert_called_once()


def test_idempotent_ensure_postgres_client_session_tables() -> None:
    cur = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = lambda *a, **k: cur
    ctx.__exit__ = lambda *a, **k: None
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=ctx)
    idempotent_ensure_client_session_tables(conn, get_schema_definition())
    assert cur.execute.call_count >= 6
    statements = [call[0][0] for call in cur.execute.call_args_list]
    assert any("client_sessions" in stmt for stmt in statements)
    assert any("session_file_locks" in stmt for stmt in statements)
    assert any("roles" in stmt for stmt in statements)
    assert any("idx_client_sessions_last_active" in stmt for stmt in statements)
    conn.commit.assert_called_once()
