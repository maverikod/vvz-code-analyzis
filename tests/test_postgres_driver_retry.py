"""Tests for self-managed execute and execute_batch retry behavior."""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_driver_pkg.drivers import postgres as postgres_mod
from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver
from code_analysis.core.database_driver_pkg.exceptions import (
    DriverOperationError,
    TransientDatabaseError,
)
from code_analysis.core.retry_policy import RetryPolicy

_LOG = "code_analysis.core.database_driver_pkg.drivers.postgres"


def _driver() -> PostgreSQLDriver:
    """Return driver."""
    d = PostgreSQLDriver()
    d._retry_policy = RetryPolicy(
        attempts=3,
        delay_seconds=0.0,
        backoff_multiplier=1.0,
        jitter_seconds=0.0,
    )
    d._schema_tables = {}
    d._query_journal = None
    d.conn = MagicMock()
    d.conn.rollback = MagicMock()

    @contextmanager
    def _acquire(write: bool = False):
        """Return acquire."""
        try:
            yield d.conn
        except BaseException as exc:
            try:
                d.conn.rollback()
            except Exception as rb:
                raise DriverOperationError(
                    f"Rollback before database retry failed: {rb}"
                ) from rb
            raise exc

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(side_effect=lambda write=False: _acquire(write=write))
    d._pool = mock_pool
    return d


@patch.object(postgres_mod.time, "sleep", autospec=True)
def test_execute_batch_retries_self_managed_transient(
    _sleep: MagicMock,
) -> None:
    """Verify test execute batch retries self managed transient."""
    d = _driver()
    n = 0
    out = [{"affected_rows": 1, "lastrowid": None, "data": None}]

    def side(*a: object, **k: object) -> list:
        """Return side."""
        nonlocal n
        n += 1
        if n < 2:
            raise TransientDatabaseError(
                "deadlock",
                sqlstate="40P01",
                error_kind="deadlock",
            )
        return out

    with patch.object(postgres_mod, "run_execute_batch", side_effect=side):
        r = d.execute_batch([("SELECT 1", None)], transaction_id=None)
    assert r == out
    assert n == 2
    d.conn.rollback.assert_called_once()


@patch.object(postgres_mod.time, "sleep", autospec=True)
def test_execute_retries_self_managed_transient(_sleep: MagicMock) -> None:
    """Verify test execute retries self managed transient."""
    d = _driver()
    n = 0
    result = {"affected_rows": 0, "lastrowid": None, "data": None}

    def side(*a: object, **k: object) -> dict:
        """Return side."""
        nonlocal n
        n += 1
        if n < 2:
            raise TransientDatabaseError(
                "deadlock",
                sqlstate="40P01",
                error_kind="deadlock",
            )
        return result

    with patch.object(postgres_mod, "run_execute", side_effect=side):
        r = d.execute("SELECT 1", params=None, transaction_id="local")
    assert r == result
    assert n == 2
    d.conn.rollback.assert_called_once()


def test_external_transaction_execute_and_batch_skips_pool_acquire() -> None:
    """Explicit transaction_id uses _transactions conn; never pool.acquire."""
    d = _driver()
    pool_mock = cast(MagicMock, d._pool)
    d._transaction_manager = MagicMock()
    ext = MagicMock()
    d._transaction_manager._transactions = {"ext-tx": ext}
    d._transaction_manager.get_connection.return_value = ext

    with patch.object(postgres_mod, "run_execute") as mock_run:
        mock_run.return_value = {
            "affected_rows": 0,
            "lastrowid": None,
            "data": None,
        }
        d.execute("SELECT 1", transaction_id="ext-tx")

    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] is ext
    pool_mock.acquire.assert_not_called()

    pool_mock.acquire.reset_mock()

    with patch.object(postgres_mod, "run_execute_batch") as mock_batch:
        mock_batch.return_value = [
            {"affected_rows": 0, "lastrowid": None, "data": None},
        ]
        d.execute_batch([("SELECT 1", None)], transaction_id="ext-tx")

    mock_batch.assert_called_once()
    assert mock_batch.call_args[0][0] is ext
    pool_mock.acquire.assert_not_called()


