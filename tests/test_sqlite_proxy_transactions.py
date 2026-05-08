"""
Tests for SQLite transaction semantics via in-process RPC (:class:`DatabaseClient`).

These tests assert ``begin`` / ``commit`` / ``rollback`` behavior on the SQLite driver
wired through :class:`~tests.sqlite_in_process_legacy_facade.SqliteLegacyRpcFacade` and an
in-process :class:`~code_analysis.core.database_client.client.DatabaseClient`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

import pytest

from tests.sqlite_inprocess_database import sqlite_inprocess_database_client
from tests.sqlite_in_process_legacy_facade import SqliteLegacyRpcFacade


@pytest.fixture
def temp_db_proxy(tmp_path: Path):
    """Temporary DB with in-process SQLite RPC (transaction-aware)."""
    db_path = tmp_path / "sqlite_tx.db"
    client = sqlite_inprocess_database_client(db_path, backup_dir=tmp_path / "backups")
    facade = SqliteLegacyRpcFacade(client)
    try:
        yield facade
    finally:
        facade.close()


def test_sqlite_proxy_transaction_commit(temp_db_proxy):
    """Transaction commit persists rows."""
    temp_db_proxy.begin_transaction()

    temp_db_proxy._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        ("proxy-commit", "/proxy/commit", "pc"),
    )

    temp_db_proxy.commit_transaction()

    result = temp_db_proxy._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("proxy-commit",)
    )
    assert result is not None
    assert result["id"] == "proxy-commit"


def test_sqlite_proxy_transaction_rollback(temp_db_proxy):
    """Rollback discards in-transaction inserts."""
    temp_db_proxy._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        ("before-proxy-rollback", "/before/proxy/rollback", "bpr"),
    )
    temp_db_proxy._commit()

    temp_db_proxy.begin_transaction()

    temp_db_proxy._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        ("proxy-rollback", "/proxy/rollback", "pr"),
    )

    temp_db_proxy.rollback_transaction()

    result = temp_db_proxy._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("proxy-rollback",)
    )
    assert result is None

    result = temp_db_proxy._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("before-proxy-rollback",)
    )
    assert result is not None


def test_sqlite_proxy_parallel_transactions(temp_db_proxy):
    """Committed transaction inserts remain visible."""
    temp_db_proxy.begin_transaction()
    temp_db_proxy._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        ("parallel-1", "/parallel/1", "p1"),
    )

    temp_db_proxy.commit_transaction()

    result = temp_db_proxy._fetchone(
        "SELECT id FROM projects WHERE id = ?", ("parallel-1",)
    )
    assert result is not None
