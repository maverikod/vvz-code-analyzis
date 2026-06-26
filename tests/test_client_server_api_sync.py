"""Ensure client facade commands match the in-process server command registry."""

from __future__ import annotations

import pytest
import pytest_asyncio

import code_analysis.hooks  # noqa: F401
from code_analysis_client.server_api import (
    assert_facade_commands_registered,
    assert_file_content_read_commands_registered,
    assert_fs_commands_registered,
    assert_removed_commands_absent,
)
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _register_server_commands() -> None:
    """Return register server commands."""
    hooks.execute_custom_commands_hooks(registry)


def test_client_facade_commands_registered_on_server() -> None:
    """Verify test client facade commands registered on server."""
    assert_facade_commands_registered(registry.get_command)


def test_removed_commands_absent_from_server() -> None:
    """Verify test removed commands absent from server."""
    assert_removed_commands_absent(registry.get_command)


def test_file_content_read_commands_registered_on_server() -> None:
    """Verify test file content read commands registered on server."""
    assert_file_content_read_commands_registered(registry.get_command)


def test_fs_commands_registered_on_server() -> None:
    """Verify test fs commands registered on server."""
    assert_fs_commands_registered(registry.get_command)
