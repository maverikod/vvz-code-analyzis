"""
Tests for explicit transaction usage with DatabaseClient (InProcessRpcClient).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers


@pytest.fixture
def ipc_client(tmp_path: Path) -> Iterator[DatabaseClient]:
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
    r = client.execute(sql, params, transaction_id=transaction_id)
    rows = r.get("data") or []
    return rows[0] if rows else None


def test_transaction_manual_commit_success(ipc_client: DatabaseClient) -> None:
    tid = ipc_client.begin_transaction()
    try:
        ipc_client.execute(
            "INSERT INTO projects (id, root_path) VALUES (?, ?)",
            ("context-success", "/context/success"),
            transaction_id=tid,
        )
        ipc_client.commit_transaction(tid)
    except Exception:
        ipc_client.rollback_transaction(tid)
        raise
    row = _fetchone(
        ipc_client, "SELECT id FROM projects WHERE id = ?", ("context-success",)
    )
    assert row is not None
    assert row["id"] == "context-success"


def test_transaction_manual_rollback_on_error(ipc_client: DatabaseClient) -> None:
    tid = ipc_client.begin_transaction()
    with pytest.raises(ValueError):
        try:
            ipc_client.execute(
                "INSERT INTO projects (id, root_path) VALUES (?, ?)",
                ("context-error", "/context/error"),
                transaction_id=tid,
            )
            raise ValueError("Test error")
        finally:
            ipc_client.rollback_transaction(tid)

    row = _fetchone(
        ipc_client, "SELECT id FROM projects WHERE id = ?", ("context-error",)
    )
    assert row is None


def test_transaction_nested_exception_rolls_back(ipc_client: DatabaseClient) -> None:
    tid = ipc_client.begin_transaction()
    try:
        ipc_client.execute(
            "INSERT INTO projects (id, root_path) VALUES (?, ?)",
            ("nested-error", "/nested/error"),
            transaction_id=tid,
        )
        raise RuntimeError("Nested error")
    except RuntimeError:
        ipc_client.rollback_transaction(tid)

    row = _fetchone(
        ipc_client, "SELECT id FROM projects WHERE id = ?", ("nested-error",)
    )
    assert row is None


def test_transaction_multiple_ops_commit(ipc_client: DatabaseClient) -> None:
    tid = ipc_client.begin_transaction()
    try:
        ipc_client.execute(
            "INSERT INTO projects (id, root_path) VALUES (?, ?)",
            ("multi-1", "/multi/1"),
            transaction_id=tid,
        )
        ipc_client.execute(
            "INSERT INTO projects (id, root_path) VALUES (?, ?)",
            ("multi-2", "/multi/2"),
            transaction_id=tid,
        )
        ipc_client.commit_transaction(tid)
    except Exception:
        ipc_client.rollback_transaction(tid)
        raise
    assert (
        _fetchone(ipc_client, "SELECT id FROM projects WHERE id = ?", ("multi-1",))
        is not None
    )
    assert (
        _fetchone(ipc_client, "SELECT id FROM projects WHERE id = ?", ("multi-2",))
        is not None
    )
