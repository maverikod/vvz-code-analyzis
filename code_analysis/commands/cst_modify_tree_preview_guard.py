"""
Preview-only guards for cst_modify_tree: changed-line span vs enclosing statement.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Optional, Tuple


def original_changed_line_span(
    original_code: str, modified_code: str
) -> Optional[Tuple[int, int]]:
    """
    Return 1-based inclusive (first_line, last_line) in *original* source where
    ``original_code`` and ``modified_code`` differ, using a single contiguous
    region from the first mismatch through the last (common for one replace op).

    Returns None when sources are identical.
    """
    a = original_code.splitlines()
    b = modified_code.splitlines()
    n, m = len(a), len(b)
    i = 0
    while i < n and i < m and a[i] == b[i]:
        i += 1
    if i == n and i == m:
        return None
    j = 0
    while j < (n - i) and j < (m - i) and a[n - 1 - j] == b[m - 1 - j]:
        j += 1
    first_orig = i + 1
    last_orig = n - j
    if last_orig < first_orig:
        return None
    return (first_orig, last_orig)


def enclosing_guard_line_span(tree: Any, node_id: str) -> Tuple[int, int]:
    """
    Allowed 1-based line span for edits targeting ``node_id``.

    Prefers the nearest ancestor ``SimpleStatementLine``; else the nearest
    ``FunctionDef`` / ``AsyncFunctionDef`` / ``ClassDef``; else the target's
    own span.
    """
    meta = tree.metadata_map.get(node_id)
    if not meta:
        return (1, 10**9)
    stmt_span: Optional[Tuple[int, int]] = None
    block_span: Optional[Tuple[int, int]] = None
    pid = getattr(meta, "parent_id", None)
    while pid:
        pm = tree.metadata_map.get(pid)
        if not pm:
            break
        ptype = getattr(pm, "type", "") or ""
        if ptype == "SimpleStatementLine":
            stmt_span = (pm.start_line, pm.end_line)
            break
        if ptype in ("FunctionDef", "AsyncFunctionDef", "ClassDef"):
            block_span = (pm.start_line, pm.end_line)
        pid = pm.parent_id
    if stmt_span is not None:
        return stmt_span
    if block_span is not None:
        return block_span
    return (meta.start_line, meta.end_line)


def diff_span_exceeds_guard(
    original_code: str,
    modified_code: str,
    tree: Any,
    replace_node_ids: Tuple[str, ...],
    slack_lines: int = 0,
) -> Optional[str]:
    """
    If any original line in the contiguous changed region lies outside every
    guard span for ``replace_node_ids``, return a short human message; else None.

    ``slack_lines`` expands each guard span by this many lines on each side.
    """
    span = original_changed_line_span(original_code, modified_code)
    if span is None:
        return None
    first_o, last_o = span
    if not replace_node_ids:
        return None
    intervals = [enclosing_guard_line_span(tree, nid) for nid in replace_node_ids]

    def _covers(line: int) -> bool:
        """Return whether a changed line is inside any expanded guard interval."""
        for lo, hi in intervals:
            lo2 = max(1, lo - slack_lines)
            hi2 = hi + slack_lines
            if lo2 <= line <= hi2:
                return True
        return False

    for line in range(first_o, last_o + 1):
        if not _covers(line):
            return (
                f"Changed original line {line} (range {first_o}-{last_o}) lies outside "
                f"the allowed guard span for the target node(s); refusing preview "
                f"to avoid unsafe diff."
            )
    return None
