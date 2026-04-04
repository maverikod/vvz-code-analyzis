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
    if operation.action == TreeOperationType.DELETE:
        if operation.node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"Node not found for deletion: {operation.node_id}. "
                f"Available nodes (first 5): {available}"
            )
    elif operation.action == TreeOperationType.REPLACE:
        if operation.node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"Node not found for replacement: {operation.node_id}. "
                f"Available nodes (first 5): {available}"
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
                f"Start node not found for replace_range: {operation.start_node_id}. "
                f"Available nodes (first 5): {available}"
            )
        if operation.end_node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"End node not found for replace_range: {operation.end_node_id}. "
                f"Available nodes (first 5): {available}"
            )
        if not operation.code and not operation.code_lines:
            raise ValueError("code or code_lines required for replace_range operation")
        try:
            parse_code_snippet(code=operation.code, code_lines=operation.code_lines)
        except Exception as e:
            raise ValueError(f"Invalid code syntax for replace_range: {e}") from e
    elif operation.action == TreeOperationType.INSERT:
        if not operation.code and not operation.code_lines:
            raise ValueError("code or code_lines required for insert operation")
        if not operation.parent_node_id and not operation.target_node_id:
            raise ValueError(
                "parent_node_id or target_node_id required for insert operation"
            )
        if operation.parent_node_id:
            resolved_parent = resolve_parent_id(tree, operation.parent_node_id.strip())
            if resolved_parent and resolved_parent not in tree.node_map:
                available = list(tree.node_map.keys())[:5]
                raise ValueError(
                    f"Parent node not found: {operation.parent_node_id}. "
                    f"Available nodes (first 5): {available}"
                )
        if operation.target_node_id and operation.target_node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"Target node not found: {operation.target_node_id}. "
                f"Available nodes (first 5): {available}"
            )
        if operation.target_node_id:
            if operation.position not in ("before", "after"):
                raise ValueError(
                    "position must be 'before' or 'after' for insert relative to target node"
                )
        elif operation.parent_node_id:
            pos = (operation.position or "last").strip().lower()
            if pos not in ("before", "after", "end", "first", "last"):
                raise ValueError(
                    "position must be 'first', 'last', 'before', 'after', or 'end' "
                    "for insert in parent node"
                )
            if pos == "after" and operation.position_after_index is None:
                raise ValueError(
                    'position_after_index (or position {"after": N}) required when '
                    "position is 'after' for insert in parent"
                )
        try:
            parse_code_snippet(code=operation.code, code_lines=operation.code_lines)
        except Exception as e:
            raise ValueError(f"Invalid code syntax for insert: {e}") from e
    elif operation.action == TreeOperationType.MOVE:
        if not operation.node_id or operation.node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"Node not found for move: {operation.node_id}. "
                f"Available nodes (first 5): {available}"
            )
        parent_id = (operation.parent_node_id or ROOT_NODE_ID_SENTINEL).strip()
        if parent_id == ROOT_NODE_ID_SENTINEL:
            parent_id = resolve_parent_id(tree, ROOT_NODE_ID_SENTINEL)
        if parent_id and parent_id not in tree.node_map:
            raise ValueError(
                f"Parent node not found for move: {parent_id}. "
                "Use __root__ for module-level placement."
            )
        pos = (operation.position or "last").strip().lower()
        if pos not in ("first", "last", "after"):
            raise ValueError(
                f"position for move must be 'first', 'last', or 'after', got {pos!r}"
            )
        if pos == "after" and operation.position_after_index is None:
            raise ValueError(
                "position_after_index required when position is 'after' for move"
            )
        if parent_id:
            ancestor: Optional[str] = parent_id
            while ancestor:
                if ancestor == operation.node_id:
                    raise ValueError(
                        f"Cannot move node into its own descendant: "
                        f"parent {parent_id} is under node {operation.node_id}"
                    )
                meta = tree.metadata_map.get(ancestor)
                ancestor = meta.parent_id if meta else None  # type: ignore[assignment]
