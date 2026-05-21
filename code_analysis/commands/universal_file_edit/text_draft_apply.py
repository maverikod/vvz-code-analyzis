"""
Plain-text universal edit pipeline (FORMAT_TEXT draft replacement).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.anchor_check import AnchorMismatch, check_text_anchor
from code_analysis.commands.universal_file_edit.edit_draft_path_utils import (
    project_root_near,
)
from code_analysis.commands.universal_file_edit.errors import (
    ANCHOR_MISMATCH,
    LINE_OUT_OF_RANGE,
    WRITE_FAILED,
    error_result_for_edit,
)
from code_analysis.commands.universal_file_replace_command import (
    TextReplacementTriple,
    _sort_text_replacements_bottom_up,
)
from code_analysis.commands.universal_file_edit.session import EditSession
from code_analysis.commands.universal_file_edit.text_node_ref import (
    resolve_text_operation_line_range,
)
from code_analysis.core.backup_manager import BackupManager


def _line_count(buffer: List[str]) -> int:
    return len(buffer)


def _resolve_line_range(op: Dict[str, Any]) -> tuple[int, int]:
    start_line = int(op.get("start_line", 1))
    end_raw = op.get("end_line")
    end_line = start_line if end_raw is None else int(end_raw)
    return start_line, end_line


def _validate_text_line_operation(
    buffer: List[str],
    op: Dict[str, Any],
) -> Optional[ErrorResult]:
    """Validate one text edit operation against the current draft buffer."""
    if op.get("position") == "last":
        return None

    op_type = op.get("type", "replace")
    start_line, end_line = _resolve_line_range(op)
    line_count = _line_count(buffer)

    if start_line < 1:
        return error_result_for_edit(
            f"start_line must be >= 1, got {start_line}",
            LINE_OUT_OF_RANGE,
            {"start_line": start_line, "end_line": end_line, "line_count": line_count},
        )
    if end_line < start_line:
        return error_result_for_edit(
            f"end_line ({end_line}) must be >= start_line ({start_line})",
            LINE_OUT_OF_RANGE,
            {"start_line": start_line, "end_line": end_line, "line_count": line_count},
        )

    anchor_head = op.get("anchor_head")
    anchor_tail = op.get("anchor_tail")
    if (anchor_head is None) != (anchor_tail is None):
        return error_result_for_edit(
            "anchor_head and anchor_tail must be supplied together",
            LINE_OUT_OF_RANGE,
            {"fields": ["anchor_head", "anchor_tail"]},
        )

    if op_type == "insert":
        if start_line > line_count + 1:
            return error_result_for_edit(
                f"insert start_line {start_line} is beyond end of file "
                f"(line_count={line_count}; max insert line is {line_count + 1})",
                LINE_OUT_OF_RANGE,
                {
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_count": line_count,
                    "hint": (
                        "Line numbers are 1-based against the current draft. "
                        "Re-run universal_file_preview with session_id after each edit."
                    ),
                },
            )
    elif op_type in ("replace", "delete"):
        if start_line > line_count or end_line > line_count:
            return error_result_for_edit(
                f"line range {start_line}-{end_line} is out of range "
                f"(draft has {line_count} lines)",
                LINE_OUT_OF_RANGE,
                {
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_count": line_count,
                    "hint": (
                        "Line numbers are 1-based against the current draft. "
                        "Do not reuse line numbers from fulltext_search or an earlier "
                        "read after a prior universal_file_edit call — re-run "
                        "universal_file_preview with session_id first."
                    ),
                },
            )
        if anchor_head is not None:
            try:
                check_text_anchor(
                    buffer,
                    start_line,
                    end_line,
                    anchor_head,
                    anchor_tail,
                )
            except AnchorMismatch as exc:
                return error_result_for_edit(
                    str(exc),
                    ANCHOR_MISMATCH,
                    {
                        **exc.details,
                        "line_count": line_count,
                        "hint": (
                            "The target lines no longer match the expected content. "
                            "Re-run universal_file_preview with session_id to obtain "
                            "fresh line numbers from the draft."
                        ),
                    },
                )

    return None


def run_text_draft_apply(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    """Apply text edits to ``session.draft_path`` sorted bottom-up.

    Each operation supports:
    - ``type``: replace (default) | insert | delete
    - ``node_ref``: optional; for ``.md`` slug paths from preview, or zero-based
      line index for other text files. Takes precedence over ``start_line``/``end_line``.
    - ``start_line``: 1-based start line (inclusive).
    - ``end_line``: 1-based end line (inclusive); defaults to start_line.
    - ``content``: text to write.
    - ``anchor_head`` / ``anchor_tail``: optional fingerprints of the target
      range (first/last line, first/last five non-whitespace chars). When
      supplied, both must be present and must match the current draft lines
      before the edit is applied.
    - ``position``: ``'last'`` — append to end of file.
      When ``position='last'``, ``start_line``/``end_line`` are ignored.
    """

    try:
        root_dir = project_root_near(session.draft_path)
        bm = BackupManager(root_dir=root_dir)
        if session.draft_path.exists():
            bm.create_backup(
                session.draft_path,
                command="universal_file_edit",
            )
    except Exception as exc:
        return error_result_for_edit(
            f"Backup before edit failed: {exc}",
            WRITE_FAILED,
            {"path": str(session.draft_path)},
        )

    buffer = session.draft_path.read_text(encoding="utf-8").splitlines(keepends=True)

    for op in operations:
        ref_err = resolve_text_operation_line_range(session.draft_path, op)
        if ref_err is not None:
            return ref_err

    for op in operations:
        if not session.is_invalid:
            continue
        if op.get("type", "replace") != "replace":
            continue
        if op.get("node_ref") not in ("", None):
            continue
        content_raw = op.get("content", op.get("code", ""))
        content_str = content_raw if isinstance(content_raw, str) else str(content_raw)
        block = content_str if content_str.endswith("\n") else content_str + "\n"
        session.draft_path.write_text(block, encoding="utf-8")
        return SuccessResult(
            data={"success": True, "line_count": len(block.splitlines())},
        )

    # Separate position='last' ops (always append, no sort needed) from
    # line-targeted ops (must be applied bottom-up to keep line numbers stable).
    append_ops: List[Dict[str, Any]] = []
    line_ops: List[Dict[str, Any]] = []
    for op in operations:
        if op.get("position") == "last":
            append_ops.append(op)
        else:
            line_ops.append(op)

    for op in line_ops:
        validation = _validate_text_line_operation(buffer, op)
        if validation is not None:
            return validation

    # Sort line-targeted ops bottom-up.
    keyed: List[Dict[str, Any]] = []
    for op in line_ops:
        s_ln = int(op.get("start_line", 1))
        e_raw = op.get("end_line")
        e_ln = s_ln if e_raw is None else int(e_raw)
        keyed.append({"start": s_ln, "end": e_ln, "op": op})
    triples_only: List[TextReplacementTriple] = [
        (int(k["start"]), int(k["end"]), [], None, None) for k in keyed
    ]
    _sort_text_replacements_bottom_up(triples_only)
    keyed.sort(key=lambda row: (row["start"], row["end"]), reverse=True)
    sorted_ops = [row["op"] for row in keyed]

    # Apply line-targeted ops first (bottom-up).
    for op in sorted_ops:
        start = int(op.get("start_line", 1)) - 1
        e_raw = op.get("end_line")
        end = (start + 1) if e_raw is None else int(e_raw)
        content_raw = op.get("content", "")
        content_str = content_raw if isinstance(content_raw, str) else str(content_raw)
        op_type = op.get("type", "replace")
        if op_type == "delete":
            del buffer[start:end]
        elif op_type == "insert":
            inserted = content_str if content_str.endswith("\n") else content_str + "\n"
            buffer.insert(start, inserted)
        else:
            block = content_str if content_str.endswith("\n") else content_str + "\n"
            buffer[start:end] = [block]

    # Apply position='last' ops in order (append to current end of buffer).
    for op in append_ops:
        content_raw = op.get("content", "")
        content_str = content_raw if isinstance(content_raw, str) else str(content_raw)
        op_type = op.get("type", "replace")
        if op_type == "delete":
            # delete with position='last' removes the last line if buffer non-empty
            if buffer:
                buffer.pop()
        else:
            # insert and replace both append to end
            appended = content_str if content_str.endswith("\n") else content_str + "\n"
            buffer.append(appended)

    session.draft_path.write_text("".join(buffer), encoding="utf-8")

    return SuccessResult(
        data={"success": True, "line_count": len(buffer)},
    )
