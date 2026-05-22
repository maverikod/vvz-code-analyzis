"""
In-process tests for session_management MCP commands.

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
from code_analysis.commands.sessions.session_close_file_command import (
    SessionCloseFileCommand,
)
from code_analysis.commands.sessions.session_create_command import SessionCreateCommand
from code_analysis.commands.sessions.session_delete_command import SessionDeleteCommand
from code_analysis.commands.sessions.session_list_command import SessionListCommand
from code_analysis.commands.sessions.session_list_file_locks_command import (
    SessionListFileLocksCommand,
)
from code_analysis.commands.sessions.session_open_file_command import (
    SessionOpenFileCommand,
)

_SESSION_COMMANDS = (
    ("session_create", SessionCreateCommand),
    ("session_delete", SessionDeleteCommand),
    ("session_list", SessionListCommand),
    ("session_open_file", SessionOpenFileCommand),
    ("session_close_file", SessionCloseFileCommand),
    ("session_list_file_locks", SessionListFileLocksCommand),
)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _register_session_commands() -> None:
    hooks.execute_custom_commands_hooks(registry)


@pytest.mark.parametrize("name,expected_cls", _SESSION_COMMANDS)
def test_session_commands_registered_as_session_management(
    name: str, expected_cls: type
) -> None:
    cls = registry.get_command(name)
    assert cls is expected_cls
    assert cls.category == "session_management"
    assert cls.name == name


@pytest.mark.parametrize("name,expected_cls", _SESSION_COMMANDS)
def test_session_command_metadata_meets_standard(name: str, expected_cls: type) -> None:
    cls = registry.get_command(name)
    meta = cls.metadata()
    for key in REQUIRED_METADATA_KEYS:
        assert key in meta, f"{name}: missing metadata key {key!r}"
        assert meta[key] not in (None, ""), f"{name}: empty metadata key {key!r}"
    assert meta.get("usage_examples"), f"{name}: usage_examples required"
    schema_props = set((cls.get_schema().get("properties") or {}).keys())
    assert (
        set(meta.get("parameters") or {}) == schema_props
    ), f"{name}: parameters keys must match get_schema properties"


@pytest.mark.asyncio
async def test_session_create_execute_returns_session_id() -> None:
    row = {
        "session_id": "11111111-1111-4111-8111-111111111111",
        "comment": "test",
        "created_at": 1.0,
        "last_active_at": 1.0,
    }
    mock_db = MagicMock()
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch(
            "code_analysis.commands.sessions.session_create_command.create_client_session",
            return_value=row,
        ) as create_fn,
    ):
        cmd = SessionCreateCommand()
        result = await cmd.execute(comment="test")

    assert isinstance(result, SuccessResult)
    assert result.data["session_id"] == row["session_id"]
    create_fn.assert_called_once_with(mock_db, comment="test", role_ids=None)


@pytest.mark.asyncio
async def test_session_list_session_id_required_when_show_ids_true() -> None:
    mock_db = MagicMock()
    config = {
        "sessions": {"show_session_ids": True},
        "registration": {"instance_uuid": "srv-uuid"},
        "security": {"policy": "disabled"},
    }
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch.object(BaseMCPCommand, "_get_raw_config", return_value=config),
    ):
        cmd = SessionListCommand()
        result = await cmd.execute()

    assert isinstance(result, ErrorResult)
    assert result.code == "SESSION_ID_REQUIRED"
    mock_db.execute.assert_not_called()


def test_session_delete_schema_and_metadata_force_default_aligned() -> None:
    """get_schema() and metadata() must agree on force default and description."""
    schema = SessionDeleteCommand.get_schema()
    force_schema = schema["properties"]["force"]
    assert force_schema["default"] is False
    assert "session_id" in schema["required"]
    assert "force" not in schema["required"]

    meta = SessionDeleteCommand.metadata()
    force_meta = meta["parameters"]["force"]
    assert force_meta["default"] is False
    assert force_meta["required"] is False
    assert force_schema["description"] == force_meta["description"]

    assert set(meta["parameters"]) == set(schema["properties"])


@pytest.mark.asyncio
async def test_session_delete_execute_defaults_force_false() -> None:
    mock_db = MagicMock()
    config = {
        "registration": {"instance_uuid": "880e8400-e29b-41d4-a716-446655440003"},
        "security": {"policy": "disabled"},
    }
    delete_result = {
        "session_id": "11111111-1111-4111-8111-111111111111",
        "deleted": True,
        "released_lock_count": 0,
        "released_subordinate_count": 0,
    }
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch.object(BaseMCPCommand, "_get_raw_config", return_value=config),
        patch(
            "code_analysis.core.client_sessions.get_client_session",
            return_value={"session_id": delete_result["session_id"]},
        ),
        patch(
            "code_analysis.commands.sessions.session_delete_command.enforce_security_policy",
            return_value=None,
        ),
        patch(
            "code_analysis.commands.sessions.session_delete_command.delete_client_session",
            return_value=delete_result,
        ) as delete_fn,
    ):
        cmd = SessionDeleteCommand()
        result = await cmd.execute(session_id=delete_result["session_id"])

    assert isinstance(result, SuccessResult)
    delete_fn.assert_called_once_with(
        mock_db,
        session_id=delete_result["session_id"],
        force=False,
    )
