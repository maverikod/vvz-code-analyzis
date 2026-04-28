"""Driver insert return contract: DbIdentity (int | str), never 0 for UUID PK (PostgreSQL)."""

from __future__ import annotations

import sqlite3
import uuid
from unittest.mock import MagicMock

from code_analysis.core.database_driver_pkg.drivers.postgres_operations import (
    PostgreSQLOperations,
    _normalize_postgres_returning_pk,
)
from code_analysis.core.database_driver_pkg.drivers.sqlite_operations import (
    SQLiteOperations,
)


def test_normalize_postgres_returning_pk_int() -> None:
    assert _normalize_postgres_returning_pk(42) == 42


def test_normalize_postgres_returning_pk_uuid_object() -> None:
    u = uuid.uuid4()
    assert _normalize_postgres_returning_pk(u) == str(u)


def test_normalize_postgres_returning_pk_uuid_string() -> None:
    s = str(uuid.uuid4())
    assert _normalize_postgres_returning_pk(s) is s


def test_postgres_insert_returns_uuid_string_not_zero() -> None:
    """Regression: non-integer RETURNING PK must not become 0."""
    conn = MagicMock()
    cursor = MagicMock()
    uid = uuid.uuid4()
    cursor.fetchone.return_value = (uid,)
    conn.cursor.return_value = cursor

    ops = PostgreSQLOperations(conn, schema_tables={})
    out = ops.insert("projects", {"id": str(uid), "name": "p"})

    assert out == str(uid)
    assert out != 0


def test_postgres_insert_returns_int_pk() -> None:
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (7,)
    conn.cursor.return_value = cursor

    ops = PostgreSQLOperations(conn, schema_tables={})
    assert ops.insert("files", {"path": "/x", "project_id": "p1"}) == 7


def test_postgres_insert_returns_none_when_no_returning_row() -> None:
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    conn.cursor.return_value = cursor

    ops = PostgreSQLOperations(conn, schema_tables={})
    assert ops.insert("files", {"path": "/x", "project_id": "p1"}) is None


def test_sqlite_insert_explicit_text_uuid_pk_returns_string(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    pid = str(uuid.uuid4())
    conn.execute(
        "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL)",
    )
    conn.commit()

    ops = SQLiteOperations(conn)
    rid = ops.insert("projects", {"id": pid, "name": "proj"})

    assert rid == pid
    assert isinstance(rid, str)
    conn.close()


def test_sqlite_insert_autoincrement_integer_pk_returns_int(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT)")
    conn.commit()

    ops = SQLiteOperations(conn)
    rid = ops.insert("files", {"path": "/a.py"})

    assert rid == 1
    assert isinstance(rid, int)
    conn.close()


def test_sqlite_insert_explicit_integer_id_returns_int(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.commit()

    ops = SQLiteOperations(conn)
    assert ops.insert("t", {"id": 100, "v": "x"}) == 100
    conn.close()
