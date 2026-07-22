"""Unit tests for RPC full-transaction logical write retry.

The retry/transaction-orchestration loop lives on
``PostgreSQLDriver.execute_logical_write_operation`` (stage-2 driver-prep); the RPC
handler (``handle_execute_logical_write_operation``) now only validates params,
delegates to ``self.driver.execute_logical_write_operation``, and translates the
plain return value / raised exceptions back into ``SuccessResult`` / ``ErrorResult``.
``FakeLogicalWriteDriver`` below borrows the *real* driver method (instead of
re-implementing the loop) so these tests exercise the actual retry logic, driven
through the fake's own recorded primitives (``begin_transaction``, ``execute_batch``,
``commit_transaction``, ``rollback_transaction``).
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple
from unittest.mock import patch

import pytest

from code_analysis.core.database_client.protocol import (
    ErrorCode,
    ErrorResult,
    SuccessResult,
)
from code_analysis.core.database_driver_pkg.drivers import postgres as postgres_mod
from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver
from code_analysis.core.database_driver_pkg.exceptions import TransientDatabaseError
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers
from code_analysis.core.retry_policy import RetryPolicy

SqlBatch = list[tuple[str, Optional[tuple[Any, ...]]]]


def _batches_two() -> list[SqlBatch]:
    """Return batches two."""
    return [
        [("INSERT INTO a VALUES (?)", (1,))],
        [("INSERT INTO b VALUES (?)", (2,))],
    ]


def _batches_one() -> list[SqlBatch]:
    """Return batches one."""
    return [
        [("INSERT INTO t VALUES (?)", (1,))],
    ]


class FakeLogicalWriteDriver:
    """Records calls and simulates transients.

    ``execute_logical_write_operation`` is the real ``PostgreSQLDriver`` method
    (borrowed, not duplicated) run against this fake's own primitives, so
    ``_retry_policy`` must be set the same way the real driver sets it (from
    ``connect()``).
    """

    execute_logical_write_operation = PostgreSQLDriver.execute_logical_write_operation

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        """Initialize the instance."""
        self._retry_policy = policy if policy is not None else RetryPolicy()
        self.calls: list[tuple[str, ...]] = []
        self._session = 0
        self._batch_in_session = 0
        # Test hooks (set per test)
        self.fail_transient_on_batch2_session1: bool = False
        self.fail_transient_on_batch1_every_attempt: bool = False
        self.commit_outcome_unknown_once: bool = False
        self.rollback_raises_after_transient: bool = False
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
        if self.rollback_raises_after_transient and self._transient_raised:
            self._transient_raised = False
            raise RuntimeError("rollback failed")
        return True

    def acquire_project_lock(self, *args: Any, **kwargs: Any) -> None:
        """Return acquire project lock."""
        self.calls.append(("acquire_project_lock",))
        raise AssertionError("project activity lock must not be used in this step")


def _run_handler(
    driver: FakeLogicalWriteDriver,
    batches: list[SqlBatch],
    **extra: Any,
) -> SuccessResult | ErrorResult:
    """Return run handler."""
    params: dict[str, Any] = {
        "batches": [
            [
                {"sql": sql, "params": list(p) if p is not None else None}
                for sql, p in batch
            ]
            for batch in batches
        ]
    }
    params.update(extra)
    h = RPCHandlers(driver)  # type: ignore[arg-type]
    return h.handle_execute_logical_write_operation(params)


@patch.object(postgres_mod.time, "sleep")
def test_retry_replays_whole_transaction_from_beginning(
    _sleep: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify test retry replays whole transaction from beginning."""
    caplog.set_level(logging.INFO)
    d = FakeLogicalWriteDriver(
        policy=RetryPolicy(attempts=3, delay_seconds=0.0, jitter_seconds=0.0)
    )
    d.fail_transient_on_batch2_session1 = True
    b = _batches_two()
    r = _run_handler(d, b)
    assert isinstance(r, SuccessResult)
    assert r.data is not None
    assert "batch_results" in r.data
    assert len(d.calls) >= 2
    begins = [c for c in d.calls if c[0] == "begin_transaction"]
    assert len(begins) == 2, "second attempt must open a new transaction"
    rolls = [c for c in d.calls if c[0] == "rollback_transaction"]
    assert len(rolls) >= 1
    batch_calls = [c for c in d.calls if c[0] == "execute_batch"]
    # Session 1: batch1 (1 op), batch2 fails. Session 2: batch1, batch2
    # execute_batch (tid, batch_idx_in_session, n_ops)
    assert batch_calls[0][2] == 1
    assert batch_calls[1][2] == 2
    assert batch_calls[2][2] == 1
    assert batch_calls[3][2] == 2


