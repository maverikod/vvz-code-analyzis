"""Registered MCP commands: metadata.parameters must mirror get_schema() after finalize."""

from __future__ import annotations

import logging
from typing import Any, Type

import pytest

from code_analysis.commands.command_metadata_helpers import finalize_command_metadata
from code_analysis.hooks import register_code_analysis_commands
from mcp_proxy_adapter.commands.command_registry import registry

logging.disable(logging.CRITICAL)

register_code_analysis_commands(registry)

_REGISTERED: list[Type[Any]] = [
    cls
    for cls in registry._commands.values()
    if str(getattr(cls, "__module__", "")).startswith("code_analysis.")
]


@pytest.mark.parametrize(
    "cmd_cls", _REGISTERED, ids=lambda c: getattr(c, "name", c.__name__)
)
def test_finalized_metadata_parameters_match_schema(cmd_cls: Type[Any]) -> None:
    schema = cmd_cls.get_schema()
    props = set((schema.get("properties") or {}).keys())
    required = set(schema.get("required") or [])
    meta = finalize_command_metadata(cmd_cls, cmd_cls.metadata())
    mparams = meta.get("parameters") or {}

    assert (
        set(mparams.keys()) == props
    ), f"{cmd_cls.name}: metadata keys {set(mparams.keys())} != schema {props}"
    for key in required:
        assert (
            mparams[key].get("required") is True
        ), f"{cmd_cls.name}: {key} must be required"
    for key in mparams:
        if key == "root_dir" and key in props:
            continue
        assert (
            key != "root_dir"
        ), f"{cmd_cls.name}: legacy root_dir in metadata but not in schema"


@pytest.mark.parametrize(
    "cmd_cls", _REGISTERED, ids=lambda c: getattr(c, "name", c.__name__)
)
def test_finalized_usage_examples_use_schema_keys_only(cmd_cls: Type[Any]) -> None:
    schema = cmd_cls.get_schema()
    props = set((schema.get("properties") or {}).keys())
    meta = finalize_command_metadata(cmd_cls, cmd_cls.metadata())
    for example in meta.get("usage_examples") or []:
        command = example.get("command") or {}
        extra = set(command.keys()) - props
        assert not extra, f"{cmd_cls.name}: example keys {extra} not in schema"
        assert "root_dir" not in command
