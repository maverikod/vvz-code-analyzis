"""Unit tests for code_analysis_client (PyPI client package under client/)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis_client import CodeAnalysisAsyncClient
from code_analysis_client.config import (
    adapter_settings_from_server_config,
    adapter_settings_to_jsonrpc_kwargs,
)


def test_adapter_settings_https_includes_ssl_when_paths_present() -> None:
    """Verify test adapter settings https includes ssl when paths present."""
    cfg = {
        "server": {
            "host": "127.0.0.1",
            "port": 443,
            "protocol": "https",
            "ssl": {
                "cert": "/tmp/ca.crt",
                "key": "/tmp/ca.key",
                "ca": "/tmp/ca.pem",
            },
        }
    }
    settings = adapter_settings_from_server_config(cfg)
    assert "ssl" in settings
    assert settings["ssl"].get("cert")


def test_adapter_settings_bind_all_host_becomes_loopback() -> None:
    """Verify test adapter settings bind all host becomes loopback."""
    cfg = {"server": {"host": "0.0.0.0", "port": 15000, "protocol": "http"}}
    settings = adapter_settings_from_server_config(cfg)
    assert settings["host"] == "127.0.0.1"


def test_adapter_settings_to_jsonrpc_kwargs_mtls_paths() -> None:
    """Verify test adapter settings to jsonrpc kwargs mtls paths."""
    settings = {
        "protocol": "mtls",
        "host": "10.0.0.1",
        "port": 8443,
        "ssl": {
            "cert": "/tmp/c.crt",
            "key_path": "/tmp/k.key",
            "ca": "/tmp/ca.pem",
        },
    }
    kwargs = adapter_settings_to_jsonrpc_kwargs(settings, timeout=30.0)
    assert kwargs["protocol"] == "mtls"
    assert kwargs["host"] == "10.0.0.1"
    assert kwargs["port"] == 8443
    assert kwargs["timeout"] == 30.0
    assert kwargs["cert"].endswith("c.crt")
    assert kwargs["key"].endswith("k.key")
    assert kwargs["ca"].endswith("ca.pem")


@pytest.mark.asyncio
async def test_call_forwards_to_execute_command() -> None:
    """Verify test call forwards to execute command."""
    mock_rpc = MagicMock()
    mock_rpc.execute_command = AsyncMock(return_value={"ok": True})
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        out = await client.call("list_projects", {"include_deleted": True})
    assert out == {"ok": True}
    mock_rpc.execute_command.assert_awaited_once_with(
        "list_projects",
        {"include_deleted": True},
        use_cmd_endpoint=False,
    )


@pytest.mark.asyncio
async def test_context_manager_closes_rpc() -> None:
    """Verify test context manager closes rpc."""
    mock_rpc = MagicMock()
    mock_rpc.close = AsyncMock()
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        async with CodeAnalysisAsyncClient(host="h", port=1) as c:
            assert c.rpc is mock_rpc
    mock_rpc.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_call_validated_uses_help_schema_then_execute() -> None:
    """Verify test call validated uses help schema then execute."""
    schema = {
        "type": "object",
        "properties": {"include_deleted": {"type": "boolean"}},
        "required": [],
        "additionalProperties": False,
    }
    mock_rpc = MagicMock()
    mock_rpc.help = AsyncMock(
        return_value={"success": True, "data": {"schema": schema, "metadata": {}}}
    )
    mock_rpc.execute_command = AsyncMock(return_value={"ok": True})
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        out = await client.call_validated("list_projects", {"include_deleted": False})
    assert out == {"ok": True}
    mock_rpc.help.assert_awaited_once_with("list_projects")
    mock_rpc.execute_command.assert_awaited_once_with(
        "list_projects",
        {"include_deleted": False},
        use_cmd_endpoint=False,
    )


@pytest.mark.asyncio
async def test_call_validated_raises_when_required_missing() -> None:
    """Verify test call validated raises when required missing."""
    schema = {
        "type": "object",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
        "additionalProperties": False,
    }
    mock_rpc = MagicMock()
    mock_rpc.help = AsyncMock(
        return_value={"success": True, "data": {"schema": schema, "metadata": {}}}
    )
    mock_rpc.execute_command = AsyncMock()
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        from code_analysis_client import ClientValidationError

        with pytest.raises(ClientValidationError, match="required parameter"):
            await client.call_validated("universal_file_open", {})
    mock_rpc.execute_command.assert_not_called()


@pytest.mark.asyncio
async def test_call_validated_rejects_unknown_key() -> None:
    """Verify test call validated rejects unknown key."""
    schema = {
        "type": "object",
        "properties": {"include_deleted": {"type": "boolean"}},
        "required": [],
        "additionalProperties": False,
    }
    mock_rpc = MagicMock()
    mock_rpc.help = AsyncMock(
        return_value={"success": True, "data": {"schema": schema, "metadata": {}}}
    )
    mock_rpc.execute_command = AsyncMock()
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        from code_analysis_client import ClientValidationError

        with pytest.raises(ClientValidationError, match="unknown parameter"):
            await client.call_validated(
                "list_projects",
                {"include_deleted": False, "extra": 1},
            )
    mock_rpc.execute_command.assert_not_called()


def test_parse_schema_from_help_unknown_command() -> None:
    """Verify test parse schema from help unknown command."""
    from code_analysis_client import (
        ClientValidationError,
        parse_schema_from_help_payload,
    )

    with pytest.raises(ClientValidationError, match="not found"):
        parse_schema_from_help_payload(
            {
                "success": True,
                "data": {
                    "error": "Command 'nope' not found",
                },
            },
            command_name="nope",
        )


def test_validate_rejects_unknown_key_when_additional_properties_false() -> None:
    """Verify test validate rejects unknown key when additional properties false."""
    from code_analysis_client import (
        ClientValidationError,
        validate_params_against_schema,
    )

    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": [],
        "additionalProperties": False,
    }
    with pytest.raises(ClientValidationError, match="unknown parameter"):
        validate_params_against_schema({"a": 1, "b": 2}, schema, "cmd")


def test_validate_rejects_unknown_key_when_additional_properties_omitted() -> None:
    """Verify test validate rejects unknown key when additional properties omitted."""
    from code_analysis_client import (
        ClientValidationError,
        validate_params_against_schema,
    )

    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": [],
    }
    with pytest.raises(ClientValidationError, match="unknown parameter"):
        validate_params_against_schema({"a": 1, "b": 2}, schema, "cmd")


def test_prepare_params_for_schema_does_not_drop_unknown_keys() -> None:
    """Verify test prepare params for schema does not drop unknown keys."""
    from code_analysis_client import prepare_params_for_schema

    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": [],
        "additionalProperties": False,
    }
    params = {"a": 1, "b": 2}
    assert prepare_params_for_schema(params, schema) == params


def test_file_session_facade_maps_all_session_commands() -> None:
    """Verify test file session facade maps all session commands."""
    from code_analysis_client.server_api import assert_file_session_facade_complete

    assert_file_session_facade_complete()


def test_transfer_facade_maps_all_transfer_commands() -> None:
    """Verify test transfer facade maps all transfer commands."""
    from code_analysis_client.server_api import assert_transfer_facade_complete

    assert_transfer_facade_complete()


@pytest.mark.asyncio
async def test_file_session_delete_omits_force_when_false() -> None:
    """Verify test file session delete omits force when false."""
    mock_rpc = MagicMock()
    mock_rpc.help = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "force": {"type": "boolean", "default": False},
                    },
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
                "metadata": {},
            },
        }
    )
    mock_rpc.execute_command = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "session_id": "11111111-1111-4111-8111-111111111111",
                "deleted": True,
                "released_lock_count": 0,
                "released_subordinate_count": 0,
            },
        }
    )
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        out = await client.file_sessions.delete_session(
            "11111111-1111-4111-8111-111111111111"
        )
    assert out["deleted"] is True
    mock_rpc.execute_command.assert_awaited_once_with(
        "session_delete",
        {"session_id": "11111111-1111-4111-8111-111111111111"},
        use_cmd_endpoint=False,
    )


@pytest.mark.asyncio
async def test_file_session_view_calls_session_view() -> None:
    """Verify test file session view calls session view."""
    mock_rpc = MagicMock()
    mock_rpc.help = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "schema": {
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
                "metadata": {},
            },
        }
    )
    sid = "11111111-1111-4111-8111-111111111111"
    mock_rpc.execute_command = AsyncMock(
        return_value={
            "success": True,
            "data": {"session_id": sid, "locked_file_count": 0},
        }
    )
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        out = await client.file_sessions.view_session(sid)
    assert out["session_id"] == sid
    mock_rpc.execute_command.assert_awaited_once_with(
        "session_view",
        {"session_id": sid},
        use_cmd_endpoint=False,
    )


def test_examples_cover_all_public_client_api() -> None:
    """Verify test examples cover all public client api."""
    from pathlib import Path

    examples_dir = Path(__file__).resolve().parents[1] / "client" / "examples"
    # Import via path manipulation matching example scripts
    import sys

    client_dir = str(examples_dir.parent)
    if client_dir not in sys.path:
        sys.path.insert(0, client_dir)
    examples_path = str(examples_dir)
    if examples_path not in sys.path:
        sys.path.insert(0, examples_path)

    from _client_api_inventory import verify_examples_cover_client_api

    verify_examples_cover_client_api(examples_dir)
