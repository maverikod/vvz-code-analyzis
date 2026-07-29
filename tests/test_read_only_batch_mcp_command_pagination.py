"""
Tests for ReadOnlyBatchMCPCommand's pagination trigger wiring (TODO 9c2018a3).

The orchestration-level pagination behavior itself (bounds, clamping,
out-of-range pages, page contents) is covered in
tests/test_read_only_batch_command.py against run_read_only_batch() directly.
This file covers the thin MCP wrapper: schema exposes the pagination
parameters, and passing any one of them switches pagination_requested=True
through to run_read_only_batch (verified by asserting the effect: a tiny
max_response_bytes does not force file-overflow when pagination is
requested, and does when it is not).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.read_only_batch_mcp_command import ReadOnlyBatchMCPCommand
from code_analysis.core.list_pagination import (
    DEFAULT_LIST_PAGE_SIZE,
    MAX_LIST_PAGE_SIZE,
)


def _no_config() -> Dict[str, Any]:
    """Return an empty raw config (defaults apply for batch settings)."""
    return {}


class _StubCommandClass:
    """Registered-command stand-in: validate_params passthrough + trivial execute()."""

    def validate_params(self, params: Any) -> Dict[str, Any]:
        """Return params unchanged (schema validation not under test here)."""
        return dict(params) if params else {}

    async def execute(self, **kwargs: Any) -> SuccessResult:
        """Return a fixed, cheap, JSON-serializable payload."""
        return SuccessResult(data={"hierarchy": [], "ok": True})


class _StubRegistry:
    """Registry stand-in resolving any command name to :class:`_StubCommandClass`."""

    def get_command(self, name: str) -> type:
        """Return a fresh stub command class for any name (whitelist already gates names)."""
        return _StubCommandClass


def test_schema_exposes_pagination_parameters() -> None:
    """get_schema() advertises page_size/block_position/offset/limit."""
    schema = ReadOnlyBatchMCPCommand.get_schema()
    props = schema["properties"]
    for key in ("page_size", "block_position", "offset", "limit"):
        assert key in props, f"missing pagination property {key!r}"
    assert props["page_size"]["maximum"] == MAX_LIST_PAGE_SIZE
    assert props["page_size"]["default"] == DEFAULT_LIST_PAGE_SIZE


@pytest.mark.asyncio
async def test_execute_without_pagination_params_uses_legacy_threshold_path(
    tmp_path: Any,
) -> None:
    """No pagination params -> tiny max_response_bytes forces file overflow (unchanged)."""
    with (
        patch.object(BaseMCPCommand, "_resolve_config_path", return_value=str(tmp_path / "config.json")),
        patch.object(BaseMCPCommand, "_get_raw_config", staticmethod(_no_config)),
        patch(
            "code_analysis.commands.read_only_batch_mcp_command.resolve_batch_output_dir",
            return_value=tmp_path,
        ),
        patch(
            "code_analysis.commands.read_only_batch_command.default_registry",
            _StubRegistry(),
        ),
    ):
        cmd = ReadOnlyBatchMCPCommand()
        result = await cmd.execute(
            invocations=[{"command": "get_class_hierarchy", "params": {}}],
            max_response_bytes=1,
        )

    assert isinstance(result, SuccessResult)
    assert result.data.get("inline") is False
    assert "output_file" in result.data
    assert "paginated" not in result.data


@pytest.mark.asyncio
async def test_execute_with_page_size_switches_to_paginated_inline(
    tmp_path: Any,
) -> None:
    """Passing page_size alone (even with a tiny max_response_bytes) yields a paginated inline page."""
    with (
        patch.object(BaseMCPCommand, "_resolve_config_path", return_value=str(tmp_path / "config.json")),
        patch.object(BaseMCPCommand, "_get_raw_config", staticmethod(_no_config)),
        patch(
            "code_analysis.commands.read_only_batch_mcp_command.resolve_batch_output_dir",
            return_value=tmp_path,
        ),
        patch(
            "code_analysis.commands.read_only_batch_command.default_registry",
            _StubRegistry(),
        ),
    ):
        cmd = ReadOnlyBatchMCPCommand()
        result = await cmd.execute(
            invocations=[{"command": "get_class_hierarchy", "params": {}}],
            max_response_bytes=1,
            page_size=1,
        )

    assert isinstance(result, SuccessResult)
    assert result.data.get("inline") is True
    assert result.data.get("paginated") is True
    assert "output_file" not in result.data
    assert result.data.get("page_size") == 1


@pytest.mark.asyncio
async def test_execute_with_block_position_alone_switches_to_paginated_inline(
    tmp_path: Any,
) -> None:
    """block_position alone (without page_size) also triggers pagination mode."""
    with (
        patch.object(BaseMCPCommand, "_resolve_config_path", return_value=str(tmp_path / "config.json")),
        patch.object(BaseMCPCommand, "_get_raw_config", staticmethod(_no_config)),
        patch(
            "code_analysis.commands.read_only_batch_mcp_command.resolve_batch_output_dir",
            return_value=tmp_path,
        ),
        patch(
            "code_analysis.commands.read_only_batch_command.default_registry",
            _StubRegistry(),
        ),
    ):
        cmd = ReadOnlyBatchMCPCommand()
        result = await cmd.execute(
            invocations=[{"command": "get_class_hierarchy", "params": {}}],
            max_response_bytes=1,
            block_position=1,
        )

    assert isinstance(result, SuccessResult)
    assert result.data.get("paginated") is True
    assert result.data.get("page_size") == DEFAULT_LIST_PAGE_SIZE
