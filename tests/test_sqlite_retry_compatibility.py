"""Tests for SQLite self-managed write retry and structured errors."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_driver_pkg.drivers import sqlite as sqlite_mod
from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver
from code_analysis.core.database_driver_pkg.drivers.sqlite_run import (
    classify_sqlite_error,
)
from code_analysis.core.database_driver_pkg.exceptions import TransientDatabaseError
from code_analysis.core.retry_policy import RetryPolicy


def _driver() -> SQLiteDriver:
    """Return driver."""
    d = SQLiteDriver()
    d._retry_policy = RetryPolicy(
        attempts=3,
        delay_seconds=0.0,
        backoff_multiplier=1.0,
        jitter_seconds=0.0,
    )
    d.conn = MagicMock()
    d.conn.rollback = MagicMock()
    d._transaction_manager = None
    d._query_journal = None
    return d


@patch.object(sqlite_mod.time, "sleep", autospec=True)
def test_self_managed_database_locked_is_retried(_sleep: MagicMock) -> None:
    """Verify test self managed database locked is retried."""
    d = _driver()
    n = 0
    out = {"affected_rows": 1, "lastrowid": 1, "data": None}

    def side(*a: object, **k: object) -> dict:
        """Return side."""
        nonlocal n
        n += 1
        if n < 2:
            raise TransientDatabaseError(
                "database is locked",
                sqlstate=None,
                error_kind="sqlite_locked",
            )
        return out

    with patch.object(sqlite_mod, "run_execute", side_effect=side):
        r = d.execute(
            "INSERT INTO t (x) VALUES (1)",
            params=None,
            transaction_id=None,
        )
    assert r == out
    assert n == 2
    d.conn.rollback.assert_called_once()


@patch.object(sqlite_mod.time, "sleep", autospec=True)
def test_self_managed_database_busy_is_retried(_sleep: MagicMock) -> None:
    """Verify test self managed database busy is retried."""
    d = _driver()
    n = 0
    out = {"affected_rows": 1, "lastrowid": 2, "data": None}

    def side(*a: object, **k: object) -> dict:
        """Return side."""
        nonlocal n
        n += 1
        if n < 2:
            raise TransientDatabaseError(
                "database is busy",
                sqlstate=None,
                error_kind="sqlite_busy",
            )
        return out

    with patch.object(sqlite_mod, "run_execute", side_effect=side):
        r = d.execute(
            "UPDATE t SET x = 1 WHERE id = 1",
            params=None,
            transaction_id="local",
        )
    assert r == out
    assert n == 2
    d.conn.rollback.assert_called_once()


def test_sqlite_transient_details_are_structured() -> None:
    """Verify test sqlite transient details are structured."""
    exc = sqlite3.OperationalError("database is locked")
    info = classify_sqlite_error(exc, for_commit=False)
    assert info.sqlstate is None
    assert info.error_kind == "sqlite_locked"
    assert info.retryable is True
    assert info.commit_outcome_unknown is False

    tde = TransientDatabaseError(
        str(exc),
        sqlstate=info.sqlstate,
        error_kind=info.error_kind,
        retryable=info.retryable,
        commit_outcome_unknown=info.commit_outcome_unknown,
    )
    det = tde.to_details()
    assert det["sqlstate"] is None
    assert det["error_kind"] == "sqlite_locked"
    assert det["retryable"] is True
    assert det["commit_outcome_unknown"] is False


def test_sqlite_syntax_error_is_not_retryable(tmp_path: Path) -> None:
    """Verify test sqlite syntax error is not retryable."""
    db = tmp_path / "syntax.db"
    driver = SQLiteDriver()
    driver.connect({"path": str(db)})
    with pytest.raises(TransientDatabaseError) as exc_info:
        driver.execute("THIS IS NOT VALID SQL", transaction_id=None)
    assert exc_info.value.retryable is False
    d = exc_info.value.to_details()
    assert d.get("retryable") is False


def test_sqlite_integrity_error_is_not_retryable(tmp_path: Path) -> None:
    """Verify test sqlite integrity error is not retryable."""
    db = tmp_path / "integ.db"
    driver = SQLiteDriver()
    driver.connect({"path": str(db)})
    driver.execute(
        "CREATE TABLE u (id INTEGER PRIMARY KEY, x TEXT NOT NULL UNIQUE)",
        transaction_id=None,
    )
    driver.execute("INSERT INTO u (x) VALUES ('a')", transaction_id=None)
    with pytest.raises(TransientDatabaseError) as exc_info:
        driver.execute("INSERT INTO u (x) VALUES ('a')", transaction_id=None)
    assert exc_info.value.retryable is False
    assert exc_info.value.error_kind == "sqlite_integrity"


@patch.object(sqlite_mod.time, "sleep", autospec=True)
def test_external_transaction_id_is_not_retried(_sleep: MagicMock) -> None:
    """Verify test external transaction id is not retried."""
    d = _driver()
    d._transaction_manager = MagicMock()
    ext = MagicMock()
    d._transaction_manager._transactions = {"ext-tx": ext}
    n = 0

    def side(*a: object, **k: object) -> dict:
        """Return side."""
        nonlocal n
        n += 1
        raise TransientDatabaseError(
            "database is locked",
            sqlstate=None,
            error_kind="sqlite_locked",
        )

    with patch.object(sqlite_mod, "run_execute", side_effect=side):
        with pytest.raises(TransientDatabaseError):
            d.execute("INSERT INTO t (a) VALUES (1)", transaction_id="ext-tx")
    assert n == 1
    d.conn.rollback.assert_not_called()


@patch.object(sqlite_mod.time, "sleep", autospec=True)
def test_commit_outcome_unknown_is_not_retried(_sleep: MagicMock) -> None:
    """Verify test commit outcome unknown is not retried."""
    d = _driver()
    n = 0

    def side(*a: object, **k: object) -> dict:
        """Return side."""
        nonlocal n
        n += 1
        raise TransientDatabaseError(
            "maybe",
            sqlstate=None,
            error_kind="sqlite_commit",
            retryable=False,
            commit_outcome_unknown=True,
        )

    with patch.object(sqlite_mod, "run_execute", side_effect=side):
        with pytest.raises(TransientDatabaseError) as ex:
            d.execute("INSERT INTO t (a) VALUES (1)", transaction_id=None)
    assert n == 1
    assert ex.value.commit_outcome_unknown is True
    assert ex.value.retryable is False
    d.conn.rollback.assert_not_called()


@patch.object(sqlite_mod.time, "sleep", autospec=True)
def test_retry_delay_uses_shared_policy(sleep: MagicMock) -> None:
    """Verify test retry delay uses shared policy."""
    d = _driver()
    d._retry_policy = RetryPolicy(
        attempts=3,
        delay_seconds=0.5,
        backoff_multiplier=1.0,
        jitter_seconds=0.0,
    )
    n = 0
    out = {"affected_rows": 0, "lastrowid": None, "data": None}

    def side(*a: object, **k: object) -> dict:
        """Return side."""
        nonlocal n
        n += 1
        if n < 2:
            raise TransientDatabaseError(
                "database is busy",
                sqlstate=None,
                error_kind="sqlite_busy",
            )
        return out

    with patch.object(sqlite_mod, "run_execute", side_effect=side):
        d.execute("DELETE FROM t WHERE 1=0", transaction_id=None)

    expected = d._retry_policy.delay_for_attempt(1)
    sleep.assert_called_once()
    assert abs(sleep.call_args[0][0] - expected) < 1e-9


def test_no_project_lock_or_advisory_lock_behavior_in_sqlite_driver() -> None:
    """Verify test no project lock or advisory lock behavior in sqlite driver."""
    root = (
        Path(__file__).resolve().parents[1]
        / "code_analysis"
        / "core"
        / "database_driver_pkg"
        / "drivers"
    )
    s1 = (root / "sqlite.py").read_text(encoding="utf-8").lower()
    s2 = (root / "sqlite_run.py").read_text(encoding="utf-8").lower()
    for needle in ("advisory", "project_lock", "project lock", "watcher", "indexer"):
        assert needle not in s1, needle
        assert needle not in s2, needle
