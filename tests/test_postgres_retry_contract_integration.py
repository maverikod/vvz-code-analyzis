"""Integration-style checks for the PostgreSQL retry contract."""

# PostgreSQL retry contract: integration-style checks (optional live DSN + fakes).
#
# ErrorResult uses ``details`` for structured fields (``wire_result.ErrorResult``),
# not a ``data`` field on errors.

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_driver_pkg.drivers import postgres as postgres_mod
from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver
from code_analysis.core.database_driver_pkg.drivers.postgres_run import (
    _raise_classified,
    classify_postgres_error,
)
from code_analysis.core.database_driver_pkg.exceptions import TransientDatabaseError
from code_analysis.core.retry_policy import RetryPolicy

_PG_ENV = "CODE_ANALYSIS_POSTGRES_TEST_DSN"
# Shared skip reason: must stay explicit (used by skipif and documented by test 1).
_PG_SKIP_REASON = (
    f"PostgreSQL integration: {_PG_ENV} is not set or empty; "
    "set it to a test database DSN to run live-DSN contract checks"
)

_LOG_DRIVER = "code_analysis.core.database_driver_pkg.drivers.postgres"
SqlBatch = list[tuple[str, Optional[tuple[Any, ...]]]]


def _pg_dsn() -> str:
    """Return pg dsn."""
    return (os.environ.get(_PG_ENV) or "").strip()


def _batches_one() -> list[SqlBatch]:
    """Return batches one."""
    return [
        [("INSERT INTO t VALUES (?)", (1,))],
    ]


def _batches_two() -> list[SqlBatch]:
    """Return batches two."""
    return [
        [("INSERT INTO a VALUES (?)", (1,))],
        [("INSERT INTO b VALUES (?)", (2,))],
    ]


class FakeLogicalWriteDriver:
    """Simulates execute_batch / commit for logical-write RPC path.

    ``execute_logical_write_operation`` is the real ``PostgreSQLDriver`` method
    (borrowed, not duplicated); the retry loop now lives on the driver, and the
    RPC handler delegates to it (stage-2 driver-prep).
    """

    execute_logical_write_operation = PostgreSQLDriver.execute_logical_write_operation

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        """Initialize the instance."""
        self._retry_policy = policy if policy is not None else RetryPolicy()
        self.calls: list[tuple[str, ...]] = []
        self._session = 0
        self._batch_in_session = 0
        self.fail_transient_on_batch2_session1: bool = False
        self.fail_transient_on_batch1_every_attempt: bool = False
        self.commit_outcome_unknown_once: bool = False
        self._transient_raised: bool = False
        self._rows = [{"affected_rows": 1, "lastrowid": None, "data": None}]

    def begin_transaction(self) -> str:
        """Return begin transaction."""
        self._session += 1
        self._batch_in_session = 0
        tid = f"tid{self._session}"
        self.calls.append(("begin_transaction", tid))
        return tid

    def execute(
        self, sql: str, params: Any, transaction_id: Optional[str]
    ) -> dict[str, Any]:
        """Execute the command."""
        self.calls.append(("execute", sql, transaction_id))
        return {"affected_rows": 0, "lastrowid": None, "data": None}

    def execute_batch(
        self,
        operations: list[tuple[str, Optional[tuple]]],
        transaction_id: Optional[str],
    ) -> list[dict[str, Any]]:
        """Return execute batch."""
        self._batch_in_session += 1
        n = len(operations)
        self.calls.append(("execute_batch", transaction_id, self._batch_in_session, n))
        if self.fail_transient_on_batch1_every_attempt:
            self._transient_raised = True
            raise TransientDatabaseError(
                "transient",
                sqlstate="40P01",
                error_kind="deadlock",
                retryable=True,
            )
        if (
            self.fail_transient_on_batch2_session1
            and self._session == 1
            and self._batch_in_session == 2
        ):
            self._transient_raised = True
            raise TransientDatabaseError(
                "deadlock on batch2",
                sqlstate="40P01",
                error_kind="deadlock",
                retryable=True,
            )
        return list(self._rows) * n if n else []

    def commit_transaction(self, transaction_id: str) -> bool:
        """Return commit transaction."""
        self.calls.append(("commit_transaction", transaction_id))
        if self.commit_outcome_unknown_once and self._session == 1:
            raise TransientDatabaseError(
                "commit unknown",
                sqlstate="08006",
                error_kind="connection_failure",
                retryable=False,
                commit_outcome_unknown=True,
            )
        return True

    def rollback_transaction(self, transaction_id: str) -> bool:
        """Return rollback transaction."""
        self.calls.append(("rollback_transaction", transaction_id))
        return True

    def acquire_project_lock(self, *args: Any, **kwargs: Any) -> None:
        """Return acquire project lock."""
        self.calls.append(("acquire_project_lock",))
        raise AssertionError("project activity lock must not be used in this test")


def _run_logical_write(
    driver: FakeLogicalWriteDriver,
    batches: list[SqlBatch],
    **extra: Any,
) -> dict[str, Any]:
    """Call the driver directly (stage 2: no RPC handler / wire envelope).

    ``execute_logical_write_operation`` takes ``LogicalWriteProgramV1`` in its
    native shape (batches of ``(sql, params)`` tuples); returns the unwrapped
    success payload or raises (``TransientDatabaseError`` /
    ``DriverOperationError``) - see ``PostgreSQLDriver.execute_logical_write_operation``.
    """
    program: dict[str, Any] = {"batches": batches}
    program.update(extra)
    return driver.execute_logical_write_operation(program)  # type: ignore[arg-type]


