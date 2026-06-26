"""
In-process tests for subordinate session MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

import code_analysis.hooks  # noqa: F401
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.command_metadata_helpers import REQUIRED_METADATA_KEYS
from code_analysis.commands.sessions.subordinate_session_commands import (
    SubordinateSessionCreateCommand,
    SubordinateSessionDeleteCommand,
    SubordinateSessionGetCommand,
    SubordinateSessionListCommand,
    SubordinateSessionUpdateCommand,
)

_SUBORDINATE_COMMANDS = (
    ("subordinate_session_create", SubordinateSessionCreateCommand),
    ("subordinate_session_get", SubordinateSessionGetCommand),
    ("subordinate_session_update", SubordinateSessionUpdateCommand),
    ("subordinate_session_delete", SubordinateSessionDeleteCommand),
    ("subordinate_session_list", SubordinateSessionListCommand),
)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _register_subordinate_commands() -> None:
    """Return register subordinate commands."""
    hooks.execute_custom_commands_hooks(registry)


@pytest.mark.parametrize("name,expected_cls", _SUBORDINATE_COMMANDS)
def test_subordinate_commands_registered(name: str, expected_cls: type) -> None:
    """Verify test subordinate commands registered."""
    cls = registry.get_command(name)
    assert cls is expected_cls
    assert cls.category == "session_management"


@pytest.mark.parametrize("name,expected_cls", _SUBORDINATE_COMMANDS)
def test_subordinate_command_metadata(name: str, expected_cls: type) -> None:
    """Verify test subordinate command metadata."""
    cls = registry.get_command(name)
    meta = cls.metadata()
    for key in REQUIRED_METADATA_KEYS:
        assert key in meta, f"{name}: missing metadata key {key!r}"
    schema_props = set((cls.get_schema().get("properties") or {}).keys())
    assert set(meta.get("parameters") or {}) == schema_props


@pytest.mark.asyncio
async def test_subordinate_session_create_execute() -> None:
    """Verify test subordinate session create execute."""
    row = {
        "parent_session_id": "11111111-1111-4111-8111-111111111111",
        "server_uuid": "880e8400-e29b-41d4-a716-446655440003",
        "comment": "worker",
    }
    mock_db = MagicMock()
    config = {"registration": {"instance_uuid": row["server_uuid"]}}
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch.object(BaseMCPCommand, "_get_raw_config", return_value=config),
        patch(
            "code_analysis.commands.sessions.subordinate_session_commands.create_subordinate_session",
            return_value=row,
        ) as create_fn,
    ):
        cmd = SubordinateSessionCreateCommand()
        result = await cmd.execute(
            parent_session_id=row["parent_session_id"],
            comment="worker",
        )

    assert isinstance(result, SuccessResult)
    create_fn.assert_called_once_with(
        mock_db,
        parent_session_id=row["parent_session_id"],
        server_uuid=row["server_uuid"],
        comment="worker",
    )


@pytest.mark.asyncio
async def test_subordinate_session_list_execute() -> None:
    """Verify test subordinate session list execute."""
    mock_db = MagicMock()
    rows = [{"parent_session_id": "a", "count": 1}]
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch(
            "code_analysis.commands.sessions.subordinate_session_commands.list_subordinate_sessions",
            return_value=rows,
        ),
    ):
        cmd = SubordinateSessionListCommand()
        result = await cmd.execute(
            parent_session_id="11111111-1111-4111-8111-111111111111"
        )

    assert isinstance(result, SuccessResult)
    assert result.data["count"] == 1


@pytest.mark.asyncio
async def test_subordinate_session_get_not_found() -> None:
    """Verify test subordinate session get not found."""
    mock_db = MagicMock()
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch(
            "code_analysis.commands.sessions.subordinate_session_commands.get_subordinate_session",
            return_value=None,
        ),
    ):
        cmd = SubordinateSessionGetCommand()
        result = await cmd.execute(
            parent_session_id="11111111-1111-4111-8111-111111111111",
            server_uuid="880e8400-e29b-41d4-a716-446655440003",
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "SUBORDINATE_SESSION_NOT_FOUND"
