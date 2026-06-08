"""
In-process MCP smoke tests for universal file **read-only** surface on CA server.

Uses :meth:`mcp_proxy_adapter.commands.base.Command.run` with hooks registration
(no live daemon). Content editing commands must not appear in the registry.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest
import pytest_asyncio

import code_analysis.hooks  # noqa: F401 — register_custom_commands_hook
from code_analysis.commands.universal_file_edit.search_command import (
    UniversalFileSearchCommand,
)
from code_analysis.commands.universal_file_preview_command import (
    UniversalFilePreviewCommand,
)
from code_analysis.commands.get_file_lines_command import GetFileLinesCommand
from code_analysis_client.server_api import (
    EDITING_REMOVED_COMMANDS,
    FILE_CONTENT_READ_COMMANDS,
    LEGACY_REMOVED_COMMANDS,
    REMOVED_COMMANDS,
    assert_file_content_read_commands_registered,
    assert_removed_commands_absent,
)
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _register_commands() -> None:
    hooks.execute_custom_commands_hooks(registry)


def test_registry_file_content_read_surface() -> None:
    assert_file_content_read_commands_registered(registry.get_command)


def test_registry_no_content_editing_commands() -> None:
    assert_removed_commands_absent(registry.get_command)


@pytest.mark.parametrize("name", sorted(REMOVED_COMMANDS))
def test_each_removed_command_absent(name: str) -> None:
    with pytest.raises(KeyError, match=name):
        registry.get_command(name)


def test_registered_read_only_universal_file_command_classes() -> None:
    cls_preview = registry.get_command("universal_file_preview")
    cls_search = registry.get_command("universal_file_search")
    cls_lines = registry.get_command("get_file_lines")

    assert cls_preview is UniversalFilePreviewCommand
    assert cls_preview.category == "preview"
    assert cls_preview.name == "universal_file_preview"

    assert cls_search is UniversalFileSearchCommand
    assert cls_search.name == "universal_file_search"

    assert cls_lines is GetFileLinesCommand
    assert cls_lines.name == "get_file_lines"


def test_editing_removed_subset_covers_legacy_and_edit_session() -> None:
    assert LEGACY_REMOVED_COMMANDS <= REMOVED_COMMANDS
    assert EDITING_REMOVED_COMMANDS <= REMOVED_COMMANDS
    assert "universal_file_open" in EDITING_REMOVED_COMMANDS
    assert "format_code" in EDITING_REMOVED_COMMANDS


def test_file_content_read_includes_preview_search_and_disk_grep() -> None:
    assert {"universal_file_preview", "universal_file_search", "fs_grep"} <= (
        FILE_CONTENT_READ_COMMANDS
    )
