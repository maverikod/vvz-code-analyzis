"""QA RPC ``qa_set_db_retry_injections`` (env-gated)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from code_analysis.core.database_client.protocol import RPCRequest
from code_analysis.core.database_driver_pkg.rpc_dispatch import process_rpc_request
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers


def test_qa_set_db_retry_injections_rpc_denied_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify test qa set db retry injections rpc denied without env."""
    monkeypatch.delenv("CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS", raising=False)
    driver = MagicMock()
    handlers = RPCHandlers(driver)
    resp = process_rpc_request(
        handlers,
        RPCRequest(
            method="qa_set_db_retry_injections",
            params={"remaining": 1},
            request_id="r1",
        ),
    )
    assert resp.error is not None
    driver.qa_set_db_retry_injections.assert_not_called()


def test_qa_set_db_retry_injections_rpc_ok_with_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify test qa set db retry injections rpc ok with env."""
    monkeypatch.setenv("CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS", "1")
    driver = MagicMock()
    driver.qa_set_db_retry_injections.return_value = {"success": True, "remaining": 1}
    handlers = RPCHandlers(driver)
    resp = process_rpc_request(
        handlers,
        RPCRequest(
            method="qa_set_db_retry_injections",
            params={"remaining": 2},
            request_id="r2",
        ),
    )
    assert resp.error is None
    assert resp.result is not None
    driver.qa_set_db_retry_injections.assert_called_once_with(2)
