"""
Metadata for zero-argument and adapter health MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from .command_metadata_helpers import (
    build_command_metadata,
    empty_params_schema,
    simple_success_return,
)


def _zero_arg_meta(
    cls: Type[Any],
    *,
    detailed_description: str,
    usage_examples: list[Dict[str, Any]],
    error_cases: Dict[str, Any],
    return_value: Dict[str, Any],
    best_practices: list[str],
) -> Dict[str, Any]:
    return build_command_metadata(
        cls,
        detailed_description=detailed_description,
        parameters={},
        usage_examples=usage_examples,
        error_cases=error_cases,
        return_value=return_value,
        best_practices=best_practices,
    )


def list_watch_dirs_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return _zero_arg_meta(
        cls,
        detailed_description=(
            "Returns all watch directories registered in the server database. "
            "Each row includes ``id`` (use as ``watch_dir_id`` in ``create_project``), "
            "``name``, and ``absolute_path``. No parameters; database path comes from server config."
        ),
        usage_examples=[
            {
                "description": "Discover watch_dir_id before create_project",
                "command": {},
                "explanation": "Use returned id in create_project.watch_dir_id.",
            },
        ],
        error_cases={
            "LIST_WATCH_DIRS_ERROR": {
                "description": "Database or query failure.",
                "solution": "Check server logs and database connectivity.",
            },
        },
        return_value=simple_success_return(
            data_fields={
                "watch_dirs": "List of {id, name, absolute_path}.",
                "count": "Number of directories.",
            },
            example={"watch_dirs": [], "count": 0},
        ),
        best_practices=[
            "Call before create_project when watch_dir_id is unknown.",
            "Prefer project-relative paths after the project exists.",
        ],
    )


def cst_list_trees_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return _zero_arg_meta(
        cls,
        detailed_description=(
            "Lists in-memory CST trees (tree_id, file_path, idle time, TTL). "
            "Use before cst_unload_tree or to debug memory usage."
        ),
        usage_examples=[
            {
                "description": "List loaded trees",
                "command": {},
                "explanation": "Returns TTL-related fields per tree.",
            },
        ],
        error_cases={},
        return_value=simple_success_return(
            data_fields={"trees": "List of loaded tree summaries."},
            example={"trees": []},
        ),
        best_practices=["Unload unused trees to free memory."],
    )


def cst_unload_tree_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return build_command_metadata(
        cls,
        detailed_description=cls.descr,
        usage_examples=[
            {
                "description": "Unload a session",
                "command": {"tree_id": "550e8400-e29b-41d4-a716-446655440000"},
                "explanation": "tree_id from cst_load_file.",
            },
        ],
        error_cases={
            "TREE_NOT_FOUND": {
                "description": "tree_id is not loaded.",
                "solution": "Call cst_list_trees to see active sessions.",
            },
        },
        return_value=simple_success_return(
            example={
                "success": True,
                "tree_id": "550e8400-e29b-41d4-a716-446655440000",
            },
        ),
        best_practices=["Unload after cst_save_tree when edits are persisted."],
    )


def health_command_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return _zero_arg_meta(
        cls,
        detailed_description=(
            "Server health: uptime, memory, registered command count, proxy registration, "
            "CST trees in memory, and queue dependency compatibility (mcp-proxy-adapter / queuemgr)."
        ),
        usage_examples=[
            {
                "description": "Probe server health",
                "command": {},
                "explanation": "status may be degraded when queue dependencies mismatch.",
            },
        ],
        error_cases={},
        return_value=simple_success_return(
            data_fields={
                "status": "ok | degraded",
                "components": "system, process, commands, queue_dependencies, …",
            },
            example={"status": "ok"},
        ),
        best_practices=["Run after deploy or dependency upgrades."],
    )


def queue_health_command_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return _zero_arg_meta(
        cls,
        detailed_description=(
            "Queue subsystem health from queuemgr plus dependency version checks. "
            "Fails with QUEUE_DEPENDENCY_INCOMPATIBLE when versions are below minimum."
        ),
        usage_examples=[
            {
                "description": "Check queue",
                "command": {},
                "explanation": "No parameters.",
            },
        ],
        error_cases={
            "QUEUE_DEPENDENCY_INCOMPATIBLE": {
                "description": "mcp-proxy-adapter or queuemgr version too old.",
                "solution": "Upgrade packages per pyproject.toml minimums.",
            },
        },
        return_value=simple_success_return(example={"status": "healthy"}),
        best_practices=["Use with queue_get_job_status for long-running jobs."],
    )


def qa_sleep_command_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return build_command_metadata(
        cls,
        detailed_description=(
            "Test-only sleep with heartbeat logs for queue lifecycle regression. "
            "Not for production workflows."
        ),
        usage_examples=[
            {
                "description": "Short sleep",
                "command": {"seconds": 2.0, "tick_seconds": 0.5},
                "explanation": "Defaults: seconds=30, tick_seconds=0.5.",
            },
        ],
        error_cases={},
        return_value=simple_success_return(
            data_fields={"slept_seconds": "Actual elapsed time."},
            example={"slept_seconds": 2.0, "success": True},
        ),
        best_practices=["Use only in automated queue tests."],
    )
