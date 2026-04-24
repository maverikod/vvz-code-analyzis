"""In-process RPC client and shared dispatch (PostgreSQL path uses same handlers)."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_client.protocol import RPCRequest
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_dispatch import process_rpc_request
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers


@pytest.fixture
def sqlite_handlers(tmp_path: Path) -> RPCHandlers:
    db_path = tmp_path / "t.db"
    driver = create_driver("sqlite", {"path": str(db_path)})
    schema = {
        "name": "t",
        "columns": [{"name": "id", "type": "INTEGER", "primary_key": True}],
    }
    driver.create_table(schema)
    return RPCHandlers(driver)


def test_process_rpc_request_unknown_method(sqlite_handlers: RPCHandlers) -> None:
    req = RPCRequest(method="no_such_method", params={}, request_id="r1")
    resp = process_rpc_request(sqlite_handlers, req)
    assert resp.is_error()
    assert resp.error is not None
    assert "Unknown method" in (resp.error.message or "")


def test_in_process_client_select_roundtrip(sqlite_handlers: RPCHandlers) -> None:
    client = InProcessRpcClient(sqlite_handlers)
    client.connect()
    try:
        from code_analysis.core.database_client.exceptions import RPCResponseError

        with pytest.raises(RPCResponseError):
            client.call(
                "select",
                {
                    "table_name": "missing_table",
                    "where": None,
                    "columns": None,
                    "limit": None,
                    "offset": None,
                    "order_by": None,
                },
            )
    finally:
        client.disconnect()


def test_in_process_client_success_path(sqlite_handlers: RPCHandlers) -> None:
    client = InProcessRpcClient(sqlite_handlers)
    client.connect()
    try:
        out = client.call(
            "select",
            {
                "table_name": "t",
                "where": None,
                "columns": ["id"],
                "limit": 10,
                "offset": None,
                "order_by": None,
            },
        )
        assert out.is_success()
        assert out.result is not None
    finally:
        client.disconnect()
