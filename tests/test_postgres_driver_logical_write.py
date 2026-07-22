"""Unit tests for ``PostgreSQLDriver.execute_logical_write_operation`` (stage-2 driver-prep).

Exercises the retry/transaction-orchestration loop directly on the driver (moved
here from the RPC handler, which now delegates to it). Verifies retry policy is
sourced from ``self._retry_policy`` and that the method returns the unwrapped
success payload / raises on failure, matching every other driver method's
convention (no RPC Result envelope at this layer).
"""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_driver_pkg.drivers import postgres as postgres_mod
from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver
from code_analysis.core.database_driver_pkg.exceptions import (
    DriverOperationError,
    TransientDatabaseError,
)
from code_analysis.core.database.logical_write_program import LogicalWriteProgramV1
from code_analysis.core.retry_policy import RetryPolicy


def _driver(policy: RetryPolicy) -> PostgreSQLDriver:
    """Return a bare PostgreSQLDriver with only ``_retry_policy`` set (no connect())."""
    d = PostgreSQLDriver()
    d._retry_policy = policy
    return d


def _program(**kwargs: Any) -> LogicalWriteProgramV1:
    """Return a minimal one-batch LogicalWriteProgramV1, overridable via kwargs."""
    program: dict[str, Any] = {
        "batches": [[("INSERT INTO t VALUES (?)", (1,))]],
    }
    program.update(kwargs)
    return program  # type: ignore[return-value]


def test_retry_policy_sourced_from_retry_policy_attribute_only() -> None:
    """The two dead RPC-only attributes must play no role; only ``_retry_policy`` does."""
    d = _driver(RetryPolicy(attempts=1, delay_seconds=0.0, jitter_seconds=0.0))
    assert not hasattr(d, "_write_retry_policy")
    assert not hasattr(d, "_driver_config")
    d.begin_transaction = MagicMock(return_value="tid1")  # type: ignore[method-assign]
    d.execute_batch = MagicMock(  # type: ignore[method-assign]
        return_value=[{"affected_rows": 1, "lastrowid": None, "data": None}]
    )
    d.commit_transaction = MagicMock(return_value=True)  # type: ignore[method-assign]
    d.rollback_transaction = MagicMock(return_value=True)  # type: ignore[method-assign]

    result = d.execute_logical_write_operation(_program())

    assert result["transaction_id"] == "tid1"
    assert result["batch_results"] == [
        {"results": [{"affected_rows": 1, "lastrowid": None, "data": None}]}
    ]
    assert result["metadata"] == {
        "operation_name": None,
        "project_id": None,
        "lock_scope": "none",
    }
    d.begin_transaction.assert_called_once()
    d.commit_transaction.assert_called_once_with("tid1")
    d.rollback_transaction.assert_not_called()


def test_success_return_shape_is_unwrapped_plain_dict() -> None:
    """No SuccessResult/ErrorResult envelope at the driver layer."""
    d = _driver(RetryPolicy(attempts=1, delay_seconds=0.0, jitter_seconds=0.0))
    d.begin_transaction = MagicMock(return_value="tid1")  # type: ignore[method-assign]
    d.execute_batch = MagicMock(return_value=[])  # type: ignore[method-assign]
    d.commit_transaction = MagicMock(return_value=True)  # type: ignore[method-assign]
    d.rollback_transaction = MagicMock(return_value=True)  # type: ignore[method-assign]

    result = d.execute_logical_write_operation(
        _program(operation_name="op1", project_id="proj1", lock_scope="project_write")
    )

    assert isinstance(result, dict)
    assert set(result.keys()) == {"batch_results", "transaction_id", "metadata"}
    assert result["metadata"] == {
        "operation_name": "op1",
        "project_id": "proj1",
        "lock_scope": "project_write",
    }


@patch.object(postgres_mod.time, "sleep")
def test_transient_retried_then_succeeds(_sleep: MagicMock) -> None:
    """A retryable transient on attempt 1 opens a fresh transaction and retries."""
    d = _driver(RetryPolicy(attempts=3, delay_seconds=0.0, jitter_seconds=0.0))
    tids = iter(["tid1", "tid2"])
    d.begin_transaction = MagicMock(side_effect=lambda: next(tids))  # type: ignore[method-assign]
    n = 0

    def batch_side(operations: Any, transaction_id: Optional[str]) -> list:
        """Fail transient on the first attempt only."""
        nonlocal n
        n += 1
        if n == 1:
            raise TransientDatabaseError(
                "deadlock", sqlstate="40P01", error_kind="deadlock", retryable=True
            )
        return [{"affected_rows": 1, "lastrowid": None, "data": None}]

    d.execute_batch = MagicMock(side_effect=batch_side)  # type: ignore[method-assign]
    d.commit_transaction = MagicMock(return_value=True)  # type: ignore[method-assign]
    d.rollback_transaction = MagicMock(return_value=True)  # type: ignore[method-assign]

    result = d.execute_logical_write_operation(_program())

    assert result["transaction_id"] == "tid2"
    assert d.begin_transaction.call_count == 2
    d.rollback_transaction.assert_called_once_with("tid1")


