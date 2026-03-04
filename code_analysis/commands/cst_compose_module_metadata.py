"""
Metadata for compose_cst_module command (AI/docs, usage examples).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_compose_cst_module_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """
    Get detailed command metadata for compose_cst_module (AI models).

    Returns:
        Dictionary with command metadata including usage_examples.
    """
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "The compose_cst_module command applies CST changes to a file with atomic operations. "
            "Two modes: (1) tree_id + optional node_id — attach a branch (CST tree) to a node or overwrite file; "
            "(2) ops — list of selector + new_code patches (e.g. replace by function name, range, cst_query). "
            "Selector kinds: module, function, class, method, range, block_id, node_id, cst_query. "
            "When apply=true (default), validates (compile, flake8, mypy, docstrings), backs up, and writes. "
            "Use apply=false with return_diff=true to preview without writing.\n\n"
            "Important for AI usage:\n"
            "- compose_cst_module (apply=true) performs full quality validation before write.\n"
            "- If your task is narrow (for example only adding docstrings) and full validation blocks write,\n"
            "  use cst_modify_tree + cst_save_tree workflow, then run quality checks explicitly.\n"
            "- Always start with apply=false, return_diff=true before applying."
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID. Required.",
                "type": "string",
                "required": True,
            },
            "file_path": {
                "description": "Target .py path relative to project root.",
                "type": "string",
                "required": True,
            },
            "tree_id": {
                "description": "CST tree ID from cst_load_file (branch to attach). Use with node_id or omit to overwrite file.",
                "type": "string",
            },
            "node_id": {
                "description": "Node ID to attach branch to (tree_id mode). Empty = overwrite file with branch.",
                "type": "string",
            },
            "ops": {
                "description": "List of { selector: { kind, ... }, new_code [, file_docstring ] }. Use instead of tree_id for selector-based patches.",
                "type": "array",
            },
            "apply": {
                "description": "If true (default), write to file. If false, only return diff/stats.",
                "type": "boolean",
                "default": True,
            },
            "create_backup": {
                "description": "Create backup before writing (when apply=true).",
                "type": "boolean",
                "default": True,
            },
            "return_diff": {
                "description": "Include unified diff in response.",
                "type": "boolean",
                "default": False,
            },
            "commit_message": {
                "description": "Optional git commit message.",
                "type": "string",
            },
        },
        "return_value": {
            "success": {
                "description": "On success: data with applied count, backup_uuid, diff (if requested)."
            },
            "error": {
                "description": "On failure: code (e.g. INVALID_PARAMS, PROJECT_NOT_FOUND), message, details."
            },
        },
        "usage_examples": _get_usage_examples(),
    }


def _get_usage_examples() -> list[Dict[str, Any]]:
    """Return usage_examples list for compose_cst_module metadata."""
    return [
        {
            "description": "Replace an import (ops mode, cst_query selector)",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "ops": [
                    {
                        "selector": {
                            "kind": "cst_query",
                            "query": "ImportFrom[module='.task_status']",
                            "match_index": 0,
                        },
                        "new_code": "from ..task_status import TaskStatus",
                    }
                ],
                "apply": True,
                "create_backup": True,
            },
            "explanation": (
                "Replaces the first ImportFrom matching the CSTQuery. "
                "Selector kinds for ops: module, function, class, method, range, block_id, node_id, cst_query."
            ),
        },
        {
            "description": "Replace code by line range (ops mode, range selector)",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/utils.py",
                "ops": [
                    {
                        "selector": {
                            "kind": "range",
                            "start_line": 10,
                            "end_line": 15,
                        },
                        "new_code": "# replaced lines 10-15",
                    }
                ],
                "apply": False,
                "return_diff": True,
            },
            "explanation": (
                "Replaces the block covering lines 10-15 (1-based). "
                "apply=false returns diff without writing; use apply=true to write."
            ),
        },
        {
            "description": "Preview-only first, then apply",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "ops": [
                    {
                        "selector": {"kind": "function", "name": "process_data"},
                        "new_code": 'def process_data(items):\n    """Process input items and return normalized result."""\n    return items',
                    }
                ],
                "apply": False,
                "return_diff": True,
            },
            "explanation": (
                "Recommended pattern for AI: first preview changes with apply=false. "
                "If diff is correct, repeat with apply=true."
            ),
        },
        {
            "description": "Replace function by name (ops mode, function selector)",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "ops": [
                    {
                        "selector": {"kind": "function", "name": "old_helper"},
                        "new_code": "def old_helper():\n    return default",
                    }
                ],
            },
            "explanation": (
                "Replaces the function named old_helper with new code. "
                "Selector kind 'function' requires 'name'."
            ),
        },
        {
            "description": "Attach branch to node (tree_id mode)",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "node_id": "function:process_data:FunctionDef:10:0-30:0",
            },
            "explanation": (
                "Inserts the CST tree (branch) from cst_load_file into the process_data function. "
                "Omit node_id to overwrite the entire file with the branch."
            ),
        },
    ]
