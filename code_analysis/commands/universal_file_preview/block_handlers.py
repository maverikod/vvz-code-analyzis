"""
BlockHandler (C-008) — five rendering rules, one per NodeKind (C-004).

Chosen by the block's own NodeKind, not the parent's kind.
A BlockHandler never includes the block's own children's content.
Set is closed under this plan: five rules only.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from .models import Node, NodeKind


def render_block(node: Node, value_preview_len: int) -> dict[str, Any]:
    """
    Render a Node using the BlockHandler rule for its own NodeKind (C-008).

    Args:
        node: The block node to render.
        value_preview_len: Max length for any inline scalar value or name
                         (from PreviewBudget C-013).

    Returns:
        Compact summary dict. Keys depend on NodeKind:
          scalar    -> {value: str (truncated)}
          lines     -> {line_count: int, first_line: str (truncated)}
          sequence  -> {element_count: int, element_kinds: list[str]}
          mapping   -> {key_count: int, key_names: list[str] (each truncated)}
          tree_node -> {type: str, name: str|None, attributes: dict,
                        child_count: int}
    """
    vpl = value_preview_len
    kind = node.node_kind
    if kind is NodeKind.SCALAR:
        return _render_scalar(node, vpl)
    if kind is NodeKind.LINES:
        return _render_lines(node, vpl)
    if kind is NodeKind.SEQUENCE:
        return _render_sequence(node, vpl)
    if kind is NodeKind.MAPPING:
        return _render_mapping(node, vpl)
    if kind is NodeKind.TREE_NODE:
        return _render_tree_node(node, vpl)
    raise ValueError(f"Unhandled NodeKind: {kind!r}")
def _render_scalar(node: Node, vpl: int) -> dict[str, Any]:
    """Rule 1: truncated value. No children content."""
    value = node.attributes.get("value") or node.name or node.type_label or ""
    return {"value": value[:vpl]}


def _render_lines(node: Node, vpl: int) -> dict[str, Any]:
    """Rule 2: total line count and first line truncated."""
    children = node.children
    first = children[0].attributes.get("value", "") if children else ""
    return {"line_count": len(children), "first_line": first[:vpl]}


def _render_sequence(node: Node, vpl: int) -> dict[str, Any]:  # noqa: ARG001
    """Rule 3: element count and coarse element-kind summary."""
    children = node.children
    kinds = sorted({c.node_kind.value for c in children})
    return {"element_count": len(children), "element_kinds": kinds}


def _render_mapping(node: Node, vpl: int) -> dict[str, Any]:
    """Rule 4: key count and key name list, each truncated. No values."""
    children = node.children
    keys = [c.name[:vpl] if c.name else "" for c in children]
    return {"key_count": len(children), "key_names": keys}


def _render_tree_node(node: Node, vpl: int) -> dict[str, Any]:
    """Rule 5: type, optional name, attributes, child count."""
    return {
        "type": (node.type_label or "")[:vpl],
        "name": node.name[:vpl] if node.name else None,
        "attributes": node.attributes,
        "child_count": len(node.children),
    }
