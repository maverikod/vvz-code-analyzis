"""Tests for Git/GitHub coverage in the casmgr info manual.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.info_command import (
    INFO_NODES,
    InfoCommand,
    _parse_info_nodes,
)
from code_analysis.hooks import register_code_analysis_commands

GIT_INFO_NODE = "Git and GitHub commands"
COMMAND_REFERENCE_NODE = "Command reference"


def test_info_schema_exposes_git_and_github_node() -> None:
    """Verify the info command help contract lists the Git/GitHub manual node."""
    schema = InfoCommand.get_schema()
    metadata = InfoCommand.metadata()

    assert GIT_INFO_NODE in INFO_NODES
    assert GIT_INFO_NODE in schema["properties"]["node"]["enum"]
    assert COMMAND_REFERENCE_NODE in INFO_NODES
    assert COMMAND_REFERENCE_NODE in schema["properties"]["node"]["enum"]
    assert "Git and GitHub" in metadata["detailed_description"]
    assert "Command reference" in metadata["detailed_description"]
    assert any(
        example["command"].get("node") == GIT_INFO_NODE
        for example in metadata["usage_examples"]
    )
    assert any(
        example["command"].get("node") == COMMAND_REFERENCE_NODE
        for example in metadata["usage_examples"]
    )


def test_built_info_manual_contains_full_git_command_block() -> None:
    """Verify generated Info docs contain the Git/GitHub command reference."""
    info_path = Path("packaging/info/casmgr-server.info")
    nodes = _parse_info_nodes(info_path.read_text(encoding="utf-8"))

    assert GIT_INFO_NODE in nodes
    assert COMMAND_REFERENCE_NODE in nodes
    text = nodes[GIT_INFO_NODE]
    for command_name in (
        "git_config_get",
        "git_config_list",
        "git_identity_get",
        "git_identity_set",
        "git_status",
        "git_branch_current",
        "git_branch_create",
        "git_branch_push",
        "git_add",
        "git_commit",
        "git_restore",
        "git_reset",
        "git_clean",
        "git_stash_push",
        "git_merge",
        "git_rebase",
        "git_cherry_pick",
        "git_revert",
        "git_tag",
        "github_repo_get",
        "github_pr_create",
        "github_pr_merge",
        "github_issue_create",
        "github_release_create",
    ):
        assert command_name in text
    for safety_phrase in (
        "confirm_hard=true",
        "dry_run=true",
        "confirm=true",
        "confirm_delete=true",
        "git worktree",
    ):
        assert safety_phrase in text

    command_reference_text = nodes[COMMAND_REFERENCE_NODE]
    assert "runtime-generated" in command_reference_text
    assert "live command registry" in command_reference_text
    assert "authoritative full command catalog" in command_reference_text


@pytest.mark.asyncio
async def test_info_command_reference_node_uses_live_registry() -> None:
    """Verify info exposes a live full command reference from registry metadata."""
    register_code_analysis_commands(registry)

    result = await InfoCommand().execute(
        node=COMMAND_REFERENCE_NODE,
        format="text",
        max_chars=1000000,
    )

    assert isinstance(result, SuccessResult)
    item = result.data["items"][0]
    assert item["node"] == COMMAND_REFERENCE_NODE
    assert result.data["truncated"] is False
    text = item["text"]
    for command_name in (
        "### git_reset",
        "### git_rebase",
        "### git_tag",
        "### github_pr_create",
        "### list_projects",
        "### search",
    ):
        assert command_name in text
    for contract_phrase in (
        "Parameters:",
        "Return value:",
        "Usage examples:",
        "Error cases:",
        "additionalProperties:",
    ):
        assert contract_phrase in text
