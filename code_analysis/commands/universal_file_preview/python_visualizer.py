"""
Python node renderer for universal_file_preview (C-022).

Converts CSTTree nodes to structured human-readable text for AI consumption.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


import pathlib

from typing import Any


from .budget import PreviewBudget


def _fmt_range(meta: Any) -> str:
    """Format a line range string from node metadata.

    Args:
        meta: NodeMetadata with start_line and end_line attributes.

    Returns:
        String 'L{start}-{end}', 'L{start}', or '' when start_line is None.
    """
    start = meta.start_line
    if start is None:
        return ""
    end = meta.end_line
    if end is not None and end != start:
        return f"L{start}-{end}"
    return f"L{start}"


def _doc_first_line(doc: Any) -> str:
    """First line for inline docstring preview (handles DocstringMeta or string)."""
    if doc is None:
        return ""
    if isinstance(doc, str):
        s = doc.strip()
        return s.splitlines()[0] if s else ""
    summary = getattr(doc, "summary", None) or ""
    summary_stripped = summary.strip()
    if summary_stripped:
        return summary_stripped.splitlines()[0]
    body = getattr(doc, "docstring_body", None) or ""
    body_stripped = body.strip()
    if body_stripped:
        return body_stripped.splitlines()[0]
    return ""


def _doc_block_preview(doc: Any) -> str:
    """Full docstring snippet for module header (handles DocstringMeta or string)."""
    if doc is None:
        return ""
    if isinstance(doc, str):
        return doc.strip()
    summary = (getattr(doc, "summary", None) or "").strip()
    if summary:
        return summary
    body = (getattr(doc, "docstring_body", None) or "").strip()
    if body:
        return body
    return ""


def _headline(meta: Any, tree: Any = None) -> str:
    """One-line header for a CST node metadata row.

    Tries, in order:
    1. ``signature`` attribute (pre-computed for functions/classes).
    2. First line of source code via ``tree.module.code_for_node`` (for
       SimpleStatementLine and other stmt nodes without a name).
    3. Fallback to ``type`` string.

    Args:
        meta: ``TreeNodeMetadata`` object from ``tree.metadata_map``.
        tree: ``CSTTree`` instance; required for source-code extraction.

    Returns:
        Single-line string describing the node.
    """
    sig = getattr(meta, "signature", None)
    if isinstance(sig, str) and sig.strip():
        return sig.strip()
    # Try to extract first line of source code for stmt nodes (e.g. SimpleStatementLine).
    if tree is not None:
        node_id = getattr(meta, "node_id", None) or getattr(meta, "stable_id", None)
        if node_id:
            cst_node = tree.node_map.get(node_id)
            if cst_node is not None:
                try:
                    raw = tree.module.code_for_node(cst_node)
                    first = raw.strip().split("\n")[0].strip()
                    if first:
                        return str(first)
                except Exception:
                    pass
    typ = getattr(meta, "type", None) or ""
    kind = getattr(meta, "kind", None) or ""
    name = getattr(meta, "name", None)
    if kind == "function" or typ in ("FunctionDef", "AsyncFunctionDef"):
        return _function_headline(meta, tree)
    if kind == "class" or typ == "ClassDef":
        return f"class {name or '?'}:"
    if typ:
        return typ
    if name:
        return str(name)
    return ""


def _meta_first_line(meta: Any, tree: Any = None) -> str:
    """First non-empty source line from metadata ``code`` or CST source."""
    code = getattr(meta, "code", None)
    if isinstance(code, str) and code.strip():
        return code.strip().splitlines()[0].strip()
    if tree is not None:
        node_id = getattr(meta, "node_id", None)
        if node_id:
            cst_node = tree.node_map.get(node_id)
            if cst_node is not None:
                try:
                    raw = tree.module.code_for_node(cst_node)
                    if raw.strip():
                        return raw.strip().splitlines()[0].strip()
                except Exception:
                    pass
    return ""


def _function_def_line(meta: Any, tree: Any = None) -> str:
    """``def`` / ``async def`` line from metadata code or CST source."""
    snippets: list[str] = []
    code = getattr(meta, "code", None)
    if isinstance(code, str) and code.strip():
        snippets.append(code)
    if tree is not None:
        node_id = getattr(meta, "node_id", None)
        if node_id:
            cst_node = tree.node_map.get(node_id)
            if cst_node is not None:
                try:
                    raw = tree.module.code_for_node(cst_node)
                    if raw.strip():
                        snippets.append(raw)
                except Exception:
                    pass
    for snippet in snippets:
        for line in snippet.splitlines():
            stripped = line.strip()
            if stripped.startswith("async def ") or stripped.startswith("def "):
                return stripped
    return ""


def _function_headline(meta: Any, tree: Any = None) -> str:
    """Header line for defs (used under classes and collapsed bodies)."""
    sig = getattr(meta, "signature", None)
    if isinstance(sig, str) and sig.strip():
        return sig.strip()
    def_line = _function_def_line(meta, tree)
    if def_line:
        return def_line
    name = getattr(meta, "name", None)
    typ = getattr(meta, "type", None) or ""
    if typ == "AsyncFunctionDef":
        return f"async def {name or '?'}:"
    return f"def {name or '?'}:"


def _decorator_headline(meta: Any, tree: Any = None) -> str:
    """One-line ``@decorator`` preview for a Decorator metadata row."""
    first = _meta_first_line(meta, tree)
    if first:
        return first if first.startswith("@") else f"@{first}"
    name = getattr(meta, "name", None)
    if name:
        text = str(name)
        return text if text.startswith("@") else f"@{text}"
    return "@..."


def render_module(tree: Any, budget: PreviewBudget) -> str:
    """Render top-level module view: classes, functions, and loose statements.

    Args:
        tree: CSTTree loaded for the file.
        budget: PreviewBudget controlling how many characters to render.

    Returns:
        Multi-line structured text of the module.
    """
    if not hasattr(tree, "metadata_map") or not tree.metadata_map:
        return ""
    root_id = getattr(tree, "root_node_id", None)
    top_level = _direct_children(tree, root_id)
    lines: list[str] = []
    rendered_blocks = 0
    for meta in top_level:
        kind = meta.kind or ""
        typ = getattr(meta, "type", None) or ""
        sid = meta.stable_id
        rng = _fmt_range(meta)
        if kind in ("function", "method") or typ in ("FunctionDef", "AsyncFunctionDef"):
            head = _function_headline(meta, tree)
            lines.append(f"[{sid}] {rng}  {head}")
            doc = _doc_first_line(meta.docstring)
            if doc:
                lines.append("    " + doc)
        elif kind == "class" or typ == "ClassDef":
            lines.append(f"[{sid}] {rng}  class {meta.name or '?'}:")
            doc = _doc_first_line(meta.docstring)
            if doc:
                lines.append("    " + doc)
            node_id = next(
                (nid for nid, m in tree.metadata_map.items() if m.stable_id == sid),
                None,
            )
            if node_id:
                methods = sorted(
                    (
                        m
                        for m in tree.metadata_map.values()
                        if m.parent_id == node_id and m.kind in ("function", "method")
                    ),
                    key=lambda m: m.start_line or 0,
                )
                for meth in methods:
                    meth_sig = _function_headline(meth, tree)
                    lines.append(
                        f"    [{meth.stable_id}] {_fmt_range(meth)}  {meth_sig}"
                    )
                    doc_m = _doc_first_line(meth.docstring)
                    if doc_m:
                        lines.append("        " + doc_m)
        else:
            head = _headline(meta, tree)
            if head:
                lines.append(f"[{sid}] {rng}  {head}")
        rendered_blocks += 1
        if rendered_blocks >= budget.preview_lines:
            lines.append("... (truncated)")
            break
    return "\n".join(lines)


_COMPOUND_STMT_TYPES = frozenset(
    {
        "If",
        "For",
        "While",
        "Try",
        "With",
        "Match",
        "ClassDef",
        "FunctionDef",
        "AsyncFunctionDef",
    }
)


def _is_compound_stmt(meta: Any) -> bool:
    """Return whether metadata denotes a compound statement for collapsed body preview.

    Args:
        meta: NodeMetadata with a ``type`` field (e.g. ``If``, ``FunctionDef``).

    Returns:
        True if ``type`` is in the compound-statement set used for ``...`` collapse.
    """
    typ = getattr(meta, "type", None) or ""
    return typ in _COMPOUND_STMT_TYPES


def _direct_children(tree: Any, node_id: str | None) -> list[Any]:
    """Collect direct statement-level child metadata rows for a CST node.

    For ``FunctionDef``, ``AsyncFunctionDef``, ``ClassDef``, and compound
    statements (``If``, ``For``, ``While``, ``Try``, ``With``, ``Match``)
    the actual body lives one level deeper inside an ``IndentedBlock`` child.
    This function transparently descends into that block and returns its
    children filtered to ``kind == 'stmt'``, skipping CST noise nodes such
    as ``TrailingWhitespace``.

    For any other node type the direct children are returned as before,
    also filtered to ``kind == 'stmt'``.

    Args:
        tree: CSTTree with ``metadata_map`` and ``parent_id`` links.
        node_id: Internal node id whose children are requested, or None.

    Returns:
        Statement-level child metadata objects sorted by ``start_line``
        (missing treated as 0).
    """
    if node_id is None:
        return []
    # Nodes whose body is wrapped in an IndentedBlock one level down.
    _BLOCK_WRAPPER_TYPES = frozenset(
        {
            "FunctionDef",
            "AsyncFunctionDef",
            "ClassDef",
            "If",
            "For",
            "While",
            "Try",
            "With",
            "Match",
        }
    )
    direct = [m for m in tree.metadata_map.values() if m.parent_id == node_id]
    parent_meta = tree.metadata_map.get(node_id)
    parent_type = getattr(parent_meta, "type", None) or ""
    if parent_type in _BLOCK_WRAPPER_TYPES:
        # Find the IndentedBlock child and use its children instead.
        indented = next(
            (m for m in direct if getattr(m, "type", None) == "IndentedBlock"),
            None,
        )
        if indented is not None:
            direct = [
                m
                for m in tree.metadata_map.values()
                if m.parent_id == indented.stable_id
                and getattr(m, "kind", None) == "stmt"
            ]
            return sorted(direct, key=lambda m: m.start_line or 0)
    # Fallback: return direct children filtered to stmt kind.
    return sorted(
        (m for m in direct if getattr(m, "kind", None) == "stmt"),
        key=lambda m: m.start_line or 0,
    )


def _append_collapsed_body_lines(
    lines: list[str], children: list[Any], tree: Any = None
) -> None:
    """Append first-level body lines; compound statements get a trailing ``...``.

    Args:
        lines: Mutable list of output lines to extend in place.
        children: Direct child metadata rows (sorted) to render.
        tree: ``CSTTree`` instance passed to ``_headline`` for source extraction.

    Returns:
        None.
    """
    for child in children:
        sid = child.stable_id
        rng = _fmt_range(child)
        head = _headline(child, tree)
        if _is_compound_stmt(child):
            lines.append(f"  [{sid}] {rng}  {head}  ...")
        else:
            lines.append(f"  [{sid}] {rng}  {head}")


def render_node(tree: Any, stable_id: str) -> str:
    """Render a single CST node identified by its stable_id (C-022).

    Args:
        tree: CSTTree loaded for the file.
        stable_id: Stable UUID of the target node from cst_load_file (C-009).

    Returns:
        Structured text for the node, or empty string if stable_id not found.
    """
    meta = next(
        (m for m in tree.metadata_map.values() if m.stable_id == stable_id), None
    )
    if meta is None:
        return ""
    node_id = next(
        (nid for nid, m in tree.metadata_map.items() if m.stable_id == stable_id),
        None,
    )

    kind = meta.kind or ""
    typ = getattr(meta, "type", None) or ""

    if typ == "Parameters":
        params = sorted(
            (
                m
                for m in tree.metadata_map.values()
                if m.parent_id == node_id and getattr(m, "type", None) == "Param"
            ),
            key=lambda m: m.start_line or 0,
        )
        param_lines: list[str] = []
        for param in params:
            preview = _meta_first_line(param, tree) or (param.name or "")
            param_lines.append(f"[{param.stable_id}] {_fmt_range(param)}  {preview}")
        return "\n".join(param_lines)

    if kind in ("function", "method") or typ in ("FunctionDef", "AsyncFunctionDef"):
        lines: list[str] = []
        decorators = sorted(
            (
                m
                for m in tree.metadata_map.values()
                if m.parent_id == node_id and getattr(m, "type", None) == "Decorator"
            ),
            key=lambda m: m.start_line or 0,
        )
        for dec in decorators:
            lines.append(
                f"[{dec.stable_id}] {_fmt_range(dec)}  {_decorator_headline(dec, tree)}"
            )
        lines.append(
            f"[{stable_id}] {_fmt_range(meta)}  {_function_headline(meta, tree)}"
        )
        doc = _doc_first_line(meta.docstring)
        if doc:
            lines.append("    " + doc)
        _append_collapsed_body_lines(lines, _direct_children(tree, node_id), tree)
        return "\n".join(lines)

    if kind == "class" or typ == "ClassDef":
        lines_cls: list[str] = [
            f"[{stable_id}] {_fmt_range(meta)}  class {meta.name or '?'}:"
        ]
        doc = _doc_first_line(meta.docstring)
        if doc:
            lines_cls.append("    " + doc)
        if node_id:
            methods = sorted(
                (
                    m
                    for m in tree.metadata_map.values()
                    if m.parent_id == node_id and m.kind in ("function", "method")
                ),
                key=lambda m: m.start_line or 0,
            )
            for meth in methods:
                sig = _function_headline(meth, tree)
                lines_cls.append(f"    [{meth.stable_id}] {_fmt_range(meth)}  {sig}")
                doc_m = _doc_first_line(meth.docstring)
                if doc_m:
                    lines_cls.append("        " + doc_m)
        return "\n".join(lines_cls)

    if typ in ("If", "For", "While", "Try", "With", "Match"):
        lines_stm: list[str] = [
            f"[{stable_id}] {_fmt_range(meta)}  {_headline(meta, tree)}"
        ]
        _append_collapsed_body_lines(lines_stm, _direct_children(tree, node_id), tree)
        return "\n".join(lines_stm)

    return f"[{stable_id}] {_fmt_range(meta)}  {_headline(meta, tree)}"
