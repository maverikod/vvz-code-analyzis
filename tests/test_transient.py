"""
Unit tests for transient failure classification and retry policy.

Covers is_rpc_connect_refused, is_sqlite_db_locked, compute_retry_delay,
format_retry_summary_suffix. Used by cst_save_tree retry logic.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import errno
from unittest.mock import patch

from code_analysis.core.database_client.transient import (
    MAX_DELAY_SECONDS,
    compute_retry_delay,
    format_retry_summary_suffix,
    is_rpc_connect_refused,
    is_sqlite_db_locked,
    is_structured_retryable_error,
)


class TestIsRpcConnectRefused:
    """is_rpc_connect_refused classifies connect-refused errors only."""

    def test_connection_refused_error_true(self) -> None:
        """ConnectionRefusedError is transient."""
        assert is_rpc_connect_refused(ConnectionRefusedError()) is True

    def test_connection_error_with_cause_errno_111_true(self) -> None:
        """ConnectionError with cause errno ECONNREFUSED is transient."""
        cause = OSError()
        cause.errno = errno.ECONNREFUSED
        exc = ConnectionError("failed")
        exc.__cause__ = cause
        assert is_rpc_connect_refused(exc) is True

    def test_message_connection_refused_true(self) -> None:
        """Exception message containing 'connection refused' is transient."""
        assert is_rpc_connect_refused(Exception("connection refused")) is True
        assert is_rpc_connect_refused(Exception("Connection Refused")) is True

    def test_message_errno_111_true(self) -> None:
        """Exception message containing 'errno 111' is transient."""
        assert is_rpc_connect_refused(Exception("errno 111")) is True

    def test_message_bracket_111_true(self) -> None:
        """Exception message containing ': 111]' is transient."""
        assert is_rpc_connect_refused(Exception("error: [something: 111]")) is True

    def test_other_connection_error_false(self) -> None:
        """ConnectionError without connect-refused semantics is not transient."""
        assert is_rpc_connect_refused(ConnectionError("timeout")) is False
        assert is_rpc_connect_refused(ConnectionError("other")) is False

    def test_other_exception_false(self) -> None:
        """Non-connection exceptions are not transient."""
        assert is_rpc_connect_refused(ValueError("x")) is False
        assert is_rpc_connect_refused(RuntimeError("y")) is False


class TestIsSqliteDbLocked:
    """is_sqlite_db_locked matches only lock/busy messages."""

    def test_database_is_locked_true(self) -> None:
        """'database is locked' matches."""
        assert is_sqlite_db_locked("database is locked") is True
        assert is_sqlite_db_locked("execute_batch failed: database is locked") is True

    def test_database_is_busy_true(self) -> None:
        """'database is busy' matches."""
        assert is_sqlite_db_locked("database is busy") is True

    def test_empty_false(self) -> None:
        """Empty string does not match."""
        assert is_sqlite_db_locked("") is False

    def test_foreign_key_false(self) -> None:
        """Non-lock SQL errors must not match (fail fast)."""
        assert is_sqlite_db_locked("FOREIGN KEY constraint failed") is False
        assert is_sqlite_db_locked("no such table") is False
        assert is_sqlite_db_locked("syntax error") is False


class TestComputeRetryDelay:
    """compute_retry_delay respects budget and jitter."""

    def test_first_retry_uses_initial_delay(self) -> None:
        """Attempt 1 uses initial delay (capped, with jitter)."""
        with patch(
            "code_analysis.core.database_client.transient.random.random",
            return_value=0.5,
        ):
            d = compute_retry_delay(1)
        # 0.2 * 2^0 = 0.2, jitter ±5% -> 0.19..0.21
        assert 0.18 <= d <= 0.22

    def test_delay_capped_by_max(self) -> None:
        """Delay is capped by MAX_DELAY_SECONDS."""
        with patch(
            "code_analysis.core.database_client.transient.random.random",
            return_value=0.5,
        ):
            d = compute_retry_delay(10)
        assert d <= MAX_DELAY_SECONDS + 0.1
        assert d >= 0.0

    def test_non_negative(self) -> None:
        """Delay is never negative."""
        with patch(
            "code_analysis.core.database_client.transient.random.random",
            return_value=0.0,
        ):
            d = compute_retry_delay(1)
        assert d >= 0.0


class TestIsStructuredRetryableError:
    """is_structured_retryable_error follows ErrorResult.details contract."""

    def test_true_when_retryable_and_no_unknown(self) -> None:
        """Verify test true when retryable and no unknown."""
        assert is_structured_retryable_error(
            {"retryable": True, "commit_outcome_unknown": False}
        )
        assert is_structured_retryable_error({"retryable": True}) is True

    def test_false_when_commit_outcome_unknown(self) -> None:
        """Verify test false when commit outcome unknown."""
        assert (
            is_structured_retryable_error(
                {
                    "retryable": True,
                    "commit_outcome_unknown": True,
                }
            )
            is False
        )

    def test_false_when_retryable_false(self) -> None:
        """Verify test false when retryable false."""
        assert is_structured_retryable_error({"retryable": False}) is False

    def test_false_when_missing_or_malformed(self) -> None:
        """Verify test false when missing or malformed."""
        assert is_structured_retryable_error(None) is False
        assert is_structured_retryable_error({}) is False
        assert is_structured_retryable_error("not a map") is False  # type: ignore[arg-type]

    def test_require_retryable_is_true(self) -> None:
        """Verify test require retryable is true."""
        assert is_structured_retryable_error({"retryable": 1}) is False


class TestFormatRetrySummarySuffix:
    """format_retry_summary_suffix produces contract message suffix."""

    def test_format(self) -> None:
        """Suffix format: ' (after N attempts, X.Xs total)'."""
        s = format_retry_summary_suffix(4, 1.4)
        assert s == " (after 4 attempts, 1.4s total)"

    def test_one_attempt(self) -> None:
        """One attempt and zero time."""
        s = format_retry_summary_suffix(1, 0.0)
        assert "1 attempts" in s and "0.0s" in s
