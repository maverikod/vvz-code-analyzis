"""
Self-defence tests for ``PostgreSQLTransactionManager`` and the batch caller.

These exercise the connection-leak fix without a live PostgreSQL server by
injecting a fake psycopg connection (``psycopg.connect`` is monkeypatched). They
cover idempotent teardown, the expiry reaper, and the exception-safety of
``save_comprehensive_analysis_results_batch``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

import pytest

from code_analysis.core.database_driver_pkg.drivers.postgres_transactions import (
    PostgreSQLTransactionManager,
)
from code_analysis.core.database_driver_pkg.exceptions import TransactionError


class _FakeCursor:
    """Minimal cursor context manager (timeouts disabled, so never executes)."""

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def execute(self, *args: Any, **kwargs: Any) -> None:
        return None


class _FakeConn:
    """Fake psycopg connection tracking close/rollback/commit call counts."""

    def __init__(self) -> None:
        self.autocommit = False
        self.close_count = 0
        self.rollback_count = 0
        self.commit_count = 0
        self.commit_should_raise = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor()

    def commit(self) -> None:
        if self.commit_should_raise:
            raise RuntimeError("injected commit failure")
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.close_count += 1


@pytest.fixture
def fake_psycopg(monkeypatch: pytest.MonkeyPatch) -> List[_FakeConn]:
    """Patch ``psycopg.connect`` to hand out fake connections; return the list."""
    import psycopg

    created: List[_FakeConn] = []

    def _connect(**_kwargs: Any) -> _FakeConn:
        conn = _FakeConn()
        created.append(conn)
        return conn

    monkeypatch.setattr(psycopg, "connect", _connect)
    return created


@pytest.fixture
def manager() -> PostgreSQLTransactionManager:
    """Return a manager with no real DB (connect is patched per-test)."""
    return PostgreSQLTransactionManager({"dbname": "fake"})


def test_teardown_idempotent(
    manager: PostgreSQLTransactionManager, fake_psycopg: List[_FakeConn]
) -> None:
    """T1: closing a transaction twice does not raise or double-close."""
    tid = manager.begin_transaction()
    conn = fake_psycopg[0]

    assert manager.close_transaction(tid, reason="unit_test") is True
    assert conn.close_count == 1
    # Second call is a no-op: returns False, never raises, never closes again.
    assert manager.close_transaction(tid, reason="unit_test") is False
    assert conn.close_count == 1
    assert manager.get_connection(tid) is None


def test_reaper_reaps_orphans(
    manager: PostgreSQLTransactionManager, fake_psycopg: List[_FakeConn]
) -> None:
    """T2: an aged, uncommitted transaction is force-closed by reap_expired."""
    tid = manager.begin_transaction()
    conn = fake_psycopg[0]
    # Age the entry deterministically past the threshold.
    manager._transactions[tid].created_monotonic = time.monotonic() - 2.0

    reaped = manager.reap_expired(1.0)

    assert reaped == 1
    assert manager.get_connection(tid) is None
    assert conn.close_count == 1
    assert conn.rollback_count == 1


def test_reaper_spares_fresh(
    manager: PostgreSQLTransactionManager, fake_psycopg: List[_FakeConn]
) -> None:
    """T3: a fresh transaction is left untouched and remains usable."""
    tid = manager.begin_transaction()
    conn = fake_psycopg[0]

    assert manager.reap_expired(300.0) == 0
    assert manager.get_connection(tid) is conn
    # Still usable: commit succeeds and closes the connection exactly once.
    assert manager.commit_transaction(tid) is True
    assert conn.commit_count == 1
    assert conn.close_count == 1
    assert manager.get_connection(tid) is None


def test_commit_failure_does_not_leak(
    manager: PostgreSQLTransactionManager, fake_psycopg: List[_FakeConn]
) -> None:
    """A failed commit still closes the backend connection and clears the entry."""
    tid = manager.begin_transaction()
    conn = fake_psycopg[0]
    conn.commit_should_raise = True

    with pytest.raises(TransactionError):
        manager.commit_transaction(tid)

    assert conn.close_count == 1
    assert manager.get_connection(tid) is None


def test_reap_returns_zero_when_empty(
    manager: PostgreSQLTransactionManager,
) -> None:
    """Reaping with nothing open returns 0 (no log, no error)."""
    assert manager.reap_expired(0.0) == 0


# --- Part B: caller exception safety -------------------------------------


class _FakeBatchClient:
    """Client backed by a real manager + fake conns; execute_batch can fail."""

    _driver_type = "sqlite"  # sql_julian helper just needs an attribute

    def __init__(self, fail_batch: bool) -> None:
        self._mgr = PostgreSQLTransactionManager({"dbname": "fake"})
        self._fail_batch = fail_batch

    def begin_transaction(self) -> str:
        return self._mgr.begin_transaction()

    def execute_batch(self, operations: Any, transaction_id: str) -> Any:
        if self._fail_batch:
            raise RuntimeError("injected batch failure")
        return []

    def commit_transaction(self, transaction_id: str) -> bool:
        return self._mgr.commit_transaction(transaction_id)

    def rollback_transaction(self, transaction_id: str) -> bool:
        return self._mgr.rollback_transaction(transaction_id)


def _save_batch(client: Any, items: Any) -> None:
    """Invoke the real mixin method against a fake client."""
    from code_analysis.core.database_client.client_api_comprehensive_analysis import (
        _ClientAPIComprehensiveAnalysisMixin,
    )

    _ClientAPIComprehensiveAnalysisMixin.save_comprehensive_analysis_results_batch(
        client, items
    )


def test_caller_rolls_back_on_failure(fake_psycopg: List[_FakeConn]) -> None:
    """T4: an exception in execute_batch leaves zero open transactions."""
    client = _FakeBatchClient(fail_batch=True)
    items = [(1, "proj", 1.0, {"a": 1}, {"b": 2})]

    with pytest.raises(RuntimeError, match="injected batch failure"):
        _save_batch(client, items)

    # The transaction connection was rolled back and closed (no orphan).
    assert len(client._mgr._transactions) == 0
    assert fake_psycopg[0].close_count == 1
    assert fake_psycopg[0].rollback_count == 1


def test_caller_commits_on_success(fake_psycopg: List[_FakeConn]) -> None:
    """Happy path: success commits exactly once and leaves no open transaction."""
    client = _FakeBatchClient(fail_batch=False)
    items = [(1, "proj", 1.0, {"a": 1}, {"b": 2})]

    _save_batch(client, items)

    assert len(client._mgr._transactions) == 0
    assert fake_psycopg[0].commit_count == 1
    assert fake_psycopg[0].close_count == 1


# --- Live PostgreSQL integration (optional; skipped without a DSN) --------

_PG_ENV = "CODE_ANALYSIS_POSTGRES_TEST_DSN"


def _live_connect_kwargs() -> Dict[str, Any]:
    """Return psycopg connect kwargs from the optional live-test DSN, or skip."""
    dsn = (os.environ.get(_PG_ENV) or "").strip()
    if not dsn:
        pytest.skip(
            f"Live PostgreSQL test skipped: set {_PG_ENV} to run (optional CI)."
        )
    import psycopg

    try:
        return psycopg.conninfo.conninfo_to_dict(dsn)
    except Exception:
        return {"conninfo": dsn}


def _backend_count(connect_kwargs: Dict[str, Any]) -> int:
    """Count this database's backend connections via a short-lived connection."""
    import psycopg

    with psycopg.connect(**connect_kwargs) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database()"
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0


