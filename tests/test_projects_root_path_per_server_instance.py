"""Tests for server-scoped projects.root_path uniqueness."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from code_analysis.core.database.migrations.projects_root_path_per_server_instance import (
    migrate_projects_root_path_per_server_instance,
)


class _SqliteMigrationDb:
    _driver_type = "sqlite"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _execute(self, sql: str, params: tuple = ()) -> None:
        self._conn.execute(sql, params)

    def _commit(self) -> None:
        self._conn.commit()

    def _fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        cur = self._conn.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        return dict(zip([d[0] for d in cur.description], row, strict=False))

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self._conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    def _get_table_info(self, table: str) -> list[dict]:
        cur = self._conn.execute(f"PRAGMA table_info({table})")
        return [{"name": row[1], "type": row[2]} for row in cur.fetchall()]


@pytest.fixture
def db() -> _SqliteMigrationDb:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE db_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("""
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            server_instance_id TEXT,
            root_path TEXT NOT NULL,
            name TEXT,
            watch_dir_id TEXT
        )
        """)
    conn.execute("""
        CREATE UNIQUE INDEX ux_projects_watch_dir_id_root_path
        ON projects(watch_dir_id, root_path)
        """)
    facade = _SqliteMigrationDb(conn)
    migrate_projects_root_path_per_server_instance(facade)
    return facade


def test_same_root_path_allowed_on_different_server_instances(db) -> None:
    wid = str(uuid.uuid4())
    stored = "code_analysis"
    db._execute(
        "INSERT INTO projects (id, server_instance_id, root_path, name, watch_dir_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "server-a", stored, "code_analysis", wid),
    )
    db._execute(
        "INSERT INTO projects (id, server_instance_id, root_path, name, watch_dir_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "server-b", stored, "code_analysis", wid),
    )
    db._commit()
    assert len(db._fetchall("SELECT id FROM projects")) == 2


def test_same_root_path_rejected_on_same_server_instance(db) -> None:
    wid = str(uuid.uuid4())
    stored = "code_analysis"
    db._execute(
        "INSERT INTO projects (id, server_instance_id, root_path, name, watch_dir_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "server-a", stored, "code_analysis", wid),
    )
    db._commit()
    with pytest.raises(sqlite3.IntegrityError):
        db._execute(
            "INSERT INTO projects (id, server_instance_id, root_path, name, watch_dir_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "server-a", stored, "code_analysis", wid),
        )
        db._commit()
