"""
CST tree modifier - modify tree with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


import logging
import hashlib

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

from .tree_modifier_ops_parse import (
    FINE_GRAINED_REPLACE_NODE_TYPES,
    class_or_function_snippet_needs_full_replace,
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


def _use_mutable_batch_path(operations: List[TreeOperation], tree: CSTTree) -> bool:
    """
    True when batch path (mutable layer) should be used: more than one replace,
    or more than one insert, or any delete; and no REPLACE_RANGE or MOVE.

    Batches that include REPLACE or DELETE targeting fine-grained node types
    (Param, Name) use the LibCST sequential path instead.
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
    for op in operations:
        if op.action not in (TreeOperationType.REPLACE, TreeOperationType.DELETE):
            continue
        nid = op.node_id
        if not nid:
            continue
        meta = tree.metadata_map.get(nid)
        if meta is None:
            continue
        node_obj = tree.node_map.get(nid)
        if node_obj is not None and isinstance(node_obj, cst.BaseExpression):
            return False
        node_type = getattr(meta, "type", "")
        if node_type and node_type in FINE_GRAINED_REPLACE_NODE_TYPES:
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

    for op in operations:
        _validate_operation(tree, op)

    sorted_ops = _sort_operations_for_batch(operations, tree)

    previous_metadata_map: Dict[str, TreeNodeMetadata] = dict(tree.metadata_map)
    replaced_positions_to_id: Dict[Tuple[int, int, str], str] = {}
    for op in sorted_ops:
        if op.action == TreeOperationType.REPLACE and op.node_id:
            meta = tree.metadata_map.get(op.node_id)
            if meta and hasattr(meta, "start_line") and hasattr(meta, "start_col"):
                replaced_positions_to_id[
                    (meta.start_line, meta.start_col, meta.type)
                ] = op.node_id
        elif op.action == TreeOperationType.REPLACE_RANGE and op.start_node_id:
            meta = tree.metadata_map.get(op.start_node_id)
            if meta and hasattr(meta, "start_line") and hasattr(meta, "start_col"):
                replaced_positions_to_id[
                    (meta.start_line, meta.start_col, meta.type)
                ] = op.start_node_id

    use_mutable_batch = _use_mutable_batch_path(operations, tree)

    try:
        if use_mutable_batch:
            mutable_tree = build_from_libcst(
                tree.module, tree.metadata_map, tree.node_map
            )
            apply_operations(mutable_tree, sorted_ops, tree.metadata_map)
            source = serialize_to_source(mutable_tree)
            new_module = cst.parse_module(source)
            _validate_module(new_module)
            tree.module = new_module
            prev_obj_to_id: Dict[int, str] = {
                id(v): k for k, v in tree.node_map.items()
            }
            tree.node_map.clear()
            tree.metadata_map.clear()
            tree.parent_map.clear()
            _build_tree_index(
                tree,
                node_types=None,
                max_depth=None,
                include_children=True,
                previous_obj_to_id=prev_obj_to_id,
            )
            tree.module_source_sha256_hex = hashlib.sha256(
                tree.module.code.encode("utf-8")
            ).hexdigest()
            return tree

        modified_module = tree.module
        sequential_multi = len(sorted_ops) > 1 and not use_mutable_batch
        completed_replaced: Dict[Tuple[int, int, str], str] = {}
        for op in sorted_ops:
            modified_module = _apply_operation(modified_module, tree, op)
            tree.module = modified_module
            _remove_operation_nodes_from_index(tree, op)
            if sequential_multi:
                if op.action == TreeOperationType.REPLACE and op.node_id:
                    om = previous_metadata_map.get(op.node_id)
                    if om and hasattr(om, "start_line") and hasattr(om, "start_col"):
                        completed_replaced[(om.start_line, om.start_col, om.type)] = (
                            op.node_id
                        )
                elif op.action == TreeOperationType.REPLACE_RANGE and op.start_node_id:
                    om = previous_metadata_map.get(op.start_node_id)
                    if om and hasattr(om, "start_line") and hasattr(om, "start_col"):
                        completed_replaced[(om.start_line, om.start_col, om.type)] = (
                            op.start_node_id
                        )
                prev_obj_to_id = {id(v): k for k, v in tree.node_map.items()}
                tree.node_map.clear()
                tree.metadata_map.clear()
                tree.parent_map.clear()
                _build_tree_index(
                    tree,
                    node_types=None,
                    max_depth=None,
                    include_children=True,
                    previous_metadata_map=previous_metadata_map,
                    replaced_positions_to_id=(
                        dict(completed_replaced) if completed_replaced else None
                    ),
                    previous_obj_to_id=prev_obj_to_id,
                )

        if not sequential_multi:
            prev_obj_to_id = {id(v): k for k, v in tree.node_map.items()}
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
                previous_obj_to_id=prev_obj_to_id,
            )

        _validate_module(modified_module)
        tree.module_source_sha256_hex = hashlib.sha256(
            tree.module.code.encode("utf-8")
        ).hexdigest()
        return tree

    except Exception as e:
        logger.error(f"Error applying operations to tree {tree_id}: {e}")
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
    Find the nearest ancestor node_id that has an insertable statement body.

    Resolves stale UUIDs via tree.node_id_aliases before lookup.
    Walks up the parent_id chain until it finds a node whose type is one of:
    Module, IndentedBlock, ClassDef, FunctionDef — i.e. a node that can serve
    as parent_node_id for insert_node_relative / insert_node_at_position.

    This means callers can pass any node_id (e.g. Import inside
    SimpleStatementLine, Name inside FunctionDef) and always get back a
    valid insertable container — no manual level-picking required.

    Args:
        tree: CSTTree
        node_id: Node ID to find insertable parent for

    Returns:
        Parent node_id of nearest insertable container, or None if not found
    """
    # Statement-body container types — these are valid parent_node_id values
    INSERTABLE_TYPES = {"Module", "IndentedBlock", "ClassDef", "FunctionDef"}

    # Resolve alias: after insert the target node may have a new UUID
    resolved = tree.node_id_aliases.get(node_id, node_id)
    metadata = tree.metadata_map.get(resolved)
    if metadata is None and resolved != node_id:
        metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return None

    # Walk up parent_id chain until we reach an insertable container
    current_id = metadata.parent_id
    while current_id is not None:
        current_meta = tree.metadata_map.get(current_id)
        if current_meta is None:
            break
        if current_meta.type in INSERTABLE_TYPES:
            return current_id
        current_id = current_meta.parent_id

    return None


def _replace_node_header(
    module: cst.Module,
    tree: CSTTree,
    node_id: str,
    code: str,
) -> cst.Module:
    """Replace only the header of a ClassDef or FunctionDef, preserving the body.

    Parses ``code`` as a class/function stub (with ``pass`` body if needed),
    extracts the new name, bases (for class) or params/returns (for function),
    and patches the existing LibCST node in-place, keeping its original body.

    Args:
        module: Current LibCST module.
        tree: CSTTree containing node metadata and node_map.
        node_id: ID of the ClassDef or FunctionDef node to patch.
        code: New header code, e.g. ``'class Foo(Base):'`` or
              ``'def bar(self, x: int) -> str:'``.

    Returns:
        Updated module with only the header replaced.
    """
    # Resolve node
    resolved_id = tree.node_id_aliases.get(node_id, node_id)
    old_node = tree.node_map.get(resolved_id) or tree.node_map.get(node_id)
    if old_node is None:
        raise ValueError(f"Node not found for header-replace: {node_id}")

    # Parse the new header — append a pass body so libcst accepts it
    stub = code.rstrip()
    if not stub.endswith(":"):
        stub = stub + ":"
    stub_src = stub + "\n    pass\n"
    try:
        parsed = cst.parse_module(stub_src)
    except cst.ParserSyntaxError as exc:
        raise ValueError(f"Invalid header code: {exc}") from exc

    new_node_raw = parsed.body[0]

    if isinstance(old_node, cst.ClassDef) and isinstance(new_node_raw, cst.ClassDef):
        patched = old_node.with_changes(
            name=new_node_raw.name,
            bases=new_node_raw.bases,
            keywords=new_node_raw.keywords,
            decorators=new_node_raw.decorators,
        )
    elif isinstance(old_node, cst.FunctionDef) and isinstance(
        new_node_raw, cst.FunctionDef
    ):
        patched = old_node.with_changes(
            name=new_node_raw.name,
            params=new_node_raw.params,
            returns=new_node_raw.returns,
            decorators=new_node_raw.decorators,
        )
    else:
        # Type mismatch or unsupported node — fall back to full replace
        logger.warning(
            "_replace_node_header: node %s type mismatch (old=%s, new=%s), falling back to full replace",
            node_id,
            type(old_node).__name__,
            type(new_node_raw).__name__,
        )
        return replace_node(module, tree, node_id, code)

    # Swap the node in place using a CSTTransformer
    class _HeaderPatcher(cst.CSTTransformer):
        def __init__(self, target: cst.CSTNode, replacement: cst.CSTNode) -> None:
            self._target = target
            self._replacement = replacement
            self._replaced = False

        def on_leave(
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode:
            if original_node is self._target and not self._replaced:
                self._replaced = True
                return self._replacement
            return updated_node

    patcher = _HeaderPatcher(old_node, patched)
    new_module = module.visit(patcher)
    if not patcher._replaced:
        raise ValueError(
            f"Node {node_id} (type={type(old_node).__name__}) was not patched in module. "
            "Hint: node may be stale — reload tree via cst_load_file."
        )
    # Update node_map so subsequent operations see the new node
    tree.node_map[resolved_id] = patched
    return new_module


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
        if not operation.replace_all_child_nodes:
            _nid = tree.node_id_aliases.get(operation.node_id, operation.node_id)
            _meta = tree.metadata_map.get(_nid) or tree.metadata_map.get(
                operation.node_id
            )
            if (
                _meta
                and _meta.type in ("ClassDef", "FunctionDef")
                and not class_or_function_snippet_needs_full_replace(code)
            ):
                return _replace_node_header(module, tree, operation.node_id, code)
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
