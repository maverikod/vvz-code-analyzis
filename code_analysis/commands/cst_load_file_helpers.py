"""
Helpers for cst_load_file: syntax-error fix and response building.

All fixes are applied on a temporary copy (or in-memory lines); if recovery
fails, the original file is never modified and the initial error is returned.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import libcst as cst

from ..core.cst_tree.models import CSTTree
from ..core.cst_tree.skeleton import build_declarative_overview, build_node_declarative_overview
from ..core.cst_tree.tree_finder import find_nodes
from ..core.cst_tree.tree_metadata import get_node_metadata

logger = logging.getLogger(__name__)

# Default context size: lines before and after the error line to include in error responses
ERROR_CONTEXT_BEFORE = 100
ERROR_CONTEXT_AFTER = 100


def build_error_source_context(
    file_path: Path,
    error_line_1based: Optional[int] = None,
    context_before: int = ERROR_CONTEXT_BEFORE,
    context_after: int = ERROR_CONTEXT_AFTER,
) -> Tuple[List[str], int]:
    """
    Build source context for error response: lines around the error line.

    Returns (list of lines, 1-based start line). If file cannot be read,
    returns ([], 1). Used so the model sees the error and surrounding code.
    """
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ([], 1)
    if not lines:
        return ([], 1)
    if error_line_1based is None or error_line_1based < 1:
        error_line_1based = 1
    idx = min(error_line_1based - 1, len(lines) - 1)
    start = max(0, idx - context_before)
    end = min(len(lines), idx + context_after + 1)
    return (lines[start:end], start + 1)


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


def classify_syntax_error(message: str) -> str:
    """
    Classify parser error from message text.
    Returns "indentation" if error suggests indent/dedent/expected block end,
    else "syntax" (comment-out fallback).
    """
    msg = message.lower()
    if "indent" in msg or "dedent" in msg:
        logger.debug(
            "classify_syntax_error message_preview=%s -> indentation", msg[:80]
        )
        return "indentation"
    if "expected" in msg and (
        "except" in msg
        or "finally" in msg
        or "elif" in msg
        or "else" in msg
        or ":" in msg
    ):
        logger.debug(
            "classify_syntax_error message_preview=%s -> indentation", msg[:80]
        )
        return "indentation"
    if "unexpected indent" in msg or "expected an indented block" in msg:
        logger.debug(
            "classify_syntax_error message_preview=%s -> indentation", msg[:80]
        )
        return "indentation"
    logger.debug("classify_syntax_error message_preview=%s -> syntax", msg[:80])
    return "syntax"


def get_line_indent(line: str) -> int:
    """Return number of leading spaces (tabs treated as 4 for consistency)."""
    if not line.startswith(" ") and not line.startswith("\t"):
        return 0
    spaces = 0
    for c in line:
        if c == " ":
            spaces += 1
        elif c == "\t":
            spaces += 4
        else:
            break
    return spaces


def _get_prev_non_empty_line(lines: List[str], from_idx: int) -> Optional[int]:
    """Return 0-based index of last non-empty, non-comment line before from_idx."""
    for i in range(from_idx - 1, -1, -1):
        s = lines[i].strip()
        if s and not s.startswith("#"):
            return i
    return None


def try_apply_indent_fix(lines: List[str], line_no_1based: int) -> List[str]:
    """
    Fix indent of the given line (1-based) using previous non-empty line.
    If previous line is a block starter, set indent to prev + 4 spaces;
    else set to same as previous. All work on copy; does not modify original.
    """
    if line_no_1based < 1 or line_no_1based > len(lines):
        logger.debug(
            "try_apply_indent_fix line_no=%s out of range (1..%s) -> no change",
            line_no_1based,
            len(lines),
        )
        return list(lines)
    idx = line_no_1based - 1
    line = lines[idx]
    if not line.strip():
        logger.debug(
            "try_apply_indent_fix line_no=%s line is empty -> no change", line_no_1based
        )
        return list(lines)
    prev_idx = _get_prev_non_empty_line(lines, idx)
    if prev_idx is None:
        new_indent = ""
        logger.debug(
            "try_apply_indent_fix line_no=%s no prev line -> indent ''", line_no_1based
        )
    else:
        prev_line = lines[prev_idx]
        prev_indent_len = get_line_indent(prev_line)
        prev_stripped = prev_line.strip()
        if is_block_starter_line(prev_stripped):
            new_indent = " " * (prev_indent_len + 4)
            logger.debug(
                "try_apply_indent_fix line_no=%s prev_line_no=%s block_starter -> indent len=%s",
                line_no_1based,
                prev_idx + 1,
                prev_indent_len + 4,
            )
        else:
            new_indent = " " * prev_indent_len
            logger.debug(
                "try_apply_indent_fix line_no=%s prev_line_no=%s same indent len=%s",
                line_no_1based,
                prev_idx + 1,
                prev_indent_len,
            )
    new_line = new_indent + line.strip()
    result = list(lines)
    result[idx] = new_line
    return result


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
    Used when error is not indentation or indent fix did not help.
    Returns (new_lines, 1-based line number of the '# original' line in result).
    """
    line_no = getattr(e, "raw_line", None)
    if line_no is None or line_no < 1:
        line_no = 1
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
            logger.debug(
                "apply_syntax_error_fix dedent at line 1 -> using candidate line_no=%s",
                candidate,
            )
            line_no = candidate
    idx = max(0, min(line_no - 1, len(lines) - 1))
    if not lines[idx].strip():
        # Empty line: find next non-empty
        for i in range(idx + 1, len(lines)):
            if lines[i].strip():
                idx = i
                break
        else:
            idx = 0
    raw = lines[idx]
    lead = raw[: len(raw) - len(raw.lstrip())]
    stripped = raw.strip()
    if stripped.startswith("#"):
        # Already comment: comment the next non-empty line
        for i in range(idx + 1, len(lines)):
            if lines[i].strip() and not lines[i].strip().startswith("#"):
                idx = i
                raw = lines[idx]
                lead = raw[: len(raw) - len(raw.lstrip())]
                stripped = raw.strip()
                break
        else:
            idx = 0
            raw = lines[0]
            lead = raw[: len(raw) - len(raw.lstrip())]
            stripped = raw.strip() or "# (no content)"
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
    """Build response dict for cst_load_file (full or declarative, optional selected_nodes)."""
    data: Dict[str, Any] = {
        "success": True,
        "tree_id": tree.tree_id,
        "file_path": str(target),
    }
    if return_format in {"declarative", "skeleton"}:
        overview, outline_nodes = build_declarative_overview(tree)
        data["declarative"] = overview
        data["outline_nodes"] = outline_nodes
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
                if isinstance(node_id, str):
                    if node_id in tree.metadata_map:
                        selected_metas.append(tree.metadata_map[node_id])
                    else:
                        meta = tree.find_by_stable_id(node_id)
                        if meta:
                            selected_metas.append(meta)
        elif isinstance(selector, dict):
            q = selector.get("query")
            if isinstance(q, str):
                try:
                    selected_metas = find_nodes(
                        tree.tree_id, query=q, search_type="xpath"
                    )
                except ValueError:
                    pass
            else:
                raw_ids = selector.get("node_ids")
                if isinstance(raw_ids, list):
                    for node_id in raw_ids:
                        if isinstance(node_id, str):
                            if node_id in tree.metadata_map:
                                selected_metas.append(tree.metadata_map[node_id])
                            else:
                                meta = tree.find_by_stable_id(node_id)
                                if meta:
                                    selected_metas.append(meta)
        selected_with_code = []
        for meta in selected_metas:
            entry = meta.to_dict()
            # Apply declarative rules: function/method/class -> skeleton view;
            # other node kinds -> include full code inline.
            if meta.kind in {"function", "method", "class"}:
                overview_text, outline = build_node_declarative_overview(
                    tree, meta.node_id
                )
                entry["declarative"] = overview_text
                entry["outline_nodes"] = outline
            else:
                with_code = get_node_metadata(
                    tree.tree_id, meta.node_id, include_code=True
                )
                if with_code:
                    entry = with_code.to_dict()
            selected_with_code.append(entry)
        data["selected_nodes"] = selected_with_code

    if commented_lines_info:
        data["syntax_errors_fixed"] = True
        data["commented_lines"] = commented_lines_info
        data["temp_file"] = str(path_tmp) if path_tmp else None

    return data
