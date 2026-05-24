"""Static checks: metadata.parameters align with get_schema(); no root_dir drift."""

from __future__ import annotations

from typing import Any, Callable, Dict, Type

from code_analysis.commands.ast.dependencies import FindDependenciesMCPCommand
from code_analysis.commands.ast.entity_dependencies import (
    GetEntityDependenciesMCPCommand,
    GetEntityDependentsMCPCommand,
)
from code_analysis.commands.ast.entity_dependencies_metadata import (
    get_entity_dependencies_metadata,
    get_entity_dependents_metadata,
)
from code_analysis.commands.ast.get_ast import GetASTMCPCommand
from code_analysis.commands.ast.hierarchy import GetClassHierarchyMCPCommand
from code_analysis.commands.ast.usages import FindUsagesMCPCommand
from code_analysis.commands.search_mcp_commands_find_classes import (
    FindClassesMCPCommand,
)

CommandMetaFn = Callable[[], Dict[str, Any]]

# High-traffic AST/search commands migrated from root_dir to project_id in schema.
SAMPLE_COMMANDS: tuple[tuple[Type[Any], CommandMetaFn], ...] = (
    (
        FindClassesMCPCommand,
        FindClassesMCPCommand.metadata,
    ),
    (
        FindUsagesMCPCommand,
        FindUsagesMCPCommand.metadata,
    ),
    (
        FindDependenciesMCPCommand,
        FindDependenciesMCPCommand.metadata,
    ),
    (GetASTMCPCommand, GetASTMCPCommand.metadata),
    (
        GetClassHierarchyMCPCommand,
        GetClassHierarchyMCPCommand.metadata,
    ),
    (GetEntityDependenciesMCPCommand, get_entity_dependencies_metadata),
    (GetEntityDependentsMCPCommand, get_entity_dependents_metadata),
)


def _resolve_metadata(meta_fn: CommandMetaFn) -> Dict[str, Any]:
    return meta_fn()


def test_sample_commands_schema_use_project_id_not_root_dir() -> None:
    for cmd_cls, _ in SAMPLE_COMMANDS:
        schema = cmd_cls.get_schema()
        props = schema.get("properties") or {}
        assert "project_id" in props, cmd_cls.name
        assert "root_dir" not in props, cmd_cls.name


def test_sample_commands_metadata_has_no_root_dir_drift() -> None:
    for cmd_cls, meta_fn in SAMPLE_COMMANDS:
        schema = cmd_cls.get_schema()
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        meta = _resolve_metadata(meta_fn)
        mparams = meta.get("parameters") or {}

        assert (
            "root_dir" not in mparams
        ), f"{cmd_cls.name}: metadata still documents root_dir"
        assert "project_id" in mparams, f"{cmd_cls.name}: metadata missing project_id"

        for key in mparams:
            assert key in props, f"{cmd_cls.name}: metadata param {key!r} not in schema"

        if "project_id" in required:
            assert mparams["project_id"].get("required") is True, cmd_cls.name

        for example in meta.get("usage_examples") or []:
            command = example.get("command") or {}
            assert (
                "root_dir" not in command
            ), f"{cmd_cls.name}: usage example still uses root_dir"
            if command:
                assert (
                    "project_id" in command
                ), f"{cmd_cls.name}: usage example missing project_id"


def test_sample_commands_metadata_examples_match_schema_keys() -> None:
    for cmd_cls, meta_fn in SAMPLE_COMMANDS:
        schema = cmd_cls.get_schema()
        props = set((schema.get("properties") or {}).keys())
        meta = _resolve_metadata(meta_fn)
        for example in meta.get("usage_examples") or []:
            command = example.get("command") or {}
            extra = set(command.keys()) - props
            assert (
                not extra
            ), f"{cmd_cls.name}: example keys {extra} not in schema properties"
