"""Schema/metadata alignment for unified search MCP commands."""

from __future__ import annotations

from typing import Any, Type

import pytest

from code_analysis.commands.command_metadata_helpers import finalize_command_metadata
from code_analysis.commands.search_cancel_command import SearchCancelCommand
from code_analysis.commands.search_close_command import SearchCloseCommand
from code_analysis.commands.search_get_page_command import SearchGetPageCommand
from code_analysis.commands.search_get_status_command import SearchGetStatusCommand
from code_analysis.commands.search_mcp_command import SearchMCPCommand

SEARCH_COMMANDS: tuple[Type[Any], ...] = (
    SearchMCPCommand,
    SearchGetPageCommand,
    SearchGetStatusCommand,
    SearchCancelCommand,
    SearchCloseCommand,
)

_PAGINATED_CROSS_PARAMS = frozenset(
    {
        "project_id",
        "query",
        "enable_semantic",
        "enable_grep",
        "grep_patterns",
        "fulltext_limit",
        "semantic_limit",
        "page_size",
        "min_semantic_score",
        "require_structural_grep",
        "literal",
        "case_sensitive",
        "hard_timeout_seconds",
        "first_block_wait_seconds",
    }
)


@pytest.mark.parametrize("cmd_cls", SEARCH_COMMANDS)
def test_metadata_parameters_match_schema(cmd_cls: Type[Any]) -> None:
    schema = cmd_cls.get_schema()
    props = set((schema.get("properties") or {}).keys())
    meta = finalize_command_metadata(cmd_cls, cmd_cls.metadata())
    mparams = meta.get("parameters") or {}

    for key in mparams:
        assert key in props, f"{cmd_cls.name}: metadata param {key!r} not in schema"

    for key in schema.get("required") or []:
        assert mparams[key].get("required") is True, f"{cmd_cls.name}: {key} required"


@pytest.mark.parametrize("cmd_cls", SEARCH_COMMANDS)
def test_usage_examples_only_use_schema_keys(cmd_cls: Type[Any]) -> None:
    schema = cmd_cls.get_schema()
    props = set((schema.get("properties") or {}).keys())
    meta = finalize_command_metadata(cmd_cls, cmd_cls.metadata())
    for example in meta.get("usage_examples") or []:
        command = example.get("command") or {}
        extra = set(command.keys()) - props
        assert not extra, f"{cmd_cls.name}: example keys {extra} not in schema"


def test_search_schema_has_no_search_start_references() -> None:
    for cmd_cls in SEARCH_COMMANDS:
        schema = cmd_cls.get_schema()
        for prop in (schema.get("properties") or {}).values():
            desc = str(prop.get("description") or "")
            assert "search_start" not in desc, cmd_cls.name


def test_search_backend_params_are_in_schema() -> None:
    schema = SearchMCPCommand.get_schema()
    props = set((schema.get("properties") or {}).keys())
    missing = _PAGINATED_CROSS_PARAMS - props
    assert not missing, f"search schema missing backend params: {missing}"
