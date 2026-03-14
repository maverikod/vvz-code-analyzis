"""
JSON schema for cst_modify_tree command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict


def get_cst_modify_tree_schema() -> Dict[str, Any]:
    """Return JSON schema for cst_modify_tree command parameters."""
    return {
        "type": "object",
        "properties": {
            "tree_id": {
                "type": "string",
                "description": "Tree ID from cst_load_file",
            },
            "preview": {
                "type": "boolean",
                "description": (
                    "Preview mode: show changes without applying (default: false). "
                    "Recommended first step for AI models before write operations."
                ),
            },
            "operations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "replace",
                                "replace_many",
                                "replace_range",
                                "insert",
                                "delete",
                                "move",
                            ],
                            "description": "Operation type",
                        },
                        "replacements": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "selector": {"type": "string"},
                                    "match_index": {"type": "integer"},
                                    "code": {"type": "string"},
                                    "code_lines": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "description": (
                                    "For replace_many: selector and code/code_lines per replacement."
                                ),
                            },
                            "description": (
                                "Shorthand: only for action replace_many. "
                                "Expanded into multiple replace ops internally."
                            ),
                        },
                        "node_id": {
                            "type": "string",
                            "description": (
                                "Node ID for replace/delete/insert/move (from cst_find_node). "
                                "For replace and delete: provide exactly one of node_id or selector."
                            ),
                        },
                        "selector": {
                            "type": "string",
                            "description": (
                                "XPath-like CSTQuery selector (alternative to node_id for replace/delete). "
                                "Requires tree_id. Use with match_index or replace_all for multi-node ops. "
                                "For replace and delete: provide exactly one of node_id or selector."
                            ),
                        },
                        "match_index": {
                            "type": "integer",
                            "description": (
                                "When using selector: which match (0-based). Default 0. "
                                "Omit or 0 for first match."
                            ),
                        },
                        "replace_all": {
                            "type": "boolean",
                            "description": "When using selector: apply to all matches. Default false.",
                        },
                        "code": {
                            "type": "string",
                            "description": (
                                "New code for replace/insert operations (single string, "
                                "may have escaping issues with multi-line)"
                            ),
                        },
                        "code_lines": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "New code as list of lines (alternative to code, "
                                "recommended for multi-line code to avoid JSON escaping issues)"
                            ),
                        },
                        "position": {
                            "description": (
                                "Position for insert/move: 'first', 'last', 'before', 'after', 'end'; "
                                'or object {"after": N} for after 0-based sibling index N.'
                            ),
                            "oneOf": [
                                {
                                    "type": "string",
                                    "enum": [
                                        "first",
                                        "last",
                                        "before",
                                        "after",
                                        "end",
                                    ],
                                },
                                {
                                    "type": "object",
                                    "properties": {"after": {"type": "integer"}},
                                    "required": ["after"],
                                },
                            ],
                        },
                        "parent_node_id": {
                            "type": "string",
                            "description": (
                                "Parent node ID for insert/move. Use __root__ for module-level placement. "
                                "For module docstring insertion use action=insert, parent_node_id=__root__, "
                                "position=first, and code_lines for multiline content."
                            ),
                        },
                        "target_node_id": {
                            "type": "string",
                            "description": (
                                "Target node ID for insert operation (insert before/after this node, "
                                "alternative to parent_node_id)"
                            ),
                        },
                        "start_node_id": {
                            "type": "string",
                            "description": (
                                "Start node ID for replace_range operation "
                                "(first node in range to replace)"
                            ),
                        },
                        "end_node_id": {
                            "type": "string",
                            "description": (
                                "End node ID for replace_range operation "
                                "(last node in range to replace)"
                            ),
                        },
                    },
                    "required": ["action"],
                },
                "description": "List of operations to apply atomically",
            },
            "project_id": {
                "type": "string",
                "description": (
                    "Optional. When set with file_path, apply operations then save tree to file. "
                    "On save failure, in-memory tree is rolled back and save_error is returned."
                ),
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Optional. Target file path (relative to project root). "
                    "Used with project_id for apply+save in one request."
                ),
            },
            "validate": {
                "type": "boolean",
                "default": True,
                "description": "Validate before saving (when project_id+file_path are set)",
            },
            "backup": {
                "type": "boolean",
                "default": True,
                "description": "Create backup when saving (when project_id+file_path are set)",
            },
            "commit_message": {
                "type": "string",
                "description": "Optional git commit message when saving",
            },
        },
        "required": ["tree_id", "operations"],
        "additionalProperties": False,
    }
