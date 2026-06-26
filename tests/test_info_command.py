"""
Tests for the MCP info command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import gzip

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

import code_analysis.commands.info_command as info_module
from code_analysis.commands.command_metadata_helpers import REQUIRED_METADATA_KEYS
from code_analysis.commands.info_command import InfoCommand


@pytest.mark.asyncio
async def test_info_command_lists_nodes_from_manual() -> None:
    """The command reads the packaged Info manual and exposes known nodes."""
    result = await InfoCommand().execute(format="nodes")

    assert isinstance(result, SuccessResult)
    assert "Installation" in result.data["nodes"]
    assert "Systemd" in result.data["nodes"]
    assert result.data["package"]["manual"]["path"]
    assert result.data["items"] == []


@pytest.mark.asyncio
async def test_info_command_returns_requested_node_text() -> None:
    """A direct node request returns text from that manual node."""
    result = await InfoCommand().execute(
        node="Installation",
        format="text",
        max_chars=5000,
    )

    assert isinstance(result, SuccessResult)
    assert result.data["items"][0]["node"] == "Installation"
    assert "dpkg -i" in result.data["items"][0]["text"]
    assert result.data["truncated"] is False


@pytest.mark.asyncio
async def test_info_command_reads_debian_compressed_info(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Debian install-info may gzip the installed manual."""
    source = info_module.Path.cwd() / "packaging" / "info" / "casmgr-server.info"
    compressed = tmp_path / "casmgr-server.info.gz"
    with gzip.open(compressed, "wt", encoding="utf-8") as handle:
        handle.write(source.read_text(encoding="utf-8"))

    monkeypatch.setattr(info_module, "INFO_PATH_CANDIDATES", [compressed])
    monkeypatch.setattr(info_module, "TEXI_PATH_CANDIDATES", [])

    result = await InfoCommand().execute(node="Systemd", format="text")

    assert isinstance(result, SuccessResult)
    assert result.data["package"]["manual"]["path"] == str(compressed)
    assert result.data["package"]["manual"]["format"] == "info"
    assert result.data["items"][0]["node"] == "Systemd"


@pytest.mark.asyncio
async def test_info_command_rejects_unknown_node() -> None:
    """Unknown nodes fail with a stable error code."""
    result = await InfoCommand().execute(node="No such node")

    assert isinstance(result, ErrorResult)
    assert result.code == "INFO_NODE_NOT_FOUND"


def test_info_command_schema_and_metadata_are_help_ready() -> None:
    """Schema and metadata follow the command help standard."""
    schema = InfoCommand.get_schema()
    assert schema["additionalProperties"] is False
    assert "Installation" in schema["properties"]["node"]["enum"]
    assert schema["properties"]["format"]["enum"] == ["summary", "text", "nodes"]

    meta = InfoCommand.metadata()
    for key in REQUIRED_METADATA_KEYS:
        assert key in meta, f"missing metadata key: {key}"
    assert meta["name"] == "info"
    assert "casmgr-server.info" in meta["detailed_description"]
