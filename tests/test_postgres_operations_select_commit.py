"""PostgreSQL operations: SELECT ends implicit transaction (idle-in-transaction fix)."""

from __future__ import annotations

from unittest.mock import MagicMock

from code_analysis.core.database_driver_pkg.drivers.postgres_operations import (
    PostgreSQLOperations,
)


def test_postgres_select_calls_commit_after_successful_read() -> None:
    """SELECT must commit so autocommit=False sessions do not sit idle in transaction."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.description = [("id",)]
    cursor.fetchall.return_value = [(1,)]
    conn.cursor.return_value = cursor

    ops = PostgreSQLOperations(conn, schema_tables={})
    rows = ops.select("projects", where={"id": "x"}, columns=["id"])

    assert rows == [{"id": 1}]
    conn.commit.assert_called_once()
    cursor.close.assert_called_once()
