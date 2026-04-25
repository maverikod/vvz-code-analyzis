# Unit tests for structured PostgreSQL error classification (no live server).

from __future__ import annotations

from code_analysis.core.database_driver_pkg.drivers.postgres_run import (
    classify_postgres_error,
)
from code_analysis.core.database_driver_pkg.exceptions import (
    TransientDatabaseError,
    database_error_details,
)


def test_deadlock_sqlstate_is_retryable() -> None:
    exc = _FakePG(sqlstate="40P01", message="deadlock")
    info = classify_postgres_error(exc)
    assert info.error_kind == "deadlock"
    assert info.retryable is True
    assert info.commit_outcome_unknown is False


def test_serialization_failure_sqlstate_is_retryable() -> None:
    exc = _FakePG(sqlstate="40001", message="foo")
    info = classify_postgres_error(exc)
    assert info.error_kind == "serialization_failure"
    assert info.retryable is True
    assert info.commit_outcome_unknown is False


def test_lock_not_available_sqlstate_is_retryable() -> None:
    exc = _FakePG(sqlstate="55P03", message="foo")
    info = classify_postgres_error(exc)
    assert info.error_kind == "lock_not_available"
    assert info.retryable is True
    assert info.commit_outcome_unknown is False


def test_query_canceled_timeout_is_retryable() -> None:
    exc = _FakePG(
        sqlstate="57014",
        message="ERROR: canceling statement due to statement timeout",
    )
    info = classify_postgres_error(exc)
    assert info.error_kind == "query_canceled"
    assert info.retryable is True


def test_query_canceled_manual_cancel_is_not_retryable() -> None:
    exc = _FakePG(
        sqlstate="57014",
        message="canceling statement due to user request",
    )
    info = classify_postgres_error(exc)
    assert info.error_kind == "query_canceled"
    assert info.retryable is False


def test_unknown_sqlstate_is_not_retryable() -> None:
    exc = _FakePG(sqlstate="99999", message="mystery")
    info = classify_postgres_error(exc)
    assert info.error_kind == "postgres_error"
    assert info.retryable is False


def test_sqlstate_can_be_read_from_diag_fallback() -> None:
    exc = _FakePGDiag()
    assert getattr(exc, "sqlstate", None) is None
    assert getattr(getattr(exc, "diag", None), "sqlstate", None) == "40P01"
    info = classify_postgres_error(exc)
    assert info.error_kind == "deadlock"
    assert info.sqlstate == "40P01"


def test_transient_database_error_to_details_schema() -> None:
    t = TransientDatabaseError(
        "msg",
        sqlstate="40P01",
        error_kind="deadlock",
        attempts=1,
    )
    d = t.to_details(
        operation_name="watcher_ignore_purge",
        attempts=3,
    )
    assert set(d.keys()) == {
        "sqlstate",
        "error_kind",
        "retryable",
        "attempts",
        "operation_name",
        "commit_outcome_unknown",
    }
    assert d == {
        "sqlstate": "40P01",
        "error_kind": "deadlock",
        "retryable": True,
        "attempts": 3,
        "operation_name": "watcher_ignore_purge",
        "commit_outcome_unknown": False,
    }


def test_database_error_details_handles_transient_and_non_transient() -> None:
    t = TransientDatabaseError(
        "x",
        sqlstate="40P01",
        error_kind="deadlock",
    )
    d1 = database_error_details(t, operation_name="op", attempts=1)
    assert d1["retryable"] is True
    assert d1["error_kind"] == "deadlock"
    assert d1["commit_outcome_unknown"] is False

    nont = _FakePG(sqlstate="99999", message="m")
    d2 = database_error_details(nont, operation_name="p", attempts=2)
    assert d2["retryable"] is False
    assert d2["error_kind"] == "postgres_error"
    assert d2.get("message") is not None


class _FakePG:
    def __init__(self, sqlstate: str, message: str) -> None:
        self.sqlstate = sqlstate
        self._message = message

    def __str__(self) -> str:  # noqa: D105
        return self._message


class _FakePGDiag:
    def __init__(self) -> None:
        self.diag = _Diag()

    def __str__(self) -> str:  # noqa: D105
        return "deadlock"


class _Diag:
    sqlstate = "40P01"
