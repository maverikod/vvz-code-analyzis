"""``PostgreSQLDriver.qa_set_db_retry_injections`` env gate (stage-2 driver-prep).

The RPC handler (``handle_qa_set_db_retry_injections``) already pre-checks
``CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS`` before calling the driver (see
``tests/test_qa_rpc_db_retry_hooks.py``). This file verifies the driver method
now enforces the same gate itself, so a *direct* caller (bypassing the RPC
handler) cannot slip past it.
"""

from __future__ import annotations

import pytest

from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver
from code_analysis.core.database_driver_pkg.exceptions import DriverOperationError


def test_driver_rejects_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify test driver rejects when env unset."""
    monkeypatch.delenv("CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS", raising=False)
    d = PostgreSQLDriver()
    with pytest.raises(DriverOperationError) as exc_info:
        d.qa_set_db_retry_injections(1)
    assert "disabled" in str(exc_info.value)
    assert d._qa_transient_injections_remaining == 0


def test_driver_allows_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify test driver allows when env set."""
    monkeypatch.setenv("CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS", "1")
    d = PostgreSQLDriver()
    result = d.qa_set_db_retry_injections(3)
    assert result == {"success": True, "remaining": 3}
    assert d._qa_transient_injections_remaining == 3


def test_driver_still_validates_range_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify test driver still validates range when env set."""
    monkeypatch.setenv("CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS", "1")
    d = PostgreSQLDriver()
    with pytest.raises(DriverOperationError) as exc_info:
        d.qa_set_db_retry_injections(21)
    assert "between 0 and 20" in str(exc_info.value)