@patch.object(postgres_mod.time, "sleep")
def test_retry_does_not_replay_only_failed_batch(
    _sleep: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify test retry does not replay only failed batch."""
    _ = caplog
    d = FakeLogicalWriteDriver(
        policy=RetryPolicy(attempts=3, delay_seconds=0.0, jitter_seconds=0.0)
    )
    d.fail_transient_on_batch2_session1 = True
    b = _batches_two()
    _ = _run_handler(d, b)
    batch_calls = [c for c in d.calls if c[0] == "execute_batch"]
    # After failed batch2 on session 1, session 2 must run batch1 before batch2
    assert batch_calls[2][2] == 1, "batch 1 must re-run before batch 2 on retry"
    assert batch_calls[2][1] == batch_calls[3][1], "same transaction for batch1+batch2"


def test_commit_outcome_unknown_is_not_retried() -> None:
    """Verify test commit outcome unknown is not retried."""
    d = FakeLogicalWriteDriver(
        policy=RetryPolicy(attempts=3, delay_seconds=0.0, jitter_seconds=0.0)
    )
    d.commit_outcome_unknown_once = True
    b = _batches_one()
    r = _run_handler(d, b)
    assert isinstance(r, ErrorResult)
    assert r.error_code == ErrorCode.DATABASE_ERROR
    assert r.details is not None
    assert r.details.get("commit_outcome_unknown") is True
    assert r.details.get("retryable") is False
    # Regression guard: the old handler always passed the CURRENT loop attempt
    # (attempt_1based), not whatever default TransientDatabaseError.attempts was;
    # this early-exit fires on the first attempt.
    assert r.details.get("attempts") == 1
    begins = [c for c in d.calls if c[0] == "begin_transaction"]
    assert len(begins) == 1
    rolls = [c for c in d.calls if c[0] == "rollback_transaction"]
    assert len(rolls) >= 1


@patch.object(postgres_mod.time, "sleep")
def test_exhausted_attempts_returns_structured_details(_sleep: Any) -> None:
    """Verify test exhausted attempts returns structured details."""
    d = FakeLogicalWriteDriver(
        policy=RetryPolicy(attempts=2, delay_seconds=0.0, jitter_seconds=0.0)
    )
    d.fail_transient_on_batch1_every_attempt = True
    b = _batches_one()
    r = _run_handler(d, b)
    assert isinstance(r, ErrorResult)
    assert r.error_code == ErrorCode.DATABASE_ERROR
    assert r.details is not None
    assert r.details.get("attempts") == 2
    assert r.details.get("sqlstate") == "40P01"
    assert r.details.get("error_kind") == "deadlock"
    assert r.details.get("retryable") is True
    assert r.details.get("commit_outcome_unknown") is False


@patch.object(postgres_mod.time, "sleep")
def test_operation_name_is_forwarded_to_error_details_and_logs(
    _sleep: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify test operation name is forwarded to error details and logs."""
    caplog.set_level(logging.INFO)
    d = FakeLogicalWriteDriver(
        policy=RetryPolicy(attempts=2, delay_seconds=0.0, jitter_seconds=0.0)
    )
    d.fail_transient_on_batch1_every_attempt = True
    b = _batches_one()
    r = _run_handler(d, b, operation_name="index_upsert")
    assert isinstance(r, ErrorResult)
    assert r.details is not None
    assert r.details.get("operation_name") == "index_upsert"
    joined = " ".join(rec.message for rec in caplog.records)
    assert "[DB_RETRY]" in joined
    assert "operation=execute_logical_write_operation" in joined
    assert "operation_name=index_upsert" in joined
    # The loop now runs on the driver, not the RPC handler.
    assert "layer=driver" in joined
    assert "backend=postgres" in joined


def test_project_id_and_lock_scope_are_metadata_only_in_this_step() -> None:
    """Verify test project id and lock scope are metadata only in this step."""
    d = FakeLogicalWriteDriver(
        policy=RetryPolicy(attempts=1, delay_seconds=0.0, jitter_seconds=0.0)
    )
    b = _batches_one()
    r = _run_handler(
        d,
        b,
        project_id="p1",
        lock_scope="project_read",
        operation_name="m",
    )
    assert isinstance(r, SuccessResult)
    assert r.data is not None
    meta = r.data.get("metadata")
    assert meta == {
        "operation_name": "m",
        "project_id": "p1",
        "lock_scope": "project_read",
    }
    # Metadata-only: handler must not call driver lock helpers (none exist on this fake).
    assert not any(c[0] == "acquire_project_lock" for c in d.calls)


@patch.object(postgres_mod.time, "sleep")
def test_rollback_failure_stops_retry(_sleep: Any) -> None:
    """Verify test rollback failure stops retry."""
    d = FakeLogicalWriteDriver(
        policy=RetryPolicy(attempts=3, delay_seconds=0.0, jitter_seconds=0.0)
    )
    d.fail_transient_on_batch1_every_attempt = True
    d.rollback_raises_after_transient = True
    b = _batches_one()
    r = _run_handler(d, b)
    assert isinstance(r, ErrorResult)
    assert "rollback failed" in r.description
    assert r.details is not None
    assert r.details.get("error_kind") == "rollback_failed"
    assert r.details.get("retryable") is False
    # Regression guard: the old handler's details dict always carried "attempts"
    # (the current loop's attempt_1based) and the BARE rollback exception's own
    # text in "message" (not the wrapped "rollback failed: ..." description).
    assert r.details.get("attempts") == 1
    assert r.details.get("message") == "rollback failed"
    begins = [c for c in d.calls if c[0] == "begin_transaction"]
    assert len(begins) == 1, "no further attempt after failed rollback"
