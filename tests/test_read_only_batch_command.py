"""
Tests for read_only_batch contract: whitelist, inline vs file output, metadata consistency.

Covers: accept whitelisted read-only commands; reject non-whitelisted/mutating;
inline when below threshold; file output when above threshold; file_size and
per-command size/offset/length consistency. No tests for fallback behavior
banned by TZ (no inline oversized payload).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, cast

import pytest

from code_analysis.commands.read_only_batch_command import (
    run_read_only_batch,
    _Invocation,
)
from code_analysis.commands.read_only_batch_output import extract_command_fragment
from code_analysis.commands.read_only_batch_whitelist import (
    READ_ONLY_BATCH_WHITELIST,
    ERROR_CODE_NOT_WHITELISTED,
)
from mcp_proxy_adapter.commands.result import SuccessResult


class _FakeRegistry:
    """Fake registry returning real command instances (no MagicMock) so JSON serialization works."""

    def __init__(
        self,
        command_responses: Optional[Dict[str, Any]] = None,
        command_not_found: Optional[str] = None,
    ) -> None:
        self._responses = command_responses or {}
        self._not_found = command_not_found

    def get_command(self, name: str) -> type:
        if self._not_found is not None and name == self._not_found:
            raise KeyError(f"Command '{name}' not found")
        data = dict(self._responses.get(name, {"ok": True}))

        class _Cmd:
            def validate_params(self, params: Any) -> Dict[str, Any]:
                return dict(params) if params else {}

            async def execute(self, **kwargs: Any) -> SuccessResult:
                return SuccessResult(data=data)

        return _Cmd


def _make_mock_registry(
    command_responses: Optional[Dict[str, Any]] = None,
    command_not_found: Optional[str] = None,
) -> _FakeRegistry:
    """Build a registry: get_command(name) returns a class with validate_params + execute."""
    return _FakeRegistry(
        command_responses=command_responses,
        command_not_found=command_not_found,
    )


@pytest.mark.asyncio
async def test_accept_whitelisted_read_only_commands(tmp_path: Any) -> None:
    """Batch accepts whitelisted read-only commands and returns inline results."""
    registry = _make_mock_registry(
        command_responses={"get_class_hierarchy": {"hierarchy": [], "project_id": "p1"}}
    )
    invocations = [
        {"command": "get_class_hierarchy", "params": {"project_id": "p1"}},
    ]
    result = await run_read_only_batch(
        cast(Sequence[_Invocation], invocations),
        max_response_bytes=100_000,
        output_dir=str(tmp_path),
        registry=registry,
    )
    assert result.get("inline") is True
    assert "results" in result
    assert len(result["results"]) == 1
    assert result["results"][0]["command"] == "get_class_hierarchy"
    assert result["results"][0]["result"].get("success") is True
    assert result["results"][0]["result"].get("data", {}).get("hierarchy") == []


@pytest.mark.asyncio
async def test_reject_non_whitelisted_command(tmp_path: Any) -> None:
    """Batch rejects non-whitelisted command with explicit error payload."""
    registry = _make_mock_registry()
    invocations = [{"command": "cst_save_tree", "params": {"project_id": "p1"}}]
    result = await run_read_only_batch(
        cast(Sequence[_Invocation], invocations),
        max_response_bytes=100_000,
        output_dir=str(tmp_path),
        registry=registry,
    )
    assert result.get("inline") is False
    assert "error" in result
    assert result.get("error_code") == ERROR_CODE_NOT_WHITELISTED
    assert result.get("command") == "cst_save_tree"
    assert "results" not in result


@pytest.mark.asyncio
async def test_reject_mutating_command_by_name(tmp_path: Any) -> None:
    """Batch rejects mutating command (cst_apply_buffer) via whitelist."""
    registry = _make_mock_registry()
    invocations = [{"command": "cst_apply_buffer", "params": {}}]
    result = await run_read_only_batch(
        cast(Sequence[_Invocation], invocations),
        max_response_bytes=100_000,
        output_dir=str(tmp_path),
        registry=registry,
    )
    assert result.get("inline") is False
    assert result.get("error_code") == ERROR_CODE_NOT_WHITELISTED
    assert "cst_apply_buffer" in (result.get("command"), result.get("error", ""))


@pytest.mark.asyncio
async def test_reject_empty_command_name(tmp_path: Any) -> None:
    """Batch rejects empty or invalid command name."""
    registry = _make_mock_registry()
    for inv in [{"command": "", "params": {}}, {"command": "   ", "params": {}}]:
        result = await run_read_only_batch(
            cast(Sequence[_Invocation], [inv]),
            max_response_bytes=100_000,
            output_dir=str(tmp_path),
            registry=registry,
        )
        assert result.get("inline") is False
        assert result.get("error_code") == ERROR_CODE_NOT_WHITELISTED


@pytest.mark.asyncio
async def test_inline_response_when_below_threshold(tmp_path: Any) -> None:
    """When serialized payload is below max_response_bytes, response is inline."""
    registry = _make_mock_registry(
        command_responses={"list_code_entities": {"entities": [], "total": 0}}
    )
    invocations = [
        {"command": "list_code_entities", "params": {"project_id": "p1"}},
    ]
    result = await run_read_only_batch(
        cast(Sequence[_Invocation], invocations),
        max_response_bytes=1_000_000,
        output_dir=str(tmp_path),
        registry=registry,
    )
    assert result.get("inline") is True
    assert "results" in result
    assert "output_file" not in result
    assert "results_metadata" not in result


@pytest.mark.asyncio
async def test_file_output_when_payload_exceeds_threshold(tmp_path: Any) -> None:
    """When payload exceeds max_response_bytes, output goes to file; no inline oversize."""
    # One command returning data large enough to exceed a tiny threshold
    big = {"items": [{"id": str(i), "name": f"entity_{i}"} for i in range(500)]}
    registry = _make_mock_registry(command_responses={"get_code_entity_info": big})
    invocations = [{"command": "get_code_entity_info", "params": {"entity_id": "e1"}}]
    result = await run_read_only_batch(
        cast(Sequence[_Invocation], invocations),
        max_response_bytes=50,
        output_dir=str(tmp_path),
        registry=registry,
    )
    assert result.get("inline") is False
    assert "output_file" in result
    assert "file_size" in result
    assert "results_metadata" in result
    assert "results" not in result


@pytest.mark.asyncio
async def test_file_size_and_metadata_consistency(tmp_path: Any) -> None:
    """file_size and per-command size/offset/length are consistent with actual file."""
    registry = _make_mock_registry(
        command_responses={
            "get_class_hierarchy": {"hierarchy": [{"name": "A"}]},
            "list_code_entities": {"entities": [{"id": "1"}], "total": 1},
        }
    )
    invocations = [
        {"command": "get_class_hierarchy", "params": {"project_id": "p1"}},
        {"command": "list_code_entities", "params": {"project_id": "p1"}},
    ]
    result = await run_read_only_batch(
        cast(Sequence[_Invocation], invocations),
        max_response_bytes=10,
        output_dir=str(tmp_path),
        registry=registry,
    )
    assert result.get("inline") is False
    output_file = result["output_file"]
    file_size = result["file_size"]
    meta = result["results_metadata"]

    with open(output_file, "rb") as f:
        actual_size = len(f.read())
    assert file_size == actual_size

    assert len(meta) == 2
    for i, m in enumerate(meta):
        assert "command" in m
        assert "size" in m
        assert "offset" in m
        assert "length" in m
        assert m["size"] == m["length"]
        assert m["offset"] >= 0
        assert m["length"] > 0

    # Offsets and lengths sum to file_size
    total_from_meta = sum(m["length"] for m in meta)
    assert total_from_meta == file_size

    # Last entry: offset + length == file_size
    last = meta[-1]
    assert last["offset"] + last["length"] == file_size

    # Byte-range extraction reproduces exact fragment
    first_meta = meta[0]
    fragment = extract_command_fragment(
        output_file,
        first_meta["offset"],
        first_meta["length"],
    )
    assert len(fragment) == first_meta["length"]
    assert first_meta["command"].encode("utf-8") in fragment


@pytest.mark.asyncio
async def test_whitelisted_command_not_found_returns_error(tmp_path: Any) -> None:
    """When command is whitelisted but not in registry, return BATCH_COMMAND_NOT_FOUND."""
    registry = _make_mock_registry(
        command_not_found="get_class_hierarchy",
    )
    invocations = [{"command": "get_class_hierarchy", "params": {"project_id": "p1"}}]
    result = await run_read_only_batch(
        cast(Sequence[_Invocation], invocations),
        max_response_bytes=100_000,
        output_dir=str(tmp_path),
        registry=registry,
    )
    assert result.get("inline") is False
    assert result.get("error_code") == "BATCH_COMMAND_NOT_FOUND"
    assert (
        "not found" in result.get("error", "").lower()
        or "not registered" in result.get("error", "").lower()
    )


def test_whitelist_contains_expected_read_only_commands() -> None:
    """Whitelist includes expected read-only analysis commands; no mutating commands."""
    expected = {
        "get_class_hierarchy",
        "list_code_entities",
        "get_code_entity_info",
        "find_dependencies",
        "find_usages",
        "get_entity_dependencies",
        "get_entity_dependents",
    }
    assert expected <= READ_ONLY_BATCH_WHITELIST
    mutating = {"cst_save_tree", "cst_apply_buffer", "cst_modify_tree"}
    assert READ_ONLY_BATCH_WHITELIST.isdisjoint(mutating)
