"""
CST tree modifier - modify tree with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import libcst as cst

from .models import (
    CSTTree,
    ROOT_NODE_ID_SENTINEL,
    TreeOperation,
    TreeOperationType,
    TreeNodeMetadata,
)
from .tree_builder import _build_tree_index, get_tree
from .tree_metadata import _resolve_node_id as resolve_parent_id
from .tree_modifier_ops import (
    delete_node,
    insert_node_at_position,
    insert_node_relative,
    replace_node,
    replace_range,
)
from .tree_modifier_validate import _validate_operation

try:
    from code_analysis.core.mutable_cst import (
        apply_operations,
        build_from_libcst,
        serialize_to_source,
    )
except ImportError:
    build_from_libcst = None  # type: ignore[assignment]
    serialize_to_source = None  # type: ignore[assignment]
    apply_operations = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _apply_libcst_codegen_compat() -> None:
    """
    Work around libcst codegen passing default_semicolon to nodes that do not accept it.

    In libcst 1.8.x the codegen caller may pass default_semicolon= to _codegen_impl(),
    but SimpleStatementLine._codegen_impl(self, state) does not accept it, causing
    TypeError. We wrap _codegen_impl to accept **kwargs and ignore them.
    """
    orig = cst.SimpleStatementLine._codegen_impl

    def _codegen_impl_compat(
        self: cst.SimpleStatementLine,
        state: object,
        **kwargs: object,
    ) -> None:
        orig(self, state)  # type: ignore[arg-type]

    cst.SimpleStatementLine._codegen_impl = _codegen_impl_compat  # type: ignore[method-assign]


_apply_libcst_codegen_compat()


def _use_mutable_batch_path(operations: List[TreeOperation]) -> bool:
    """
    True when batch path (mutable layer) should be used: more than one replace,
    or more than one insert, or any delete; and no REPLACE_RANGE or MOVE.
    """
    if (
        build_from_libcst is None
        or serialize_to_source is None
        or apply_operations is None
    ):
        return False
    replace_count = sum(
        1 for op in operations if op.action == TreeOperationType.REPLACE
    )
    insert_count = sum(1 for op in operations if op.action == TreeOperationType.INSERT)
    has_delete = any(op.action == TreeOperationType.DELETE for op in operations)
    has_range_or_move = any(
        op.action in (TreeOperationType.REPLACE_RANGE, TreeOperationType.MOVE)
        for op in operations
    )
    if has_range_or_move:
        return False
    return replace_count > 1 or insert_count > 1 or has_delete


def modify_tree(tree_id: str, operations: List[TreeOperation]) -> CSTTree:
    """
    Modify tree with atomic operations.

    All operations are validated before being applied.
    If any operation fails, all changes are rolled back.

    Args:
        tree_id: Tree ID
        operations: List of operations to apply

    Returns:
        Modified CSTTree

    Raises:
        ValueError: If any operation is invalid
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    # Validate all operations first
    for op in operations:
        _validate_operation(tree, op)

    # Sort DELETE operations by position descending (bottom-to-top) so that
    # deleting one node does not shift positions of nodes we have not yet deleted.
    # This avoids "Node was not removed" when node from stale node_map is not in
    # the updated module.
    sorted_ops = _sort_operations_for_batch(operations, tree)

    # Snapshot metadata before any changes so we can preserve node_ids on rebuild.
    # Replace: same node_id is assigned to the new content at (start_line, start_col).
    previous_metadata_map: Dict[str, TreeNodeMetadata] = dict(tree.metadata_map)
    replaced_positions_to_id: Dict[Tuple[int, int], str] = {}
    for op in sorted_ops:
        if op.action == TreeOperationType.REPLACE and op.node_id:
            meta = tree.metadata_map.get(op.node_id)
            if meta and hasattr(meta, "start_line") and hasattr(meta, "start_col"):
                replaced_positions_to_id[(meta.start_line, meta.start_col)] = op.node_id
        elif op.action == TreeOperationType.REPLACE_RANGE and op.start_node_id:
            meta = tree.metadata_map.get(op.start_node_id)
            if meta and hasattr(meta, "start_line") and hasattr(meta, "start_col"):
                replaced_positions_to_id[(meta.start_line, meta.start_col)] = (
                    op.start_node_id
                )

    try:
        if _use_mutable_batch_path(operations):
            mutable_tree = build_from_libcst(
                tree.module, tree.metadata_map, tree.node_map
            )
            apply_operations(mutable_tree, sorted_ops, tree.metadata_map)
            source = serialize_to_source(mutable_tree)
            new_module = cst.parse_module(source)
            _validate_module(new_module)
            tree.module = new_module
            tree.node_map.clear()
            tree.metadata_map.clear()
            tree.parent_map.clear()
            _build_tree_index(
                tree,
                node_types=None,
                max_depth=None,
                include_children=True,
            )
            return tree

        # Current LibCST path (single-op or REPLACE_RANGE/MOVE)
        modified_module = tree.module

        # Apply all operations. Do not rebuild index between ops so UUID node_ids
        # for unmodified nodes stay valid (batch replace at multiple points).
        for op in sorted_ops:
            modified_module = _apply_operation(modified_module, tree, op)
            tree.module = modified_module
            _remove_operation_nodes_from_index(tree, op)

        # Rebuild index preserving node_ids: unchanged nodes keep id, replaced node keeps id
        tree.node_map.clear()
        tree.metadata_map.clear()
        tree.parent_map.clear()
        _build_tree_index(
            tree,
            node_types=None,
            max_depth=None,
            include_children=True,
            previous_metadata_map=previous_metadata_map,
            replaced_positions_to_id=replaced_positions_to_id or None,
        )

        _validate_module(modified_module)

        return tree

    except Exception as e:
        logger.error(f"Error applying operations to tree {tree_id}: {e}")
        # Tree remains unchanged (we modified a copy)
        raise


