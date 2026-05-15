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


def _headline(meta: Any) -> str:
    """One-line header without assuming TreeNodeMetadata.signature exists."""
    sig = getattr(meta, "signature", None)
    if isinstance(sig, str) and sig.strip():
        return sig.strip()
    code = getattr(meta, "code", None)
    if isinstance(code, str) and code.strip():
        return code.strip().split("\n")[0]
    typ = getattr(meta, "type", None) or ""
    kind = getattr(meta, "kind", None) or ""
    name = getattr(meta, "name", None)
    if kind == "function" or typ in ("FunctionDef", "AsyncFunctionDef"):
        if typ == "AsyncFunctionDef":
            return f"async def {name or '?'}:"
        return f"def {name or '?'}:"
    if kind == "class" or typ == "ClassDef":
        return f"class {name or '?'}:"
    if typ:
        return typ
    if name:
        return str(name)
    return ""


def _function_headline(meta: Any) -> str:
    """Header line for defs (used under classes and collapsed bodies)."""
    h = _headline(meta)
    if h.startswith("def ") or h.startswith("async def "):
        return h
    name = getattr(meta, "name", None)
    typ = getattr(meta, "type", None) or ""
    if typ == "AsyncFunctionDef":
        return f"async def {name or '?'}:"
    return f"def {name or '?'}:"


def render_module(tree: Any, budget: PreviewBudget) -> str:
    """Render a structured text overview of a Python module (C-022).

    When the file has fewer lines than budget.full_text_max_lines and that
    threshold is positive, returns the raw file source instead of the
    structured overview (C-023 full-text fallback).

    Args:
        tree: CSTTree loaded for the file.
        budget: PreviewBudget with full_text_max_lines cap.

    Returns:
        Structured text string suitable for AI consumption.
    """
    file_line_count = max(
        (meta.end_line for meta in tree.metadata_map.values() if meta.end_line),
        default=0,
    )
    if budget.full_text_max_lines > 0 and file_line_count < budget.full_text_max_lines:
        file_path = getattr(tree, "file_path", None)
        if file_path:
            try:
                return pathlib.Path(file_path).read_text(encoding="utf-8")
            except Exception:
                pass

    root_id = getattr(tree, "root_node_id", None)
    top_nodes = sorted(
        (
            meta
            for meta in tree.metadata_map.values()
            if root_id is not None and meta.parent_id == root_id
        ),
        key=lambda m: m.start_line or 0,
    )

    entries: list[str] = []
    for meta in top_nodes:
        kind = meta.kind or ""
        stable_id = meta.stable_id
        rng = _fmt_range(meta)

        if kind == "import" or (
            not kind and meta.type in ("Import", "ImportFrom", "ImportStar")
        ):
            entries.append(f"[{stable_id}] {rng}  {_headline(meta)}")
        elif kind == "smallstmt":
            entries.append(f"[{stable_id}] {rng}  {_headline(meta)}")
        elif kind == "function":
            line1 = f"[{stable_id}] {rng}  {_function_headline(meta)}"
            doc = _doc_first_line(meta.docstring)
            if doc:
                entries.append(line1 + "\n    " + doc)
            else:
                entries.append(line1)
        elif kind == "class":
            line1 = f"[{stable_id}] {rng}  class {meta.name or '?'}:"
            lines_for_entry = [line1]
            doc = _doc_first_line(meta.docstring)
            if doc:
                lines_for_entry.append("    " + doc)
            node_id = next(
                (
                    nid
                    for nid, m in tree.metadata_map.items()
                    if m.stable_id == stable_id
                ),
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
                    sig = _function_headline(meth)
                    lines_for_entry.append(
                        "    [{sid}] {r}  {sig}".format(
                            sid=meth.stable_id, r=_fmt_range(meth), sig=sig
                        )
                    )
            entries.append("\n".join(lines_for_entry))

    root_meta = tree.metadata_map.get(tree.root_node_id)
    module_docstring = _doc_block_preview(root_meta.docstring if root_meta else None)
    parts: list[str] = []
    if module_docstring:
        parts.append(module_docstring)
    parts.extend(entries)
    return "\n\n".join(parts)


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


def _append_collapsed_body_lines(lines: list[str], children: list[Any]) -> None:
    """Append first-level body lines; compound statements get a trailing ``...``.

    Args:
        lines: Mutable list of output lines to extend in place.
        children: Direct child metadata rows (sorted) to render.

    Returns:
        None.
    """
    for child in children:
        sid = child.stable_id
        rng = _fmt_range(child)
        head = _headline(child)
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

    if kind in ("function", "method") or typ in ("FunctionDef", "AsyncFunctionDef"):
        line1 = f"[{stable_id}] {_fmt_range(meta)}  " f"{_function_headline(meta)}"
        lines: list[str] = [line1]
        doc = _doc_first_line(meta.docstring)
        if doc:
            lines.append("    " + doc)
        _append_collapsed_body_lines(lines, _direct_children(tree, node_id))
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
                sig = _function_headline(meth)
                lines_cls.append(f"    [{meth.stable_id}] {_fmt_range(meth)}  {sig}")
                doc_m = _doc_first_line(meth.docstring)
                if doc_m:
                    lines_cls.append("        " + doc_m)
        return "\n".join(lines_cls)

    if typ in ("If", "For", "While", "Try", "With", "Match"):
        lines_stm: list[str] = [f"[{stable_id}] {_fmt_range(meta)}  {_headline(meta)}"]
        _append_collapsed_body_lines(lines_stm, _direct_children(tree, node_id))
        return "\n".join(lines_stm)

    return f"[{stable_id}] {_fmt_range(meta)}  {_headline(meta)}"
