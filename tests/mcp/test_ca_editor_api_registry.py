"""
Registry smoke test: editor-facing API on code-analysis-server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest
import pytest_asyncio

import code_analysis.hooks  # noqa: F401
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks

_EDITOR_FACING_COMMANDS = (
    "session_create",
    "session_validate",
    "session_delete",
    "session_open_file",
    "session_close_file",
    "session_list_file_locks",
    "project_file_transfer_download_begin",
    "project_file_transfer_upload_save",
    "project_file_advisory_lock_batch",
    "project_file_lock_status",
    "list_project_files",
    "universal_file_preview",
)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _register_commands() -> None:
    """Return register commands."""
    hooks.execute_custom_commands_hooks(registry)


@pytest.mark.parametrize("command_name", _EDITOR_FACING_COMMANDS)
def test_editor_facing_commands_registered(command_name: str) -> None:
    """Verify test editor facing commands registered."""
    cls = registry.get_command(command_name)
    assert cls is not None
    assert cls.name == command_name
