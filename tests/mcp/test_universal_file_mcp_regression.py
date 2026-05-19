"""
In-process MCP smoke tests for the universal file **edit-session** lifecycle.

Uses :meth:`mcp_proxy_adapter.commands.base.Command.run` with hooks registration
(no live daemon). Legacy commands (`universal_file_read`, …) are asserted absent
from the registry per spec.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest
import pytest_asyncio

import code_analysis.hooks  # noqa: F401 — register_custom_commands_hook
from code_analysis.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from code_analysis.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from code_analysis.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from code_analysis.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from code_analysis.commands.universal_file_preview_command import (
    UniversalFilePreviewCommand,
)
from code_analysis.commands.get_file_lines_command import GetFileLinesCommand
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks

_LEGACY_ABSENT_FROM_REGISTRY = (
    "universal_file_read",
    "universal_file_save",
    "universal_file_replace",
    "universal_file_delete",
    "read_project_text_file",
    "write_project_text_lines",
)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _register_commands() -> None:
    hooks.execute_custom_commands_hooks(registry)


@pytest.mark.asyncio
async def test_registry_exposes_universal_file_lifecycle_and_preview() -> None:
    for name in (
        "universal_file_open",
        "universal_file_edit",
        "universal_file_write",
        "universal_file_close",
        "universal_file_preview",
        "get_file_lines",
    ):
        assert registry.get_command(name) is not None, name


def test_registered_universal_edit_commands_categories_and_aliases() -> None:
    cls_open = registry.get_command("universal_file_open")
    cls_edit = registry.get_command("universal_file_edit")
    cls_write = registry.get_command("universal_file_write")
    cls_close = registry.get_command("universal_file_close")
    cls_preview = registry.get_command("universal_file_preview")
    cls_lines = registry.get_command("get_file_lines")

    assert cls_open is UniversalFileOpenCommand
    assert cls_open.category == "file_management"
    assert cls_open.name == "universal_file_open"

    assert cls_edit is UniversalFileEditCommand
    assert cls_edit.category == "file_management"
    assert cls_edit.name == "universal_file_edit"

    assert cls_write is UniversalFileWriteCommand
    assert cls_write.__name__ == "UniversalFileWriteCommand"

    assert cls_close is UniversalFileCloseCommand
    assert cls_close.category == "file_management"
    assert cls_close.name == "universal_file_close"

    assert cls_preview is UniversalFilePreviewCommand
    assert cls_preview.category == "preview"
    assert cls_preview.name == "universal_file_preview"

    assert cls_lines is GetFileLinesCommand
    assert cls_lines.category == "cst"
    assert cls_lines.name == "get_file_lines"


@pytest.mark.asyncio
async def test_registry_legacy_file_commands_removed() -> None:
    for name in _LEGACY_ABSENT_FROM_REGISTRY:
        with pytest.raises(KeyError, match=name):
            registry.get_command(name)
