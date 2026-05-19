"""
Find and delete nodes in CST module by position (for tree modifier operations).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Union, cast

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from .models import CSTTree, TreeNodeMetadata
from .tree_modifier_ops_parse import FINE_GRAINED_REPLACE_NODE_TYPES

_COMPOUND_STMT_TYPE_NAMES = frozenset(
    {
        "ClassDef",
        "FunctionDef",
        "AsyncFunctionDef",
        "If",
        "For",
        "While",
        "Try",
        "With",
    }
)

_COMPOUND_STMT_TYPES: Tuple[type, ...] = (
    cst.ClassDef,
    cst.FunctionDef,
    cst.If,
    cst.For,
    cst.While,
    cst.Try,
    cst.With,
)
if hasattr(cst, "AsyncFunctionDef"):
    _COMPOUND_STMT_TYPES = _COMPOUND_STMT_TYPES + (cast(type, cst.AsyncFunctionDef),)


def _node_is_in_module_tree(module: cst.Module, node: cst.CSTNode) -> bool:
    """True if ``node`` is the same object as some node visited under ``module``."""
    found = [False]

    class _IdentityVisitor(cst.CSTVisitor):
        def on_visit(self, n: cst.CSTNode) -> bool:
            if n is node:
                found[0] = True
                return False
            return True

    module.visit(_IdentityVisitor())
    return found[0]


def resolve_replace_target_to_current_module(
    module: cst.Module,
    node: cst.CSTNode,
    metadata: Optional[TreeNodeMetadata],
) -> cst.CSTNode:
    """
    Ensure ``node`` references the CST object graph of ``module``.

    ``tree.node_map`` can point at nodes from a previous ``Module`` after
    ``module.visit`` / codegen replaced the tree; ``NodeReplacer`` then compares
    ``stmt is target`` against ``module.body`` and never matches. For compound
    statements, re-resolve by type + name (and start position when needed).
    """
    if _node_is_in_module_tree(module, node):
        return node
    if metadata is None or metadata.type not in _COMPOUND_STMT_TYPE_NAMES:
        return node

    m = metadata
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    candidates: List[cst.CSTNode] = []

    class _Collect(cst.CSTVisitor):
        def on_visit(self, n: cst.CSTNode) -> bool:
            if not isinstance(n, _COMPOUND_STMT_TYPES):
                return True
            if type(n).__name__ != m.type:
                return True
            node_name = getattr(getattr(n, "name", None), "value", None)
            if m.name is not None:
                if node_name != m.name:
                    return True
            else:
                p = positions.get(n)
                if (
                    p is None
                    or not hasattr(p, "start")
                    or (
                        p.start.line,
                        p.start.column,
                    )
                    != (m.start_line, m.start_col)
                ):
                    return True
            candidates.append(n)
            return True

    module.visit(_Collect())
    if not candidates:
        return node
    if len(candidates) == 1:
        return candidates[0]
    narrowed: List[cst.CSTNode] = []
    for c in candidates:
        p = positions.get(c)
        if (
            p is not None
            and hasattr(p, "start")
            and p.start.line == m.start_line
            and p.start.column == m.start_col
        ):
            narrowed.append(c)
    if len(narrowed) == 1:
        return narrowed[0]
    if len(narrowed) > 1:
        raise ValueError(
            "Ambiguous replace target: multiple compound statements match "
            f"type={m.type!r}, name={m.name!r}, "
            f"start_line={m.start_line}, start_col={m.start_col}"
        )
    # Start column may differ from metadata (e.g. after reformat); same line + name.
    line_only: List[cst.CSTNode] = []
    for c in candidates:
        p = positions.get(c)
        if p is not None and hasattr(p, "start") and p.start.line == m.start_line:
            line_only.append(c)
    if len(line_only) == 1:
        return line_only[0]
    if len(line_only) > 1:
        raise ValueError(
            "Ambiguous replace target: multiple compound statements on the same line "
            f"match type={m.type!r}, name={m.name!r}, "
            f"start_line={m.start_line}"
        )
    return node


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
                preferred_type=metadata.type,
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

    node = resolve_replace_target_to_current_module(module, node, metadata)

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
    so that leave_Module finds it in module.body.
    """
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    result: List[Optional[cst.CSTNode]] = [None]

    class Finder(cst.CSTVisitor):
        def on_visit(self, node: cst.CSTNode) -> bool:
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
            def on_visit(self, node: cst.CSTNode) -> bool:
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
    # KEY FIX: если found — compound statement (FunctionDef, ClassDef и т.д.),
    # возвращаем его напрямую. Не нужно искать 'родителя' в module.body —
    # это именно тот узел который нужно заменить. NodeReplacer найдёт его
    # через leave_IndentedBlock, а не через leave_Module.
    if isinstance(found, cst.BaseCompoundStatement):
        return found
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
    *,
    preferred_type: Optional[str] = None,
) -> Optional[cst.CSTNode]:
    """
    Find the CST node whose span exactly matches (start_line, start_col,
    end_line, end_col). No promotion to the enclosing Module/IndentedBlock
    statement (unlike find_node_in_module_by_position).

    Multiple CST nodes can share the same span (e.g. ``Parameters`` and inner
    ``Param``). Pass ``preferred_type`` (``Name`` / ``Param`` / ``Annotation``)
    so the node matches :data:`FINE_GRAINED_REPLACE_NODE_TYPES` and metadata.
    """
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    matches: List[Tuple[cst.CSTNode, int]] = []

    class ExactCollector(cst.CSTVisitor):
        def __init__(self) -> None:
            self._depth = 0

        def on_visit(self, node: cst.CSTNode) -> bool:
            self._depth += 1
            kind = type(node).__name__
            include = isinstance(node, cst.BaseExpression) or kind in (
                "Param",
                "Annotation",
            )
            if include:
                pos = positions.get(node)
                if pos is not None and hasattr(pos, "start") and hasattr(pos, "end"):
                    if (
                        pos.start.line == start_line
                        and pos.start.column == start_col
                        and pos.end.line == end_line
                        and pos.end.column == end_col
                    ):
                        matches.append((node, self._depth))
            return True

        def on_leave(self, original_node: cst.CSTNode) -> None:
            self._depth -= 1

    module.visit(ExactCollector())
    if not matches:
        return None
    candidates = matches
    if preferred_type is not None:
        typed = [(n, d) for n, d in matches if type(n).__name__ == preferred_type]
        if typed:
            candidates = typed
    if len(candidates) == 1:
        return candidates[0][0]
    # Same span for several nodes (rare): prefer deepest in the tree.
    max_d = max(d for _n, d in candidates)
    deepest = [n for n, d in candidates if d == max_d]
    return deepest[0]