@patch.object(postgres_mod.time, "sleep", autospec=True)
def test_external_transaction_id_not_retried(_sleep: MagicMock) -> None:
    """Verify test external transaction id not retried."""
    d = _driver()
    d._transaction_manager = MagicMock()
    ext = MagicMock()
    d._transaction_manager._transactions = {"ext-tx": ext}
    d._transaction_manager.get_connection.return_value = ext
    n = 0

    def side(*a: object, **k: object) -> dict:
        """Return side."""
        nonlocal n
        n += 1
        raise TransientDatabaseError(
            "deadlock",
            sqlstate="40P01",
            error_kind="deadlock",
        )

    with patch.object(postgres_mod, "run_execute", side_effect=side):
        with pytest.raises(TransientDatabaseError):
            d.execute("SELECT 1", transaction_id="ext-tx")
    assert n == 1
    d.conn.rollback.assert_not_called()


@patch.object(postgres_mod.time, "sleep", autospec=True)
def test_rollback_before_transient_retry(_sleep: MagicMock) -> None:
    """Verify test rollback before transient retry."""
    d = _driver()
    calls: list[str] = []

    def se(*a: object, **k: object) -> list:
        """Return se."""
        calls.append("run")
        if len(calls) < 2:
            raise TransientDatabaseError(
                "deadlock",
                sqlstate="40P01",
                error_kind="deadlock",
            )
        return [
            {
                "affected_rows": 0,
                "lastrowid": None,
                "data": None,
            }
        ]

    def rb() -> None:
        """Return rb."""
        calls.append("rollback")
        return None

    d.conn.rollback.side_effect = rb

    with patch.object(postgres_mod, "run_execute_batch", side_effect=se):
        d.execute_batch([("X", None)])
    # run, rollback, run
    assert calls == ["run", "rollback", "run"]


@patch.object(postgres_mod.time, "sleep", autospec=True)
def test_no_retry_when_commit_outcome_unknown(_sleep: MagicMock) -> None:
    """Verify test no retry when commit outcome unknown."""
    d = _driver()
    n = 0

    def side(*a: object, **k: object) -> dict:
        """Return side."""
        nonlocal n
        n += 1
        raise TransientDatabaseError(
            "maybe lost",
            sqlstate="08006",
            error_kind="connection_failure",
            retryable=True,
            commit_outcome_unknown=True,
        )

    with patch.object(postgres_mod, "run_execute", side_effect=side):
        with pytest.raises(TransientDatabaseError):
            d.execute("SELECT 1")
    assert n == 1
    d.conn.rollback.assert_called_once()


@patch.object(postgres_mod.time, "sleep", autospec=True)
def test_db_retry_log_line_includes_fields(_sleep: MagicMock, caplog) -> None:
    """Verify test db retry log line includes fields."""
    d = _driver()
    n = 0

    def side(*a: object, **k: object) -> dict:
        """Return side."""
        nonlocal n
        n += 1
        if n < 2:
            raise TransientDatabaseError(
                "deadlock",
                sqlstate="40P01",
                error_kind="deadlock",
            )
        return {"affected_rows": 0, "lastrowid": None, "data": None}

    with caplog.at_level(logging.INFO, logger=_LOG):
        with patch.object(postgres_mod, "run_execute", side_effect=side):
            d.execute("SELECT 1", transaction_id="local")

    found = [r for r in caplog.records if "[DB_RETRY]" in r.getMessage()]
    assert found, "expected a [DB_RETRY] log line"
    text = found[0].getMessage()
    assert "[DB_RETRY]" in text
    assert "backend=postgres" in text
    assert "layer=driver" in text
    assert "operation=execute" in text
    assert re.search(r"attempt=\d+/\d+", text)
    assert "sqlstate=40P01" in text
    assert "error_kind=deadlock" in text


@patch.object(postgres_mod.time, "sleep", autospec=True)
def test_rollback_fails_stops_with_driver_error(_sleep: MagicMock) -> None:
    """Verify test rollback fails stops with driver error."""
    d = _driver()
    n = 0

    def side(*a: object, **k: object) -> dict:
        """Return side."""
        nonlocal n
        n += 1
        if n < 2:
            raise TransientDatabaseError(
                "deadlock",
                sqlstate="40P01",
                error_kind="deadlock",
            )
        return {"affected_rows": 0, "lastrowid": None, "data": None}

    d.conn.rollback.side_effect = OSError("rb failed")
    with patch.object(postgres_mod, "run_execute", side_effect=side):
        with pytest.raises(DriverOperationError) as exc_info:
            d.execute("SELECT 1")
    assert "Rollback before database retry failed" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, OSError)
    assert n == 1