def _sort_operations_for_batch(
    operations: List[TreeOperation], tree: CSTTree
) -> List[TreeOperation]:
    """
    Sort operations so DELETE and REPLACE run bottom-to-top (by position).
    INSERT ops run bottom-to-top by parent position.
    This prevents position shift from invalidating node references in batch.
    """
    deletes: List[Tuple[int, int, TreeOperation]] = []
    replaces: List[Tuple[int, int, TreeOperation]] = []
    inserts: List[Tuple[int, int, TreeOperation]] = []
    others: List[TreeOperation] = []
    for op in operations:
        if op.action == TreeOperationType.DELETE and op.node_id:
            meta = tree.metadata_map.get(op.node_id)
            line = meta.start_line if meta else 0
            col = meta.start_col if meta else 0
            deletes.append((-line, -col, op))  # negate for descending
        elif op.action == TreeOperationType.REPLACE and op.node_id:
            meta = tree.metadata_map.get(op.node_id)
            line = meta.start_line if meta else 0
            col = meta.start_col if meta else 0
            replaces.append((-line, -col, op))  # bottom-to-top
        elif op.action == TreeOperationType.INSERT and op.parent_node_id:
            meta = tree.metadata_map.get(op.parent_node_id)
            line = meta.start_line if meta else 0
            col = meta.start_col if meta else 0
            inserts.append((-line, -col, op))  # bottom-to-top
        else:
            others.append(op)
    deletes.sort(key=lambda x: (x[0], x[1]))
    replaces.sort(key=lambda x: (x[0], x[1]))
    inserts.sort(key=lambda x: (x[0], x[1]))
    return (
        [op for (_, _, op) in deletes]
        + [op for (_, _, op) in replaces]
        + [op for (_, _, op) in inserts]
        + others
    )


def _remove_operation_nodes_from_index(tree: CSTTree, operation: TreeOperation) -> None:
    """
    Remove from node_map/metadata_map/parent_map only the node(s) affected by
    this operation, so other node_ids (UUIDs) stay valid for the next operation.
    """
    to_remove: List[str] = []
    if operation.action == TreeOperationType.REPLACE and operation.node_id:
        to_remove.append(operation.node_id)
    elif operation.action == TreeOperationType.MOVE and operation.node_id:
        to_remove.append(operation.node_id)
    elif operation.action == TreeOperationType.DELETE and operation.node_id:
        to_remove.append(operation.node_id)
    elif operation.action == TreeOperationType.REPLACE_RANGE:
        if operation.start_node_id and operation.end_node_id:
            start_meta = tree.metadata_map.get(operation.start_node_id)
            end_meta = tree.metadata_map.get(operation.end_node_id)
            parent_id = start_meta.parent_id if start_meta else None
            if parent_id and end_meta and end_meta.parent_id == parent_id:
                parent_meta = tree.metadata_map.get(parent_id)
                if parent_meta and parent_meta.children_ids:
                    try:
                        i = parent_meta.children_ids.index(operation.start_node_id)
                        j = parent_meta.children_ids.index(operation.end_node_id)
                        if i <= j:
                            to_remove.extend(parent_meta.children_ids[i : j + 1])
                    except ValueError:
                        to_remove.extend(
                            [operation.start_node_id, operation.end_node_id]
                        )
            else:
                to_remove.extend([operation.start_node_id, operation.end_node_id])
        else:
            if operation.start_node_id:
                to_remove.append(operation.start_node_id)
            if operation.end_node_id:
                to_remove.append(operation.end_node_id)
    for nid in to_remove:
        tree.node_map.pop(nid, None)
        tree.metadata_map.pop(nid, None)
        tree.parent_map.pop(nid, None)


