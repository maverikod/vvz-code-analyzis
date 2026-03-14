"""
Helpers for deriving semantic attributes of LibCST nodes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Optional

import libcst as cst


def get_node_name(node: cst.CSTNode) -> Optional[str]:
    """Return the semantic name of a node when available."""
    if isinstance(node, (cst.FunctionDef, cst.ClassDef)):
        return node.name.value
    if isinstance(node, cst.Name):
        return node.value
    return None


def get_node_kind(node: cst.CSTNode, class_stack: list[str]) -> str:
    """Return the semantic kind used by CST commands and selectors."""
    if isinstance(node, cst.Module):
        return "module"
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


def get_node_qualname(
    node: cst.CSTNode,
    class_stack: list[str],
    func_stack: list[str],
) -> Optional[str]:
    """Return the qualified name for class/function-like nodes."""
    if isinstance(node, cst.ClassDef):
        return (
            ".".join(class_stack + [node.name.value])
            if class_stack
            else node.name.value
        )
    if isinstance(node, cst.FunctionDef):
        if class_stack:
            return ".".join(class_stack + [node.name.value])
        parts = list(func_stack[:-1]) + [node.name.value]
        return ".".join(parts) if parts else node.name.value
    return ".".join(class_stack + func_stack) if (class_stack or func_stack) else None