_COMPOUND_INSERT_PARENT_TYPES = frozenset({"Module", "ClassDef", "FunctionDef"})


def resolve_insert_parent_node(
    module: cst.Module,
    tree: CSTTree,
    parent_node_id: str,
) -> Optional[cst.CSTNode]:
    """
    Resolve an insert/move parent to the current ``module`` graph.

    For ClassDef, FunctionDef, and Module parents, uses metadata + identity
    re-alignment instead of span containment (which would pick an inner method body).
    """
    meta = tree.metadata_map.get(parent_node_id)
    if meta and meta.type in _COMPOUND_INSERT_PARENT_TYPES:
        node = tree.node_map.get(parent_node_id)
        if node is not None:
            resolved = resolve_replace_target_to_current_module(module, node, meta)
            if isinstance(resolved, cst.Module):
                return module
            return resolved
    if meta and hasattr(meta, "start_line") and hasattr(meta, "start_col"):
        found = find_parent_in_module_by_position(
            module, meta.start_line, meta.start_col
        )
        if found is not None:
            return found
    parent_node = tree.node_map.get(parent_node_id)
    if isinstance(parent_node, cst.Module):
        return module
    return parent_node


def find_parent_in_module_by_position(
    module: cst.Module, start_line: int, start_col: int
) -> Optional[cst.CSTNode]:
    """
    Find a container node in module with exact start position, or whose span
    contains the position (fallback after prior inserts may shift positions).
    Used for insert so we get the node from the current module after prior ops
    (node_map may be stale).
    Supports: Module, IndentedBlock, or any node whose body is IndentedBlock
    (FunctionDef, ClassDef, If, For, While, With, Try, ExceptHandler, Else, Finally, MatchCase).
    """
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    result: List[Optional[cst.CSTNode]] = [None]
    # Fallback: candidates that contain (start_line, start_col), pick smallest
    candidates: List[Tuple[cst.CSTNode, int]] = []

    class ParentFinder(cst.CSTVisitor):
        def on_visit(self, node: cst.CSTNode) -> bool:
            is_container = isinstance(node, (cst.Module, cst.IndentedBlock)) or (
                hasattr(node, "body")
                and isinstance(getattr(node, "body", None), cst.IndentedBlock)
            )
            if not is_container:
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
        return result[0]
    if candidates:
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]
    return None