def _find_parent_for_node(tree: CSTTree, node_id: str) -> Optional[str]:
    """
    Find parent node_id for a given node_id.

    Args:
        tree: CSTTree
        node_id: Node ID to find parent for

    Returns:
        Parent node_id or None if not found
    """
    metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return None
    return metadata.parent_id


def _apply_operation(
    module: cst.Module, tree: CSTTree, operation: TreeOperation
) -> cst.Module:
    """Apply a single operation to module."""
    if operation.action == TreeOperationType.DELETE:
        return delete_node(module, tree, operation.node_id)
    elif operation.action == TreeOperationType.REPLACE:
        code = operation.code
        if operation.code_lines:
            code = "\n".join(operation.code_lines)
        if not code:
            raise ValueError("code or code_lines required for replace operation")
        return replace_node(module, tree, operation.node_id, code)
    elif operation.action == TreeOperationType.REPLACE_RANGE:
        code = operation.code
        if operation.code_lines:
            code = "\n".join(operation.code_lines)
        if not code:
            raise ValueError("code or code_lines required for replace_range operation")
        if not operation.start_node_id or not operation.end_node_id:
            raise ValueError(
                "start_node_id and end_node_id required for replace_range operation"
            )
        return replace_range(
            module, tree, operation.start_node_id, operation.end_node_id, code
        )
    elif operation.action == TreeOperationType.INSERT:
        # If target_node_id is provided, find parent automatically and insert relative to target
        code = operation.code
        if operation.code_lines:
            code = "\n".join(operation.code_lines)
        if not code:
            raise ValueError("code or code_lines required for insert operation")
        if operation.target_node_id:
            parent_id = _find_parent_for_node(tree, operation.target_node_id)
            if not parent_id:
                raise ValueError(
                    f"Cannot find parent for target node: {operation.target_node_id}"
                )
            position = operation.position or "after"
            return insert_node_relative(
                module,
                tree,
                operation.target_node_id,
                parent_id,
                code,
                position,
            )
        else:
            # Use parent_node_id (with optional first/last/after N)
            if not operation.parent_node_id:
                raise ValueError(
                    "parent_node_id or target_node_id required for insert operation"
                )
            position = (operation.position or "end").strip().lower()
            parent_id_raw = operation.parent_node_id or ROOT_NODE_ID_SENTINEL
            resolved_parent = resolve_parent_id(tree, parent_id_raw)
            if not resolved_parent:
                raise ValueError(
                    f"Parent node not found: {parent_id_raw}. "
                    "Use __root__ for module-level placement."
                )
            # Map legacy "before"/"after"/"end" to first/last when no target
            if position == "before":
                position = "first"
            elif position in ("after", "end"):
                position = "last"
            return insert_node_at_position(
                module,
                tree,
                resolved_parent,
                code,
                position=position,
                position_after_index=operation.position_after_index,
            )
    elif operation.action == TreeOperationType.MOVE:
        node_id = operation.node_id
        node = tree.node_map.get(node_id)
        if not node:
            raise ValueError(f"Node not found for move: {node_id}")
        code = tree.module.code_for_node(node)
        parent_id_raw = (operation.parent_node_id or ROOT_NODE_ID_SENTINEL).strip()
        move_parent_id = resolve_parent_id(tree, parent_id_raw)
        if not move_parent_id:
            raise ValueError(
                f"Parent node not found for move: {parent_id_raw}. "
                "Use __root__ for module-level placement."
            )
        position = (operation.position or "last").strip().lower()
        after_index = operation.position_after_index
        module_after_delete = delete_node(module, tree, node_id)
        return insert_node_at_position(
            module_after_delete,
            tree,
            move_parent_id,
            code,
            position=position,
            position_after_index=after_index,
        )
    else:
        raise ValueError(f"Unknown operation type: {operation.action}")


def _validate_module(module: cst.Module) -> None:
    """Validate module by compiling it."""
    try:
        compile(module.code, "<string>", "exec")
    except SyntaxError as e:
        raise ValueError(f"Module validation failed: {e}") from e
