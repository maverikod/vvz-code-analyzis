"""
Shared metadata builders for JSON tree MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from .command_metadata_helpers import (
    build_command_metadata,
    parameters_from_schema,
    project_file_error_cases,
    simple_success_return,
)


def _json_tree_return(op: str) -> Dict[str, Any]:
    """Build the standard return-value metadata for a JSON tree operation."""
    return simple_success_return(
        description=f"JSON tree {op} completed.",
        data_fields={
            "success": "True on success.",
            "tree_id": "Session id for in-memory JSON tree (when applicable).",
            "nodes": "Node metadata list (load/find/get_info).",
        },
        example={"success": True, "tree_id": "550e8400-e29b-41d4-a716-446655440000"},
    )


def json_tree_command_metadata(
    cls: Type[Any],
    *,
    operation: str,
    detailed_description: str,
    example_params: Dict[str, Any],
    extra_errors: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build standard metadata for json_* commands."""
    errors = dict(project_file_error_cases())
    errors["INVALID_JSON"] = {
        "description": "File content is not valid JSON.",
        "solution": "Fix the file or use a JSON linter before loading.",
    }
    errors["JSON_LOAD_ERROR"] = {
        "description": f"Unexpected failure during json_{operation}.",
    }
    if extra_errors:
        errors.update(extra_errors)
    return build_command_metadata(
        cls,
        detailed_description=detailed_description,
        parameters=parameters_from_schema(cls.get_schema()),
        usage_examples=[
            {
                "description": f"Example json_{operation}",
                "command": dict(example_params),
                "explanation": "Paths are relative to the project root.",
            },
        ],
        error_cases=errors,
        return_value=_json_tree_return(operation),
        best_practices=[
            "Use list_json_blocks or json_find_node to discover node ids before modify.",
            "Unload trees with json_reload_tree / session cleanup when finished.",
            "Only .json files are supported.",
        ],
    )