@pytest.mark.postgres
@pytest.mark.integration
def test_live_backend_connection_conservation() -> None:
    """T6: N begin+commit cycles do not grow the backend connection count."""
    connect_kwargs = _live_connect_kwargs()
    mgr = PostgreSQLTransactionManager(connect_kwargs)

    baseline = _backend_count(connect_kwargs)
    for _ in range(50):
        tid = mgr.begin_transaction()
        # The dedicated connection is live here (baseline + 1), then released.
        assert mgr.get_connection(tid) is not None
        mgr.commit_transaction(tid)

    assert len(mgr._transactions) == 0
    after = _backend_count(connect_kwargs)
    # No monotonic growth: every transaction released its backend connection.
    assert after <= baseline + 1, (
        f"backend connections leaked: baseline={baseline} after={after}"
    )
    mgr.close_all()


@pytest.mark.postgres
@pytest.mark.integration
def test_live_reaper_closes_orphan_backend() -> None:
    """A genuinely orphaned live transaction is force-closed by the reaper."""
    connect_kwargs = _live_connect_kwargs()
    mgr = PostgreSQLTransactionManager(connect_kwargs)

    baseline = _backend_count(connect_kwargs)
    tid = mgr.begin_transaction()
    assert _backend_count(connect_kwargs) >= baseline + 1
    # Age past the threshold without committing, then reap.
    mgr._transactions[tid].created_monotonic = time.monotonic() - 10.0

    assert mgr.reap_expired(1.0) == 1
    assert mgr.get_connection(tid) is None
    # Give the backend a moment to drop the terminated connection.
    deadline = time.monotonic() + 5.0
    while _backend_count(connect_kwargs) > baseline and time.monotonic() < deadline:
        time.sleep(0.1)
    assert _backend_count(connect_kwargs) <= baseline
    mgr.close_all()
