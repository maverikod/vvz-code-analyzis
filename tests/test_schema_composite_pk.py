"""
Regression tests for composite PRIMARY KEY DDL generation in both drivers.

Tables such as ``watch_dirs`` / ``watch_dir_paths`` flag two columns with
``primary_key: True`` (a composite key). The generator must emit ONE table-level
``PRIMARY KEY (a, b)`` clause, never two inline column-level ``PRIMARY KEY``
clauses (rejected by SQLite "more than one primary key" / PostgreSQL "multiple
primary keys for table are not allowed").

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, List

from code_analysis.core.database_driver_pkg.drivers.postgres_tables import (
    run_create_table_postgres,
)

_COMPOSITE_SCHEMA = {
    "name": "watch_dir_paths",
    "columns": [
        {
            "name": "server_instance_id",
            "type": "TEXT",
            "not_null": True,
            "primary_key": True,
        },
        {"name": "watch_dir_id", "type": "TEXT", "not_null": True, "primary_key": True},
        {"name": "absolute_path", "type": "TEXT"},
    ],
}

_SINGLE_PK_SCHEMA = {
    "name": "solo",
    "columns": [
        {"name": "id", "type": "TEXT", "primary_key": True},
        {"name": "val", "type": "TEXT"},
    ],
}


# --------------------------------------------------------------------------- #
# PostgreSQL driver (SQL generation only; no live server)
# --------------------------------------------------------------------------- #


class _FakeCursor:
    """Represent FakeCursor."""

    def __init__(self, sink: List[str]) -> None:
        """Initialize the instance."""
        self._sink = sink

    def execute(self, sql: str, params: Any = None) -> None:
        """Execute the command."""
        self._sink.append(sql)


class _FakeConn:
    """Represent FakeConn."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self.statements: List[str] = []

    def cursor(self) -> _FakeCursor:
        """Return cursor."""
        return _FakeCursor(self.statements)

    def commit(self) -> None:
        """Return commit."""
        pass

    def rollback(self) -> None:
        """Return rollback."""
        pass


def test_postgres_composite_pk_single_table_level_clause() -> None:
    """Verify test postgres composite pk single table level clause."""
    conn = _FakeConn()
    assert run_create_table_postgres(conn, _COMPOSITE_SCHEMA) is True
    sql = conn.statements[-1]
    # Exactly one table-level composite clause, no inline column PK.
    assert "PRIMARY KEY (server_instance_id, watch_dir_id)" in sql
    assert "TEXT PRIMARY KEY" not in sql


def test_postgres_single_pk_inline() -> None:
    """Verify test postgres single pk inline."""
    conn = _FakeConn()
    assert run_create_table_postgres(conn, _SINGLE_PK_SCHEMA) is True
    sql = conn.statements[-1]
    assert "id TEXT PRIMARY KEY" in sql
    assert "PRIMARY KEY (" not in sql  # no composite clause for a single PK
