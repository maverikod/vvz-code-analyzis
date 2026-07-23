"""
Regression tests for bug c5e8fb49 (boot race).

Covers the shared-DB bootstrap bounded retry, the fail-loud process-exit path
taken once that retry is exhausted (daemon thread — a bare raise would not
restart the process), and the health-command visibility of an unavailable
shared DB. The deadlock-injection retry for ``ensure_postgres_schema`` lives
alongside the existing PostgreSQL retry-contract harness in
``tests/test_postgres_retry_contract_integration.py`` instead of here.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis import main_app_events
from code_analysis.core import shared_database
from code_analysis.core.retry_policy import RetryPolicy

_LOGGER = logging.getLogger("test.boot_race_c5e8fb49")


# ---------------------------------------------------------------------------
# (b) bootstrap retry: _bootstrap_with_retry + shared_database round-trip
# ---------------------------------------------------------------------------


def test_bootstrap_with_retry_succeeds_after_transient_failures() -> None:
    """attempt_fn failing N-1 times then succeeding -> returns None, called N times."""
    calls = {"n": 0}

    def flaky() -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("db not ready yet")

    policy = RetryPolicy(
        attempts=5, delay_seconds=0.0, backoff_multiplier=1.0, jitter_seconds=0.0
    )
    sleeps: list[float] = []
    last_exc = main_app_events._bootstrap_with_retry(
        flaky,
        retry_policy=policy,
        logger=_LOGGER,
        operation_name="test_op",
        sleep_fn=sleeps.append,
    )
    assert last_exc is None
    assert calls["n"] == 3
    assert len(sleeps) == 2, "one sleep between each of the two failed attempts"


def test_bootstrap_with_retry_returns_last_exception_after_exhaustion() -> None:
    """attempt_fn always failing -> returns the last exception, called exactly N times."""
    calls = {"n": 0}

    def always_fails() -> None:
        calls["n"] += 1
        raise ConnectionError(f"still down (attempt {calls['n']})")

    policy = RetryPolicy(
        attempts=4, delay_seconds=0.0, backoff_multiplier=1.0, jitter_seconds=0.0
    )
    last_exc = main_app_events._bootstrap_with_retry(
        always_fails,
        retry_policy=policy,
        logger=_LOGGER,
        operation_name="test_op",
        sleep_fn=lambda _s: None,
    )
    assert calls["n"] == policy.attempts == 4
    assert isinstance(last_exc, ConnectionError)
    assert "attempt 4" in str(last_exc)


def test_bootstrap_retry_then_set_shared_database_succeeds() -> None:
    """Bug c5e8fb49 (b): open stubbed to raise N-1 times then succeed; shared DB ends up set
    and get_shared_database() works (bootstrap_impl -> set_shared_database -> retry composition).
    """
    shared_database.close_shared_database()
    calls = {"n": 0}
    fake_db = object()

    def fake_open_database_from_config_impl_then_set() -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("db not ready yet")
        # Mirrors _open_and_set_shared_database_once's own call to set_shared_database.
        shared_database.set_shared_database(fake_db)

    policy = RetryPolicy(
        attempts=5, delay_seconds=0.0, backoff_multiplier=1.0, jitter_seconds=0.0
    )
    try:
        last_exc = main_app_events._bootstrap_with_retry(
            fake_open_database_from_config_impl_then_set,
            retry_policy=policy,
            logger=_LOGGER,
            operation_name="open_shared_database",
            sleep_fn=lambda _s: None,
        )
        assert last_exc is None
        assert calls["n"] == 3
        # get_shared_database() must work now (no SharedDatabaseNotInitializedError).
        proxy = shared_database.get_shared_database()
        assert proxy is not None
        assert shared_database.is_shared_database_current_process() is True
    finally:
        shared_database.close_shared_database()


# ---------------------------------------------------------------------------
# (c) exhaustion -> fail-loud path
# ---------------------------------------------------------------------------


def test_fail_loud_shared_database_bootstrap_calls_exit_fn() -> None:
    """Bug c5e8fb49 (c): the fail-loud path calls exit_fn(1) — never a bare raise."""
    exit_calls: list[int] = []

    main_app_events._fail_loud_shared_database_bootstrap(
        RuntimeError("db permanently down"),
        _LOGGER,
        max_attempts=5,
        exit_fn=exit_calls.append,
    )
    assert exit_calls == [1]


def test_bootstrap_exhaustion_triggers_fail_loud_end_to_end() -> None:
    """Bug c5e8fb49 (c): full composition — retry exhausts, then fail-loud fires exit_fn(1)."""
    calls = {"n": 0}

    def always_fails() -> None:
        calls["n"] += 1
        raise ConnectionError("db still down")

    policy = RetryPolicy(
        attempts=3, delay_seconds=0.0, backoff_multiplier=1.0, jitter_seconds=0.0
    )
    last_exc = main_app_events._bootstrap_with_retry(
        always_fails,
        retry_policy=policy,
        logger=_LOGGER,
        operation_name="open_shared_database",
        sleep_fn=lambda _s: None,
    )
    assert calls["n"] == 3
    assert last_exc is not None

    exit_calls: list[int] = []
    main_app_events._fail_loud_shared_database_bootstrap(
        last_exc,
        _LOGGER,
        max_attempts=policy.attempts,
        exit_fn=exit_calls.append,
    )
    assert exit_calls == [1]


def test_fail_loud_default_exit_fn_is_os_exit() -> None:
    """The production default really is os._exit (not sys.exit/raise) — see docstring
    on _fail_loud_shared_database_bootstrap for why (daemon-thread fail-fast).
    """
    import os

    assert main_app_events._fail_loud_shared_database_bootstrap.__kwdefaults__[
        "exit_fn"
    ] is os._exit


# ---------------------------------------------------------------------------
# (d) health reflects unavailable / available shared DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_reports_database_error_when_shared_db_unavailable() -> None:
    """Bug c5e8fb49 (d): health must not report ok while the shared DB is unset."""
    from code_analysis.commands.health_command import HealthCommand

    shared_database.close_shared_database()
    result = await HealthCommand().execute()
    assert isinstance(result, SuccessResult)
    assert result.data["components"]["shared_database"] == {"status": "unavailable"}
    assert result.data["status"] == "database_error"


@pytest.mark.asyncio
async def test_health_reports_ok_shared_db_when_set() -> None:
    """Bug c5e8fb49 (d): health reflects a shared DB that IS set as ok."""
    from code_analysis.commands.health_command import HealthCommand

    shared_database.set_shared_database(object())
    try:
        result = await HealthCommand().execute()
        assert result.data["components"]["shared_database"] == {"status": "ok"}
        assert result.data["status"] != "database_error"
    finally:
        shared_database.close_shared_database()


def test_shared_database_status_helper_matches_process_membership() -> None:
    """shared_database_status() is a thin, direct read of is_shared_database_current_process()."""
    shared_database.close_shared_database()
    try:
        assert shared_database.shared_database_status() == "unavailable"
        shared_database.set_shared_database(object())
        assert shared_database.shared_database_status() == "ok"
    finally:
        shared_database.close_shared_database()
    assert shared_database.shared_database_status() == "unavailable"
