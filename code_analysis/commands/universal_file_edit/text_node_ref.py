"""
Resolve text-format ``node_ref`` to 1-based line ranges for universal_file_edit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.commands.universal_file_edit.errors import (
    LINE_OUT_OF_RANGE,
    UNKNOWN_NODE_REF,
    error_result_for_edit,
)
from code_analysis.commands.universal_file_preview.errors import PreviewError
from code_analysis.commands.universal_file_preview.handlers.markdown_line_ranges import (
    resolve_markdown_line_range,
)


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def resolve_text_operation_line_range(
    draft_path: Path,
    op: Dict[str, Any],
) -> Optional[ErrorResult]:
    """When ``node_ref`` is set, fill ``start_line``/``end_line`` on ``op`` in place."""
    node_ref = op.get("node_ref")
    if node_ref in (None, ""):
        return None

    source = _read_source(draft_path)
    suffix = draft_path.suffix.lower()
    if suffix == ".md" or draft_path.name.endswith(".md.draft"):
        bounds = resolve_markdown_line_range(source, str(node_ref))
        if isinstance(bounds, PreviewError):
            return error_result_for_edit(
                bounds.message,
                UNKNOWN_NODE_REF,
                bounds.details,
            )
        start_line, end_line = bounds
    else:
        try:
            idx = int(str(node_ref))
        except ValueError:
            return error_result_for_edit(
                f"node_ref {node_ref!r} is not a valid integer line index.",
                UNKNOWN_NODE_REF,
                {"node_ref": node_ref},
            )
        lines = source.splitlines()
        if idx < 0 or idx >= len(lines):
            return error_result_for_edit(
                f"Line index {idx} out of range [0, {len(lines)}).",
                LINE_OUT_OF_RANGE,
                {"node_ref": node_ref, "total_lines": len(lines)},
            )
        start_line = idx + 1
        end_line = start_line

    op_type = op.get("type", "replace")
    if op_type == "insert":
        position = op.get("position", "after")
        if position not in (None, "after", "before", "last"):
            return error_result_for_edit(
                f"insert position must be 'before' or 'after', got {position!r}",
                LINE_OUT_OF_RANGE,
                {"position": position, "node_ref": node_ref},
            )
        if position == "before":
            op["start_line"] = start_line
        else:
            op["start_line"] = end_line + 1
        op.pop("end_line", None)
    else:
        op["start_line"] = start_line
        op["end_line"] = end_line
    return None
