"""Driver insert return contract: DbIdentity (int | str), never 0 for UUID PK (PostgreSQL)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from code_analysis.core.database_driver_pkg.drivers.postgres_operations import (
    PostgreSQLOperations,
    _normalize_postgres_returning_pk,
)


def test_normalize_postgres_returning_pk_int() -> None:
    """Verify test normalize postgres returning pk int."""
    assert _normalize_postgres_returning_pk(42) == 42


def test_normalize_postgres_returning_pk_uuid_object() -> None:
    """Verify test normalize postgres returning pk uuid object."""
    u = uuid.uuid4()
    assert _normalize_postgres_returning_pk(u) == str(u)


def test_normalize_postgres_returning_pk_uuid_string() -> None:
    """Verify test normalize postgres returning pk uuid string."""
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
    """Verify test postgres insert returns int pk."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (7,)
    conn.cursor.return_value = cursor

    ops = PostgreSQLOperations(conn, schema_tables={})
    assert ops.insert("files", {"path": "/x", "project_id": "p1"}) == 7


def test_postgres_insert_returns_none_when_no_returning_row() -> None:
    """Verify test postgres insert returns none when no returning row."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    conn.cursor.return_value = cursor

    ops = PostgreSQLOperations(conn, schema_tables={})
    assert ops.insert("files", {"path": "/x", "project_id": "p1"}) is None