@patch.object(postgres_mod.time, "sleep")
def test_exhausted_retries_raises_transient_with_final_attempts(
    _sleep: MagicMock,
) -> None:
    """Mirrors ``_run_self_managed_with_retry``: rebuild with attempts=max_attempts."""
    d = _driver(RetryPolicy(attempts=2, delay_seconds=0.0, jitter_seconds=0.0))
    d.begin_transaction = MagicMock(return_value="tid1")  # type: ignore[method-assign]
    d.execute_batch = MagicMock(  # type: ignore[method-assign]
        side_effect=TransientDatabaseError(
            "deadlock", sqlstate="40P01", error_kind="deadlock", retryable=True
        )
    )
    d.commit_transaction = MagicMock(return_value=True)  # type: ignore[method-assign]
    d.rollback_transaction = MagicMock(return_value=True)  # type: ignore[method-assign]

    with pytest.raises(TransientDatabaseError) as exc_info:
        d.execute_logical_write_operation(_program())
    assert exc_info.value.attempts == 2
    assert d.begin_transaction.call_count == 2


def test_commit_outcome_unknown_not_retried() -> None:
    """commit_outcome_unknown must abort immediately, not retry."""
    d = _driver(RetryPolicy(attempts=3, delay_seconds=0.0, jitter_seconds=0.0))
    d.begin_transaction = MagicMock(return_value="tid1")  # type: ignore[method-assign]
    d.execute_batch = MagicMock(return_value=[])  # type: ignore[method-assign]
    d.commit_transaction = MagicMock(  # type: ignore[method-assign]
        side_effect=TransientDatabaseError(
            "commit unknown",
            sqlstate="08006",
            error_kind="connection_failure",
            retryable=False,
            commit_outcome_unknown=True,
        )
    )
    d.rollback_transaction = MagicMock(return_value=True)  # type: ignore[method-assign]

    with pytest.raises(TransientDatabaseError) as exc_info:
        d.execute_logical_write_operation(_program())
    assert exc_info.value.commit_outcome_unknown is True
    assert d.begin_transaction.call_count == 1
    # Regression guard: rebuilt with the current loop's attempt_1based (1 here),
    # not left at the raiser's default (unset -> None) -- see
    # _transient_with_attempts and its use in the commit_outcome_unknown branch.
    assert exc_info.value.attempts == 1


@patch.object(postgres_mod.time, "sleep")
def test_rollback_failure_after_transient_raises_driver_operation_error(
    _sleep: MagicMock,
) -> None:
    """A rollback failure after a transient stops retrying and raises DriverOperationError."""
    d = _driver(RetryPolicy(attempts=3, delay_seconds=0.0, jitter_seconds=0.0))
    d.begin_transaction = MagicMock(return_value="tid1")  # type: ignore[method-assign]
    d.execute_batch = MagicMock(  # type: ignore[method-assign]
        side_effect=TransientDatabaseError(
            "deadlock", sqlstate="40P01", error_kind="deadlock", retryable=True
        )
    )
    d.commit_transaction = MagicMock(return_value=True)  # type: ignore[method-assign]
    d.rollback_transaction = MagicMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("rollback boom")
    )

    with pytest.raises(DriverOperationError) as exc_info:
        d.execute_logical_write_operation(_program())
    assert "rollback failed" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert d.begin_transaction.call_count == 1, "no further attempt after failed rollback"
    # Regression guard: the attempt count is attached dynamically (no static field
    # on DriverOperationError) so the RPC handler can forward it in ErrorResult.details.
    assert getattr(exc_info.value, "attempts", None) == 1


def test_empty_batches_raises_value_error() -> None:
    """Mirrors the client's own ``execute_logical_write_operation`` guard."""
    d = _driver(RetryPolicy(attempts=1, delay_seconds=0.0, jitter_seconds=0.0))
    with pytest.raises(ValueError):
        d.execute_logical_write_operation({"batches": []})  # type: ignore[typeddict-item]


def test_invalid_operation_name_type_raises_value_error() -> None:
    """Restored from the deleted RPC boundary (``rpc_handlers_schema``, fc4dde4b):
    a non-string, non-null ``operation_name`` must fail loud before opening a
    transaction."""
    d = _driver(RetryPolicy(attempts=1, delay_seconds=0.0, jitter_seconds=0.0))
    d.begin_transaction = MagicMock(  # type: ignore[method-assign]
        side_effect=AssertionError("must not open a transaction on validation failure")
    )
    with pytest.raises(ValueError, match="operation_name"):
        d.execute_logical_write_operation(_program(operation_name=123))  # type: ignore[arg-type]
    d.begin_transaction.assert_not_called()


def test_invalid_project_id_type_raises_value_error() -> None:
    """Restored from the deleted RPC boundary (``rpc_handlers_schema``, fc4dde4b):
    a non-string, non-null ``project_id`` must fail loud before opening a
    transaction."""
    d = _driver(RetryPolicy(attempts=1, delay_seconds=0.0, jitter_seconds=0.0))
    d.begin_transaction = MagicMock(  # type: ignore[method-assign]
        side_effect=AssertionError("must not open a transaction on validation failure")
    )
    with pytest.raises(ValueError, match="project_id"):
        d.execute_logical_write_operation(_program(project_id=456))  # type: ignore[arg-type]
    d.begin_transaction.assert_not_called()


def test_invalid_lock_scope_raises_value_error() -> None:
    """Restored from the deleted RPC boundary (``rpc_handlers_schema``, fc4dde4b):
    a ``lock_scope`` outside {none, project_write, project_read} must fail loud
    before opening a transaction."""
    d = _driver(RetryPolicy(attempts=1, delay_seconds=0.0, jitter_seconds=0.0))
    d.begin_transaction = MagicMock(  # type: ignore[method-assign]
        side_effect=AssertionError("must not open a transaction on validation failure")
    )
    with pytest.raises(ValueError, match="lock_scope"):
        d.execute_logical_write_operation(_program(lock_scope="invalid"))  # type: ignore[arg-type]
    d.begin_transaction.assert_not_called()
