"""
Tests for database transaction support (DatabaseClient + InProcessRpcClient).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.exceptions import RPCResponseError
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers


@pytest.fixture
def ipc_client(tmp_path: Path) -> Iterator[DatabaseClient]:
    """Temporary DB, full schema, in-process RPC client."""
    db_path = tmp_path / "test.db"
    driver = create_driver("sqlite", {"path": str(db_path)})
    handlers = RPCHandlers(driver)
    ipc = InProcessRpcClient(handlers)
    client = DatabaseClient(rpc_client=ipc)
    client.connect()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    client.sync_schema(get_schema_definition(), backup_dir=str(backup_dir))
    try:
        yield client
    finally:
        client.disconnect()


def _fetchone(
    client: DatabaseClient,
    sql: str,
    params: tuple | None = None,
    *,
    transaction_id: str | None = None,
):
    """Return fetchone."""
    r = client.execute(sql, params, transaction_id=transaction_id)
    rows = r.get("data") or []
    return rows[0] if rows else None


def test_begin_transaction_returns_id(ipc_client: DatabaseClient) -> None:
    """Verify test begin transaction returns id."""
    tid = ipc_client.begin_transaction()
    assert isinstance(tid, str) and len(tid) > 0
    ipc_client.commit_transaction(tid)


def test_commit_transaction(ipc_client: DatabaseClient) -> None:
    """Verify test commit transaction."""
    tid = ipc_client.begin_transaction()
    ipc_client.execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("test-id", "/test/path"),
        transaction_id=tid,
    )
    ipc_client.commit_transaction(tid)
    row = _fetchone(ipc_client, "SELECT id FROM projects WHERE id = ?", ("test-id",))
    assert row is not None
    assert row["id"] == "test-id"


def test_rollback_transaction(ipc_client: DatabaseClient) -> None:
    """Verify test rollback transaction."""
    tid = ipc_client.begin_transaction()
    ipc_client.execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("rollback-id", "/rollback/path"),
        transaction_id=tid,
    )
    ipc_client.rollback_transaction(tid)
    row = _fetchone(
        ipc_client, "SELECT id FROM projects WHERE id = ?", ("rollback-id",)
    )
    assert row is None


def test_two_separate_transactions_allowed(ipc_client: DatabaseClient) -> None:
    """RPC SQLite driver uses one connection per ``transaction_id`` (no legacy single-tx mutex)."""
    tid1 = ipc_client.begin_transaction()
    tid2 = ipc_client.begin_transaction()
    assert tid1 != tid2
    ipc_client.rollback_transaction(tid1)
    ipc_client.rollback_transaction(tid2)


def test_commit_without_transaction_fails(ipc_client: DatabaseClient) -> None:
    """Verify test commit without transaction fails."""
    with pytest.raises(RPCResponseError):
        ipc_client.commit_transaction("00000000-0000-0000-0000-000000000099")


def test_rollback_without_transaction_fails(ipc_client: DatabaseClient) -> None:
    """Verify test rollback without transaction fails."""
    with pytest.raises(RPCResponseError):
        ipc_client.rollback_transaction("00000000-0000-0000-0000-000000000099")


def test_transaction_isolation(ipc_client: DatabaseClient) -> None:
    """Verify test transaction isolation."""
    ipc_client.execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("outside-id", "/outside/path"),
    )
    tid = ipc_client.begin_transaction()
    ipc_client.execute(
        "INSERT INTO projects (id, root_path) VALUES (?, ?)",
        ("inside-id", "/inside/path"),
        transaction_id=tid,
    )
    inside_in_tx = _fetchone(
        ipc_client,
        "SELECT id FROM projects WHERE id = ?",
        ("inside-id",),
        transaction_id=tid,
    )
    inside_on_main = _fetchone(
        ipc_client, "SELECT id FROM projects WHERE id = ?", ("inside-id",)
    )
    assert inside_in_tx is not None
    assert inside_on_main is None

    ipc_client.rollback_transaction(tid)
    assert (
        _fetchone(ipc_client, "SELECT id FROM projects WHERE id = ?", ("inside-id",))
        is None
    )
    assert (
        _fetchone(ipc_client, "SELECT id FROM projects WHERE id = ?", ("outside-id",))
        is not None
    )


def test_begin_commit_rollback_roundtrip(ipc_client: DatabaseClient) -> None:
    """Verify test begin commit rollback roundtrip."""
    tid = ipc_client.begin_transaction()
    ipc_client.commit_transaction(tid)
    tid2 = ipc_client.begin_transaction()
    ipc_client.rollback_transaction(tid2)
