"""
Helpers for cst_load_file: syntax-error fix and response building.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import libcst as cst

from ..core.cst_tree.models import CSTTree
from ..core.cst_tree.skeleton import skeleton_from_tree
from ..core.cst_tree.tree_finder import find_nodes
from ..core.cst_tree.tree_metadata import get_node_metadata

# Prefix for the TODO comment above a commented-out error line
TODO_PREFIX = "TODO: The line following this one was commented out due to an error: "
MAX_SYNTAX_FIX_ITERATIONS = 100

# Block starters that require a body (so we add pass with body indent)
BLOCK_STARTERS = (
    "if ",
    "elif ",
    "else:",
    "try:",
    "except ",
    "except:",
    "finally:",
    "def ",
    "class ",
    "for ",
    "while ",
    "with ",
)


def is_block_starter_line(stripped: str) -> bool:
    """True if stripped line starts a block (if/def/for/else/...)."""
    if not stripped.endswith(":"):
        return False
    key = stripped.split("(")[0].strip() if "(" in stripped else stripped
    return any(key.startswith(s.rstrip(":")) or key == s for s in BLOCK_STARTERS)


def indent_for_pass_after_error(lines: List[str], error_line_idx: int) -> str:
    """
    Find indent for a placeholder 'pass' so the block stays valid.
    Scans upward for a line that starts a block (if/def/else/...), returns its
    indent plus one level (4 spaces).
    """
    for i in range(error_line_idx - 1, -1, -1):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if is_block_starter_line(stripped):
            lead = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            return lead + "    "
    return "    "


def apply_syntax_error_fix(
    lines: List[str], e: cst.ParserSyntaxError
) -> Tuple[List[str], int]:
    """
    Comment out the line reported by the parser and add TODO.
    Returns (new_lines, 1-based line number of the '# original' line in result).
    """
    line_no = e.raw_line
    err_msg = str(e).lower()
    if line_no == 1 and "dedent" in err_msg:
        candidate = None
        for i, line in enumerate(lines):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if line and not line[: len(line) - len(line.lstrip())]:
                if is_block_starter_line(s):
                    candidate = i + 1
        if candidate is not None:
            line_no = candidate
    idx = line_no - 1
    if idx < 0 or idx >= len(lines) or not lines[idx].strip():
        raise
    raw = lines[idx]
    lead = raw[: len(raw) - len(raw.lstrip())]
    stripped = raw.strip()
    if stripped.startswith("#"):
        raise
    err_text = str(e).strip().replace("\n", " ")
    todo_line = lead + "# " + TODO_PREFIX + err_text
    comment_line = lead + "# " + stripped
    pass_indent = indent_for_pass_after_error(lines, idx)
    fixed = (
        lines[:idx] + [todo_line, comment_line, pass_indent + "pass"] + lines[idx + 1 :]
    )
    comment_line_no = idx + 2
    return fixed, comment_line_no


def build_load_response(
    tree: CSTTree,
    target: Path,
    return_format: str,
    selector: Optional[Any],
    commented_lines_info: List[Dict[str, Any]],
    path_tmp: Optional[Path],
) -> Dict[str, Any]:
    """Build response dict for cst_load_file (full or skeleton, optional selected_nodes)."""
    data: Dict[str, Any] = {
        "success": True,
        "tree_id": tree.tree_id,
        "file_path": str(target),
    }
    if return_format == "skeleton":
        data["skeleton"] = skeleton_from_tree(tree)
    else:
        nodes = [meta.to_dict() for meta in tree.metadata_map.values()]
        data["nodes"] = nodes
        data["total_nodes"] = len(nodes)

    if selector is not None:
        selected_metas: List[Any] = []
        if isinstance(selector, str):
            try:
                selected_metas = find_nodes(
                    tree.tree_id, query=selector, search_type="xpath"
                )
            except ValueError:
                pass
        elif isinstance(selector, list):
            for node_id in selector:
                if isinstance(node_id, str) and node_id in tree.metadata_map:
                    selected_metas.append(tree.metadata_map[node_id])
        selected_with_code = []
        for meta in selected_metas:
            with_code = get_node_metadata(tree.tree_id, meta.node_id, include_code=True)
            selected_with_code.append(
                with_code.to_dict() if with_code else meta.to_dict()
            )
        data["selected_nodes"] = selected_with_code

    if commented_lines_info:
        data["syntax_errors_fixed"] = True
        data["commented_lines"] = commented_lines_info
        data["temp_file"] = str(path_tmp) if path_tmp else None

    return data
