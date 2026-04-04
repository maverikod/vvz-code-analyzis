"""
Find and delete nodes in CST module by position (for tree modifier operations).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Union, cast

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from .models import CSTTree
from .tree_modifier_ops_parse import FINE_GRAINED_REPLACE_NODE_TYPES


def delete_node(module: cst.Module, tree: CSTTree, node_id: str) -> cst.Module:
    """Delete a node from module."""
    metadata = tree.metadata_map.get(node_id)
    node = None
    if metadata and hasattr(metadata, "start_line"):
        use_leaf = metadata.type in FINE_GRAINED_REPLACE_NODE_TYPES
        if use_leaf:
            node = find_leaf_node_in_module_by_position(
                module,
                metadata.start_line,
                metadata.start_col,
                metadata.end_line,
                metadata.end_col,
            )
        if node is None:
            node = find_node_in_module_by_position(
                module,
                metadata.start_line,
                metadata.start_col,
                metadata.end_line,
                metadata.end_col,
            )
    if node is None:
        node = tree.node_map.get(node_id)
    if not node:
        raise ValueError(f"Node not found: {node_id}")

    # Use LibCST transformer to remove the node
    class NodeRemover(cst.CSTTransformer):
        def __init__(self, target_node: cst.CSTNode):
            self.target_node = target_node
            self.removed = False

        def on_visit(self, node: cst.CSTNode) -> bool:
            if node is self.target_node:
                self.removed = True
                return False
            return True

        def on_leave(  # type: ignore[override]
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode | cst.RemovalSentinel | cst.FlattenSentinel[cst.CSTNode]:
            if original_node is self.target_node:
                return cst.RemoveFromParent()
            return updated_node

    remover = NodeRemover(node)
    result = module.visit(remover)
    if not remover.removed:
        raise ValueError(f"Node {node_id} was not removed")
    return result


def find_node_in_module_by_position(
    module: cst.Module,
    start_line: int,
    start_col: int,
    end_line: int,
    end_col: int,
) -> Optional[cst.CSTNode]:
    """
    Find a node in the given module with exact position (for use after previous
    ops have updated the module so tree.node_map may point at stale nodes).
    Returns the statement-level node that appears in Module.body when the
    matched node is inside one (e.g. ImportFrom inside SimpleStatementLine),
    so that leave_Module finds it in original_node.body.
    """
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    result: List[Optional[cst.CSTNode]] = [None]

    class Finder(cst.CSTVisitor):
        def visit(self, node: cst.CSTNode) -> bool:
            pos = positions.get(node)
            if pos is not None and hasattr(pos, "start") and hasattr(pos, "end"):
                if (
                    pos.start.line == start_line
                    and pos.start.column == start_col
                    and pos.end.line == end_line
                    and pos.end.column == end_col
                ):
                    # Prefer statement-level node so replace matches body items
                    if isinstance(node, cst.BaseStatement):
                        result[0] = node
                        return False
                    if result[0] is None:
                        result[0] = node
                    return True
            return True

    module.visit(Finder())
    found = result[0]
    # When no exact position match (e.g. after prior replace in batch), find by
    # start position so batch replace still resolves the correct statement.
    target_start = (start_line, start_col)
    if found is None:
        for stmt in module.body:
            pos = positions.get(stmt)
            if pos is None or not hasattr(pos, "start"):
                continue
            stmt_start = (pos.start.line, pos.start.column)
            if stmt_start == target_start:
                return stmt

        # Fallback: search whole tree for node with matching start (e.g. method
        # inside class body, after prior replace shifted end position).
        class FindByStart(cst.CSTVisitor):
            def visit(self, node: cst.CSTNode) -> bool:
                if isinstance(node, (cst.FunctionDef, cst.ClassDef)):
                    p = positions.get(node)
                    if (
                        p
                        and hasattr(p, "start")
                        and (
                            p.start.line,
                            p.start.column,
                        )
                        == target_start
                    ):
                        result[0] = node
                        return False
                return True

        result[0] = None
        module.visit(FindByStart())
        if result[0] is not None:
            return result[0]
        return None
    # When the matched node is inside a SimpleStatementLine (e.g. ImportFrom),
    # return the statement-level node so leave_Module finds it in module.body.
    if any(stmt is found for stmt in module.body):
        return found
    # Find the statement in module.body whose span contains this position.
    target_start = (start_line, start_col)
    target_end = (end_line, end_col)
    for stmt in module.body:
        pos = positions.get(stmt)
        if pos is None or not hasattr(pos, "start") or not hasattr(pos, "end"):
            continue
        stmt_start = (pos.start.line, pos.start.column)
        stmt_end = (pos.end.line, pos.end.column)
        if stmt_start <= target_start and target_end <= stmt_end:
            return stmt
    # Fallback: match by start position only (batch replace can leave end_col
    # differing between original metadata and current module).
    for stmt in module.body:
        pos = positions.get(stmt)
        if pos is None or not hasattr(pos, "start"):
            continue
        stmt_start = (pos.start.line, pos.start.column)
        if stmt_start == target_start:
            return stmt
    return found


def find_leaf_node_in_module_by_position(
    module: cst.Module,
    start_line: int,
    start_col: int,
    end_line: int,
    end_col: int,
) -> Optional[cst.CSTNode]:
    """
    Find the CST node whose span exactly matches (start_line, start_col,
    end_line, end_col). No promotion to the enclosing Module/IndentedBlock
    statement (unlike find_node_in_module_by_position).
    """
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    result: List[Optional[cst.CSTNode]] = [None]

    class ExactFinder(cst.CSTVisitor):
        def visit(self, node: cst.CSTNode) -> bool:
            pos = positions.get(node)
            if pos is not None and hasattr(pos, "start") and hasattr(pos, "end"):
                if (
                    pos.start.line == start_line
                    and pos.start.column == start_col
                    and pos.end.line == end_line
                    and pos.end.column == end_col
                ):
                    result[0] = node
                    return False
            return True

    module.visit(ExactFinder())
    return result[0]


def find_parent_in_module_by_position(
    module: cst.Module, start_line: int, start_col: int
) -> Optional[Union[cst.Module, cst.FunctionDef, cst.ClassDef]]:
    """
    Find a container node (Module, FunctionDef, or ClassDef) in module
    with exact start position, or whose span contains the position (fallback
    after prior inserts may shift positions). Used for insert so we get the
    node from the current module after prior ops (node_map may be stale).
    """
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    result: List[Optional[cst.CSTNode]] = [None]
    # Fallback: candidates that contain (start_line, start_col), pick smallest
    candidates: List[Tuple[cst.CSTNode, int]] = []

    class ParentFinder(cst.CSTVisitor):
        def visit(self, node: cst.CSTNode) -> bool:
            if not isinstance(node, (cst.Module, cst.FunctionDef, cst.ClassDef)):
                return True
            pos = positions.get(node)
            if pos is None or not hasattr(pos, "start") or not hasattr(pos, "end"):
                return True
            sl, sc = pos.start.line, pos.start.column
            el, ec = pos.end.line, pos.end.column
            if sl == start_line and sc == start_col:
                result[0] = node
                return False
            # Span contains position (e.g. after prior insert line numbers shift)
            if (sl, sc) <= (start_line, start_col) <= (el, ec):
                span_size = (el - sl) * 10000 + (ec - sc)
                candidates.append((node, span_size))
            return True

    module.visit(ParentFinder())
    if result[0] is not None:
        return cast(
            Optional[Union[cst.Module, cst.FunctionDef, cst.ClassDef]],
            result[0],
        )
    if candidates:
        candidates.sort(key=lambda x: x[1])
        return cast(
            Optional[Union[cst.Module, cst.FunctionDef, cst.ClassDef]],
            candidates[0][0],
        )
    return None
