"""PostgreSQL operations: SELECT ends implicit transaction (idle-in-transaction fix)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from code_analysis.core.database_driver_pkg.drivers.postgres_operations import (
    PostgreSQLOperations,
)
from code_analysis.core.database_driver_pkg.exceptions import DriverOperationError


def test_postgres_select_calls_commit_after_successful_read() -> None:
    """SELECT must commit so autocommit=False sessions do not sit idle in transaction.

    Bug 8e6acb34: select() no longer runs on ``self.conn`` -- it takes the
    connection to use via the keyword-only ``connection`` argument (normally a
    pooled read-lane lease from ``PostgreSQLDriver.select()``). The
    ``PostgreSQLOperations`` instance is still constructed with a main
    connection (used by insert/update/delete), but that main connection is
    deliberately NOT the one passed to select() here, to prove select() reads
    from ``connection`` and not ``self.conn``.
    """
    main_conn = MagicMock(name="main_conn_unused_by_select")
    read_conn = MagicMock(name="pooled_read_conn")
    cursor = MagicMock()
    cursor.description = [("id",)]
    cursor.fetchall.return_value = [(1,)]
    read_conn.cursor.return_value = cursor

    ops = PostgreSQLOperations(main_conn, schema_tables={})
    rows = ops.select("projects", where={"id": "x"}, columns=["id"], connection=read_conn)

    assert rows == [{"id": 1}]
    read_conn.commit.assert_called_once()
    cursor.close.assert_called_once()
    main_conn.cursor.assert_not_called()
    main_conn.commit.assert_not_called()


def test_postgres_select_without_connection_raises() -> None:
    """select() with no ``connection`` raises immediately -- it never falls back to self.conn."""
    conn = MagicMock()
    ops = PostgreSQLOperations(conn, schema_tables={})

    with pytest.raises(DriverOperationError, match="connection not established"):
        ops.select("projects", where={"id": "x"})

    conn.cursor.assert_not_called()
