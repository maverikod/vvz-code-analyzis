"""
Line-based diff preview for Python edit sessions.

Builds clean and annotated logical source from the session tree, diffs committed
file vs draft by lines, and decorates ``+`` draft rows with ``[stable_id]`` prefixes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any, Optional

from code_analysis.core.cst_tree.node_id_markers import strip_persisted_node_ids
from code_analysis.core.cst_tree.node_stable_id import (
    strip_inline_node_id_lines_from_source,
)
from code_analysis.core.cst_tree.tree_builder import (
    _on_disk_logical_matches_tree_snapshot,
)

from .budget import PreviewBudget
from .python_visualizer import (
    build_logical_line_to_stable_id,
    clean_logical_lines_for_tree,
    render_module,
    render_node,
)

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _logical_source_from_disk(file_path: Path) -> Optional[str]:
    if not file_path.is_file():
        return None
    raw = file_path.read_text(encoding="utf-8")
    logical, _ = strip_persisted_node_ids(raw)
    return strip_inline_node_id_lines_from_source(logical)


def committed_clean_lines(file_path: str) -> list[str]:
    logical = _logical_source_from_disk(Path(file_path))
    if logical is None:
        return []
    return logical.splitlines()


def session_differs_from_disk(tree: Any, file_path: str) -> bool:
    """True when in-memory module code differs from the on-disk committed snapshot."""
    disk_hex = getattr(tree, "disk_source_sha256_hex", None)
    module_hex = getattr(tree, "module_source_sha256_hex", None)
    if isinstance(disk_hex, str) and isinstance(module_hex, str):
        return disk_hex != module_hex

    path = Path(file_path)
    if not path.is_file():
        module = getattr(tree, "module", None)
        code = getattr(module, "code", None) if module is not None else None
        return bool(isinstance(code, str) and code.strip())

    if _on_disk_logical_matches_tree_snapshot(path, tree):
        return False

    logical_disk = _logical_source_from_disk(path)
    draft = clean_logical_lines_for_tree(tree)
    if logical_disk is None:
        return bool(draft)
    return logical_disk.splitlines() != draft


def _find_meta(tree: Any, stable_id: str) -> Any | None:
    metadata_map = getattr(tree, "metadata_map", None) or {}
    return next(
        (
            m
            for m in metadata_map.values()
            if getattr(m, "stable_id", None) == stable_id
        ),
        None,
    )


def _block_start_index(lines: list[str], anchor: str) -> int | None:
    target = anchor.strip()
    for idx, line in enumerate(lines):
        if line.strip() == target:
            return idx
    return None


def _extract_block_from_index(lines: list[str], start_idx: int) -> list[str]:
    if start_idx < 0 or start_idx >= len(lines):
        return []
    first = lines[start_idx]
    base_col = len(first) - len(first.lstrip())
    out = [first]
    for line in lines[start_idx + 1 :]:
        if not line.strip():
            out.append(line)
            continue
        col = len(line) - len(line.lstrip())
        if col <= base_col:
            break
        out.append(line)
    return out


def _slice_for_focus(
    committed_lines: list[str],
    draft_lines: list[str],
    tree: Any,
    focus_stable_id: Optional[str],
) -> tuple[list[str], list[str], dict[int, str]]:
    """Return committed/draft slices and draft stable_id map for a focus node."""
    line_to_stable_id = build_logical_line_to_stable_id(tree, draft_lines)
    if not focus_stable_id:
        return committed_lines, draft_lines, line_to_stable_id

    meta = _find_meta(tree, focus_stable_id)
    if meta is None:
        return committed_lines, draft_lines, line_to_stable_id

    import libcst as cst

    node = tree.node_map.get(meta.node_id)
    if not isinstance(node, (cst.FunctionDef, cst.ClassDef)):
        return committed_lines, draft_lines, line_to_stable_id

    start_line = int(getattr(meta, "start_line", 0) or 0)
    end_line = int(getattr(meta, "end_line", 0) or 0)
    if start_line < 1 or end_line < start_line:
        return committed_lines, draft_lines, line_to_stable_id

    draft_start = start_line - 1
    if draft_start >= len(draft_lines):
        return committed_lines, draft_lines, line_to_stable_id
    draft_end = min(end_line, len(draft_lines))
    draft_slice = draft_lines[draft_start:draft_end]
    if not draft_slice:
        return committed_lines, draft_lines, line_to_stable_id

    anchor = draft_slice[0].strip()
    committed_start = _block_start_index(committed_lines, anchor)
    if committed_start is None:
        raw = tree.module.code_for_node(node)
        logical = strip_inline_node_id_lines_from_source(raw)
        logical, _ = strip_persisted_node_ids(logical)
        header = logical.splitlines()[0].strip() if logical.strip() else ""
        if header:
            committed_start = _block_start_index(committed_lines, header)

    if committed_start is None:
        committed_slice: list[str] = []
    else:
        committed_slice = _extract_block_from_index(committed_lines, committed_start)

    shifted = {
        line_no - draft_start: sid
        for line_no, sid in line_to_stable_id.items()
        if start_line <= line_no <= end_line
    }
    return committed_slice, draft_slice, shifted


def _decorate_unified_diff(
    diff_lines: list[str],
    draft_line_to_stable_id: dict[int, str],
    *,
    max_lines: int,
) -> list[str]:
    """Attach ``[stable_id]`` prefixes to ``+`` draft rows from annotated map."""
    out: list[str] = []
    draft_line = 0
    for line in diff_lines:
        if len(out) >= max_lines:
            out.append("... (diff truncated)")
            break
        hunk = _HUNK_RE.match(line)
        if hunk:
            draft_line = int(hunk.group(3)) - 1
            out.append(line)
            continue
        if line.startswith("---") or line.startswith("+++"):
            out.append(line)
            continue
        if line.startswith("+"):
            draft_line += 1
            sid = draft_line_to_stable_id.get(draft_line)
            if sid:
                out.append(f"+[{sid}] {line[1:]}")
            else:
                out.append(line)
            continue
        if line.startswith("-"):
            out.append(line)
            continue
        if line.startswith(" "):
            draft_line += 1
            out.append(line)
            continue
        out.append(line)
    return out


def render_line_diff_preview(
    committed_lines: list[str],
    draft_lines: list[str],
    draft_tree: Any,
    budget: PreviewBudget,
    *,
    focus_stable_id: Optional[str] = None,
) -> str:
    """Diff clean committed vs draft lines; decorate ``+`` rows with stable_ids."""
    committed_slice, draft_slice, id_map = _slice_for_focus(
        committed_lines, draft_lines, draft_tree, focus_stable_id
    )
    if committed_slice == draft_slice:
        if focus_stable_id:
            return render_node(draft_tree, focus_stable_id, budget)
        return render_module(draft_tree, budget)

    raw_diff = list(
        difflib.unified_diff(
            committed_slice,
            draft_slice,
            fromfile="committed",
            tofile="draft",
            lineterm="",
            n=3,
        )
    )
    if not raw_diff:
        if focus_stable_id:
            return render_node(draft_tree, focus_stable_id, budget)
        return render_module(draft_tree, budget)

    body = _decorate_unified_diff(
        raw_diff,
        id_map,
        max_lines=max(budget.preview_lines * 6, 40),
    )
    header = [
        "# draft diff (committed file → session tree)",
        "# line diff on clean source; + rows may include [stable_id] from session tree",
        "",
    ]
    return "\n".join(header + body).rstrip()


def render_preview_with_optional_diff(
    tree: Any,
    file_path: str,
    budget: PreviewBudget,
    *,
    focus_stable_id: Optional[str] = None,
) -> str:
    """Annotated view, or line diff when session draft differs from on-disk file."""
    if not session_differs_from_disk(tree, file_path):
        if focus_stable_id:
            return render_node(tree, focus_stable_id, budget)
        return render_module(tree, budget)

    committed = committed_clean_lines(file_path)
    draft = clean_logical_lines_for_tree(tree)
    if not committed and not draft:
        if focus_stable_id:
            return render_node(tree, focus_stable_id, budget)
        return render_module(tree, budget)

    return render_line_diff_preview(
        committed,
        draft,
        tree,
        budget,
        focus_stable_id=focus_stable_id,
    )