def _pg_driver() -> PostgreSQLDriver:
    """Return pg driver."""
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
    return d


def test_postgres_config_missing_skips_with_explicit_reason() -> None:
    """Skip reason is explicit; mandatory Step 20 unit tests are unaffected by this file."""
    assert _PG_ENV in _PG_SKIP_REASON
    assert "DSN" in _PG_SKIP_REASON or "dsn" in _PG_SKIP_REASON
    assert len(_PG_SKIP_REASON) > 40


@pytest.mark.skipif(
    not _pg_dsn(),
    reason=_PG_SKIP_REASON,
)
def test_postgres_sqlstate_survives_to_transient_error() -> None:
    """Verify test postgres sqlstate survives to transient error."""
    import psycopg
    from psycopg import errors

    dsn = _pg_dsn()
    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT 1")

    exc = errors.DeadlockDetected("deadlock")
    with pytest.raises(TransientDatabaseError) as raised:
        _raise_classified(exc, for_commit=False, message_prefix="x: ")
    t = raised.value
    assert t.sqlstate == "40P01"
    assert t.error_kind == "deadlock"
    assert t.retryable is True
    assert t.commit_outcome_unknown is False


@patch.object(postgres_mod.time, "sleep")
def test_postgres_rpc_error_result_has_structured_details(
    _sleep: Any,
) -> None:
    """Verify test postgres rpc error result has structured details."""
    d = FakeLogicalWriteDriver(
        policy=RetryPolicy(attempts=1, delay_seconds=0.0, jitter_seconds=0.0)
    )
    d.fail_transient_on_batch1_every_attempt = True
    with pytest.raises(TransientDatabaseError) as raised:
        _run_logical_write(d, _batches_one())
    details = raised.value.to_details()
    for key in (
        "sqlstate",
        "error_kind",
        "retryable",
        "attempts",
        "commit_outcome_unknown",
    ):
        assert key in details, f"missing {key} in TransientDatabaseError.to_details(): {details!r}"


@patch.object(postgres_mod.time, "sleep")
def test_postgres_retry_log_has_required_fields(
    _sleep: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify test postgres retry log has required fields."""
    caplog.set_level(logging.INFO, logger=_LOG_DRIVER)
    d = FakeLogicalWriteDriver(
        policy=RetryPolicy(attempts=2, delay_seconds=0.0, jitter_seconds=0.0)
    )
    d.fail_transient_on_batch2_session1 = True
    b = _batches_two()
    r = _run_logical_write(d, b)
    assert "batch_results" in r and "transaction_id" in r
    found = [r for r in caplog.records if "[DB_RETRY]" in r.getMessage()]
    assert found, "expected [DB_RETRY] log line on first transient before retry"
    text = found[0].getMessage()
    assert "backend=postgres" in text
    # The loop now runs on the driver, not the RPC handler.
    assert "layer=driver" in text
    assert "operation=execute_logical_write_operation" in text
    assert re.search(r"attempt=\d+/\d+", text)
    assert "sqlstate=40P01" in text
    assert "error_kind=deadlock" in text


def test_postgres_timeout_57014_policy() -> None:
    """Verify test postgres timeout 57014 policy."""

    def _exc_57014(msg: str) -> Exception:
        """Return exc 57014."""
        e = Exception(msg)
        e.sqlstate = "57014"  # type: ignore[attr-defined]
        return e

    t_out = _exc_57014("canceling statement due to statement timeout")
    info_to = classify_postgres_error(t_out)
    assert info_to.sqlstate == "57014"
    assert info_to.retryable is True

    ext_cancel = _exc_57014("canceling statement due to user request")
    info_c = classify_postgres_error(ext_cancel)
    assert info_c.sqlstate == "57014"
    assert info_c.retryable is False


@patch.object(postgres_mod.time, "sleep", autospec=True)
def test_postgres_external_transaction_not_retried_by_driver(
    _sleep: MagicMock,
) -> None:
    """Verify test postgres external transaction not retried by driver."""
    d = _pg_driver()
    d._transaction_manager = MagicMock()
    ext = MagicMock()
    d._transaction_manager._transactions = {"ext-tx": ext}
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


@patch.object(postgres_mod.time, "sleep")
def test_postgres_commit_outcome_unknown_not_retried(
    _sleep: Any,
) -> None:
    """Verify test postgres commit outcome unknown not retried."""
    d = FakeLogicalWriteDriver(
        policy=RetryPolicy(attempts=3, delay_seconds=0.0, jitter_seconds=0.0)
    )
    d.commit_outcome_unknown_once = True
    b = _batches_one()
    with pytest.raises(TransientDatabaseError) as raised:
        _run_logical_write(d, b)
    details = raised.value.to_details()
    assert details.get("commit_outcome_unknown") is True
    assert details.get("retryable") is False
    assert details.get("attempts") == 1
    begins = [c for c in d.calls if c[0] == "begin_transaction"]
    assert len(begins) == 1
