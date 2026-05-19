"""
Plain-text universal edit pipeline (FORMAT_TEXT draft replacement).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.universal_file_edit.edit_draft_path_utils import (
    project_root_near,
)
from code_analysis.commands.universal_file_edit.errors import (
    WRITE_FAILED,
    error_result_for_edit,
)
from code_analysis.commands.universal_file_replace_command import (
    TextReplacementTriple,
    _sort_text_replacements_bottom_up,
)
from code_analysis.commands.universal_file_edit.session import EditSession
from code_analysis.core.backup_manager import BackupManager


def run_text_draft_apply(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    """Apply text edits to ``session.draft_path`` sorted bottom-up.

    Each operation supports:
    - ``type``: replace (default) | insert | delete
    - ``start_line``: 1-based start line (inclusive).
    - ``end_line``: 1-based end line (inclusive); defaults to start_line.
    - ``content``: text to write.
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
