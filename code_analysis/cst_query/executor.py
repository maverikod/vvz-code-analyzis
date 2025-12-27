"""
CSTQuery executor for Python source (LibCST).

The executor traverses a LibCST tree, builds a lightweight parent-linked index,
and evaluates a parsed selector against nodes.

This is intentionally focused on pragmatics:
- stable-enough node_id based on span + kind + qualname
- targeting statement-like nodes for refactoring workflows

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider

from .ast import Combinator, Predicate, PredicateOp, PseudoKind, Query, SelectorStep
from .parser import parse_selector

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Match:
    """A single selector match."""

    node_id: str
    kind: str
    node_type: str
    name: Optional[str]
    qualname: Optional[str]
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    code: Optional[str] = None


@dataclass(frozen=True)
class _NodeInfo:
    node: cst.CSTNode
    parent: Optional[cst.CSTNode]
    depth: int
    kind: str
    name: Optional[str]
    qualname: Optional[str]
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    @property
    def node_type(self) -> str:
        return self.node.__class__.__name__

    @property
    def span_key(self) -> tuple[int, int, int, int]:
        return (self.start_line, self.start_col, self.end_line, self.end_col)

    def to_id(self) -> str:
        q = self.qualname or ""
        return (
            f"{self.kind}:{q}:{self.node_type}:"
            f"{self.start_line}:{self.start_col}-{self.end_line}:{self.end_col}"
        )


def query_source(
    source: str, selector: str, *, include_code: bool = False
) -> list[Match]:
    """
    Query python source using CSTQuery selectors.

    Args:
        source: python module source
        selector: selector string
        include_code: include `code_for_node` snippet for each match (can be large)
    """
    q = parse_selector(selector)
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    parents = wrapper.resolve(ParentNodeProvider)
    positions = wrapper.resolve(PositionProvider)

    nodes = _build_index(module, parents=parents, positions=positions)
    matched = _eval_query(nodes, q)

    out: list[Match] = []
    for info in matched:
        code = module.code_for_node(info.node) if include_code else None
        out.append(
            Match(
                node_id=info.to_id(),
                kind=info.kind,
                node_type=info.node_type,
                name=info.name,
                qualname=info.qualname,
                start_line=info.start_line,
                start_col=info.start_col,
                end_line=info.end_line,
                end_col=info.end_col,
                code=code,
            )
        )
    return out


def _build_index(
    module: cst.Module,
    *,
    parents: dict[cst.CSTNode, cst.CSTNode],
    positions: dict[cst.CSTNode, Any],
) -> list[_NodeInfo]:
    """
    Build a traversal-ordered node list with parent pointers and basic attributes.

    We include all nodes because selection can target any node_type, but replacement
    workflows mainly care about stmt/smallstmt nodes.
    """
    infos: list[_NodeInfo] = []

    class_stack: list[str] = []
    func_stack: list[str] = []

    def visit(node: cst.CSTNode, depth: int) -> None:
        parent = parents.get(node)
        pos = positions.get(node)
        if pos is None:
            # Some nodes may not carry positions; skip them.
            return
        try:
            # Safely access position attributes
            start_line = pos.start.line if hasattr(pos, 'start') and hasattr(pos.start, 'line') else 1
            start_col = pos.start.column if hasattr(pos, 'start') and hasattr(pos.start, 'column') else 0
            end_line = pos.end.line if hasattr(pos, 'end') and hasattr(pos.end, 'line') else 1
            end_col = pos.end.column if hasattr(pos, 'end') and hasattr(pos.end, 'column') else 0
            
            name = _node_name(node)
            kind = _node_kind(node, class_stack=class_stack)
            qual = _node_qualname(node, class_stack=class_stack, func_stack=func_stack)
            infos.append(
                _NodeInfo(
                    node=node,
                    parent=parent,
                    depth=depth,
                    kind=kind,
                    name=name,
                    qualname=qual,
                    start_line=start_line,
                    start_col=start_col,
                    end_line=end_line,
                    end_col=end_col,
                )
            )
        except (AttributeError, TypeError) as e:
            # Skip nodes with invalid positions
            logger.debug(f"Skipping node with invalid position: {e}")
            return

        entered_class = False
        entered_func = False
        if isinstance(node, cst.ClassDef):
            class_stack.append(node.name.value)
            entered_class = True
        elif isinstance(node, cst.FunctionDef):
            func_stack.append(node.name.value)
            entered_func = True

        for child in node.children:
            visit(child, depth + 1)

        if entered_func:
            func_stack.pop()
        if entered_class:
            class_stack.pop()

    visit(module, 0)
    return infos


def _node_name(node: cst.CSTNode) -> Optional[str]:
    if isinstance(node, (cst.FunctionDef, cst.ClassDef)):
        return node.name.value
    if isinstance(node, cst.Name):
        return node.value
    return None


def _node_kind(node: cst.CSTNode, *, class_stack: list[str]) -> str:
    if isinstance(node, cst.ClassDef):
        return "class"
    if isinstance(node, cst.FunctionDef):
        return "method" if class_stack else "function"
    if isinstance(node, (cst.Import, cst.ImportFrom)):
        return "import"
    if isinstance(node, cst.BaseSmallStatement):
        return "smallstmt"
    if isinstance(node, cst.BaseStatement):
        return "stmt"
    return "node"


def _node_qualname(
    node: cst.CSTNode, *, class_stack: list[str], func_stack: list[str]
) -> Optional[str]:
    if isinstance(node, cst.ClassDef):
        return (
            ".".join(class_stack + [node.name.value])
            if class_stack
            else node.name.value
        )
    if isinstance(node, cst.FunctionDef):
        if class_stack:
            return ".".join(class_stack + [node.name.value])
        # For nested functions, include outer functions if present.
        parts = list(func_stack[:-1]) + [node.name.value]
        return ".".join(parts) if parts else node.name.value
    return ".".join(class_stack + func_stack) if (class_stack or func_stack) else None


def _eval_query(nodes: list[_NodeInfo], q: Query) -> list[_NodeInfo]:
    parent_map: dict[cst.CSTNode, Optional[cst.CSTNode]] = {
        n.node: n.parent for n in nodes
    }
    current = _apply_step(nodes, q.first)
    for comb, step in q.rest:
        nxt_candidates = _apply_step(nodes, step)
        current = _apply_combinator(
            current, nxt_candidates, comb, parent_map=parent_map
        )
    return current


def _apply_combinator(
    prev: list[_NodeInfo],
    nxt: list[_NodeInfo],
    comb: Combinator,
    *,
    parent_map: dict[cst.CSTNode, Optional[cst.CSTNode]],
) -> list[_NodeInfo]:
    if not prev or not nxt:
        return []
    prev_nodes = {p.node for p in prev}

    if comb == Combinator.CHILD:
        return [n for n in nxt if n.parent in prev_nodes]

    # Descendant: any ancestor match.
    prev_set = prev_nodes
    out: list[_NodeInfo] = []
    for n in nxt:
        p = n.parent
        while p is not None:
            if p in prev_set:
                out.append(n)
                break
            p = parent_map.get(p)
    return out


def _apply_step(nodes: list[_NodeInfo], step: SelectorStep) -> list[_NodeInfo]:
    matched = [n for n in nodes if _matches_step(n, step)]
    for pseudo in step.pseudos:
        if pseudo.kind == PseudoKind.FIRST:
            matched = matched[:1]
        elif pseudo.kind == PseudoKind.LAST:
            matched = matched[-1:] if matched else []
        elif pseudo.kind == PseudoKind.NTH:
            idx = pseudo.index or 0
            matched = [matched[idx]] if 0 <= idx < len(matched) else []
    return matched


def _matches_step(node: _NodeInfo, step: SelectorStep) -> bool:
    if not _matches_node_type(node, step.node_type):
        return False
    for pred in step.predicates:
        if not _matches_predicate(node, pred):
            return False
    return True


def _matches_node_type(node: _NodeInfo, node_type: str) -> bool:
    if not node_type or node_type == "*":
        return True
    t = node_type.strip()
    alias = t.lower()
    if alias in {
        "module",
        "class",
        "function",
        "method",
        "stmt",
        "smallstmt",
        "import",
        "node",
    }:
        return node.kind == alias
    # LibCST class name match
    return node.node_type.lower() == t.lower()


def _matches_predicate(node: _NodeInfo, pred: Predicate) -> bool:
    val = _get_attr(node, pred.attr)
    if val is None:
        return False
    return _compare(str(val), pred.op, pred.value)


def _get_attr(node: _NodeInfo, attr: str) -> Optional[str]:
    a = attr.lower()
    if a == "type":
        return node.node_type
    if a == "kind":
        return node.kind
    if a == "name":
        return node.name
    if a == "qualname":
        return node.qualname
    if a == "start_line":
        return str(node.start_line)
    if a == "end_line":
        return str(node.end_line)
    return None


def _compare(left: str, op: PredicateOp, right: str) -> bool:
    if op == PredicateOp.EQ:
        return left == right
    if op == PredicateOp.NE:
        return left != right
    if op == PredicateOp.CONTAINS:
        return right in left
    if op == PredicateOp.PREFIX:
        return left.startswith(right)
    if op == PredicateOp.SUFFIX:
        return left.endswith(right)
    return False
