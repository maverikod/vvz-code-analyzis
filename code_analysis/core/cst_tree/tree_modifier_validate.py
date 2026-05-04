"""
CST tree modifier - operation validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Optional

import libcst as cst

from .models import CSTTree, ROOT_NODE_ID_SENTINEL, TreeOperation, TreeOperationType
from .tree_metadata import _resolve_node_id as resolve_parent_id
from .tree_modifier_ops import (
    FINE_GRAINED_REPLACE_NODE_TYPES,
    parse_annotation_snippet,
    parse_code_snippet,
    parse_param_snippet,
)


def _validate_operation(tree: CSTTree, operation: TreeOperation) -> None:
    """Validate an operation before applying it."""
    _STALE_HINT = (
        " node_id values are invalidated after cst_save_tree — "
        "call cst_load_file again to get fresh node_ids."
    )
    if operation.action == TreeOperationType.DELETE:
        if operation.node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"Node not found for deletion: {operation.node_id}."
                + _STALE_HINT
                + f" Available nodes (first 5): {available}"
            )
    elif operation.action == TreeOperationType.REPLACE:
        if operation.node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"Node not found for replacement: {operation.node_id}."
                + _STALE_HINT
                + f" Available nodes (first 5): {available}"
            )
        if not operation.code and not operation.code_lines:
            raise ValueError("code or code_lines required for replace operation")
        meta = tree.metadata_map.get(operation.node_id)
        try:
            if meta and meta.type in FINE_GRAINED_REPLACE_NODE_TYPES:
                if meta.type == "Name":
                    text = (
                        "\n".join(operation.code_lines)
                        if operation.code_lines
                        else (operation.code or "")
                    )
                    cst.parse_expression(text.strip())
                elif meta.type == "Annotation":
                    parse_annotation_snippet(
                        code=operation.code, code_lines=operation.code_lines
                    )
                elif meta.type == "Param":
                    parse_param_snippet(
                        code=operation.code, code_lines=operation.code_lines
                    )
                else:
                    raise ValueError(
                        f"Unexpected fine-grained replace type: {meta.type!r}"
                    )
            else:
                parse_code_snippet(code=operation.code, code_lines=operation.code_lines)
        except Exception as e:
            raise ValueError(f"Invalid code syntax for replace: {e}") from e
    elif operation.action == TreeOperationType.REPLACE_RANGE:
        if not operation.start_node_id or not operation.end_node_id:
            raise ValueError(
                "start_node_id and end_node_id required for replace_range operation"
            )
        if operation.start_node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"Start node not found for replace_range: {operation.start_node_id}."
                + _STALE_HINT
                + f" Available nodes (first 5): {available}"
            )
        if operation.end_node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
