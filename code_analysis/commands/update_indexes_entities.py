"""
Entity extraction and DB indexing for update_indexes (classes, methods, functions, imports).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging

logger = logging.getLogger(__name__)


def _extract_docstring(node: ast.AST) -> str | None:
    """Extract docstring from an AST node."""
    if isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)
    ):
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            return node.body[0].value.value
    return None


def _extract_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract argument names from function node, excluding 'self'."""
    args: list[str] = []
    for arg in node.args.args:
        if arg.arg != "self":
            args.append(arg.arg)
    return args


def _flatten_assign_target_names(target: ast.AST) -> list[str]:
    """Collect simple names from assignment targets (``x``, ``a, b``, ``self.attr``)."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        out: list[str] = []
        for elt in target.elts:
            out.extend(_flatten_assign_target_names(elt))
        return out
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        if target.value.id == "self":
            return [target.attr]
    return []


def _names_from_assign_like(node: ast.AST) -> list[str]:
    """Return names from assign like."""
    if isinstance(node, ast.AnnAssign):
        return _flatten_assign_target_names(node.target)
    if isinstance(node, ast.Assign):
        names: list[str] = []
        for t in node.targets:
            names.extend(_flatten_assign_target_names(t))
        return names
    if isinstance(node, ast.AugAssign):
        return _flatten_assign_target_names(node.target)
    return []


def _fts_symbol_overlay(*parts: str) -> str:
    """Space-separated unique tokens for FTS ``docstring`` augmentation."""
    seen: set[str] = set()
    ordered: list[str] = []
    for p in parts:
        s = (p or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        ordered.append(s)
    return " ".join(ordered)


def _merge_docstring_and_symbols(
    docstring: str | None, *symbol_parts: str
) -> str | None:
    """Append symbol tokens to docstring for FTS (identifiers, class names, args)."""
    tail = _fts_symbol_overlay(*symbol_parts)
    if docstring and tail:
        return f"{docstring}\n{tail}"
    if docstring:
        return docstring
    return tail or None
