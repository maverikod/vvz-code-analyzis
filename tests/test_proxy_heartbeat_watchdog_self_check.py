"""Tests for JSON-RPC route integrity checks in the proxy heartbeat watchdog."""

from __future__ import annotations

from code_analysis.core.proxy_heartbeat_watchdog import (
    _build_jsonrpc_self_check_payload,
    _jsonrpc_self_check_ok,
)


def test_jsonrpc_self_check_accepts_matching_response() -> None:
    """Matching JSON-RPC id and result shape is healthy."""
    payload = _build_jsonrpc_self_check_payload()
    response = {"jsonrpc": "2.0", "result": {"success": True}, "id": payload["id"]}

    assert _jsonrpc_self_check_ok(payload, response) is True


def test_jsonrpc_self_check_rejects_id_substitution() -> None:
    """A changed response id is a route/body corruption signal."""
    payload = _build_jsonrpc_self_check_payload()
    response = {"jsonrpc": "2.0", "result": {"success": True}, "id": 1}

    assert _jsonrpc_self_check_ok(payload, response) is False

