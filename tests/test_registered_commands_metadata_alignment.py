"""Registered MCP commands: metadata.parameters must mirror get_schema() after finalize."""

from __future__ import annotations

import logging
from typing import Any, Dict, Type

import pytest

from code_analysis.commands.command_metadata_helpers import finalize_command_metadata
from code_analysis.hooks import register_code_analysis_commands
from mcp_proxy_adapter.commands.command_registry import registry

_PREV_LOGGING_DISABLE = logging.root.manager.disable
logging.disable(logging.CRITICAL)
try:
    register_code_analysis_commands(registry)
finally:
    logging.disable(_PREV_LOGGING_DISABLE)

_REGISTERED: list[Type[Any]] = [
    cls
    for cls in registry._commands.values()
    if str(getattr(cls, "__module__", "")).startswith("code_analysis.")
]


@pytest.mark.parametrize(
    "cmd_cls", _REGISTERED, ids=lambda c: getattr(c, "name", c.__name__)
)
def test_finalized_metadata_parameters_match_schema(cmd_cls: Type[Any]) -> None:
    """Verify test finalized metadata parameters match schema."""
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


def test_start_worker_raw_metadata_parameters_match_schema() -> None:
    """``get_start_worker_metadata``'s own hand-written ``parameters`` dict --
    BEFORE ``finalize_command_metadata`` gets a chance to rebuild it -- must
    already be aligned with ``StartWorkerMCPCommand.get_schema()`` (bug 827e2b05).

    ``finalize_command_metadata`` unconditionally overwrites ``parameters``
    from ``get_schema()`` (``command_metadata_helpers.py:282``), so the
    `test_finalized_*` tests above pass even when the hand-written source
    (``get_start_worker_metadata`` in ``worker_management_mcp_commands_schema.py``)
    documents a stale/removed parameter like the legacy ``root_dir`` --
    finalize silently erases that drift before either test can observe it,
    and the live ``help``/``cmdname`` payload (``mcp_proxy_adapter``'s
    ``command_help_info.merge_command_metadata_into_help_payload``) also
    merges other RAW fields verbatim (``detailed_description``,
    ``usage_examples``, ``error_cases``, ``best_practices`` are only
    replaced by finalize when ABSENT, never when merely wrong) -- so wrong
    parameter docs, once written, would otherwise never be caught by any
    existing test. This test calls the RAW builder function directly,
    bypassing the registry's metadata-finalization wrapping entirely.
    """
    from code_analysis.commands.start_worker_mcp_command import StartWorkerMCPCommand
    from code_analysis.commands.worker_management_mcp_commands_schema import (
        get_start_worker_metadata,
    )

    schema = StartWorkerMCPCommand.get_schema()
    props = set((schema.get("properties") or {}).keys())
    required = set(schema.get("required") or [])

    raw_meta = get_start_worker_metadata(
        StartWorkerMCPCommand.name,
        StartWorkerMCPCommand.version,
        StartWorkerMCPCommand.descr,
        StartWorkerMCPCommand.category,
        StartWorkerMCPCommand.author,
        StartWorkerMCPCommand.email,
    )
    raw_params = set((raw_meta.get("parameters") or {}).keys())

    unknown = raw_params - props
    assert not unknown, (
        f"get_start_worker_metadata: parameters {unknown} are not in "
        f"get_schema() properties {props} (stale/removed parameter documented "
        "by hand, e.g. legacy root_dir -- bug 827e2b05)"
    )
    missing = props - raw_params
    assert not missing, (
        f"get_start_worker_metadata: get_schema() properties {missing} are "
        f"not documented at all in the raw parameters dict {raw_params}"
    )
    for key in required:
        assert raw_params_required(raw_meta, key), (
            f"get_start_worker_metadata: {key} is required by get_schema() but "
            "not marked required=True in the raw parameters dict"
        )
    assert "root_dir" not in str(raw_meta.get("detailed_description", "")), (
        "get_start_worker_metadata.detailed_description still mentions the "
        "legacy root_dir workflow (bug 827e2b05)"
    )
    for example in raw_meta.get("usage_examples") or []:
        command = example.get("command") or {}
        assert "root_dir" not in command, (
            f"get_start_worker_metadata usage example still uses legacy "
            f"root_dir: {example!r}"
        )


def raw_params_required(raw_meta: Dict[str, Any], key: str) -> bool:
    """Return whether ``key`` is marked ``required: True`` in a raw metadata
    ``parameters`` dict."""
    params = raw_meta.get("parameters") or {}
    entry = params.get(key) or {}
    return bool(entry.get("required") is True)


@pytest.mark.parametrize(
    "cmd_cls", _REGISTERED, ids=lambda c: getattr(c, "name", c.__name__)
)
def test_finalized_usage_examples_use_schema_keys_only(cmd_cls: Type[Any]) -> None:
    """Verify test finalized usage examples use schema keys only."""
    schema = cmd_cls.get_schema()
    props = set((schema.get("properties") or {}).keys())
    meta = finalize_command_metadata(cmd_cls, cmd_cls.metadata())
    for example in meta.get("usage_examples") or []:
        command = example.get("command") or {}
        extra = set(command.keys()) - props
        assert not extra, f"{cmd_cls.name}: example keys {extra} not in schema"
        assert "root_dir" not in command
