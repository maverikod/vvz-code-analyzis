"""
MCP command: replace_file_lines

Replace a range of lines in a file (for fixing syntax errors without full CST parse).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .anchor_check import AnchorMismatch, check_cst_anchor, check_text_anchor
from .base_mcp_command import BaseMCPCommand
from .base_mcp_command_resolve_path import resolve_under_project_root
from .project_text_file_guard import reject_if_write_under_project_venv
from .line_command_cst_gate import (
    LINE_CMD_DISALLOWED_MSG,
    healthy_parse_blocks_line_ops,
)
from ..core.backup_manager import BackupManager
from ..core.git_integration import commit_after_write
from ..core.file_lock import file_lock
from ..core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class ReplaceFileLinesCommand(BaseMCPCommand):
    """Replace a range of lines in a project file; backup on disk; no index update."""

    name = "replace_file_lines"
    version = "1.2.0"
    descr = (
        "Replace a range of lines in a file (1-based). Use to fix syntax errors "
        "when cst_load_file fails. Mandatory version backup under project ``old_code`` "
        "when backup=true; optional git commit when ``git_commit_on_write`` is enabled. "
        "Does not update the code index — run update_indexes if needed."
    )
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID (UUID4)",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path relative to project root",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line (1-based, inclusive)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line (1-based, inclusive)",
                },
                "new_lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New lines to replace the range (no newlines in items)",
                },
                "backup": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to create backup before replace",
                },
                "anchor_head": {
                    "type": "string",
                    "description": (
                        "First 5 non-whitespace chars of the first line in "
                        "[start_line, end_line]. Server rejects the write if "
                        "actual content differs."
                    ),
                },
                "anchor_tail": {
                    "type": "string",
                    "description": (
                        "Last 5 non-whitespace chars of the last line in "
                        "[start_line, end_line]. Server rejects the write if "
                        "actual content differs."
                    ),
                },
                "anchor_node_id": {
                    "type": "string",
                    "description": (
                        "Python files only: stable_id (UUID4) of the CST node "
                        "at start_line. Mutually exclusive with "
                        "anchor_head/anchor_tail."
                    ),
                },
            },
            "required": [
                "project_id",
                "file_path",
                "start_line",
                "end_line",
                "new_lines",
            ],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        start_line: int,
        end_line: int,
        new_lines: List[str],
        backup: bool = True,
        allow_healthy_line_ops: bool = False,
        **kwargs: Any,
    ) -> SuccessResult:
        try:
            if start_line < 1 or end_line < 1:
                return ErrorResult(
                    message="start_line and end_line must be >= 1",
                    code="INVALID_RANGE",
                    details={"start_line": start_line, "end_line": end_line},
                )
            if start_line > end_line:
                return ErrorResult(
                    message="start_line must be <= end_line",
                    code="INVALID_RANGE",
                    details={"start_line": start_line, "end_line": end_line},
                )

            root_dir = self._resolve_project_root(project_id).resolve()
            try:
                absolute_path = resolve_under_project_root(
                    root_dir, file_path, require_exists=True, must_be_file=True
                )
            except ValidationError as e:
                return ErrorResult(
                    message=str(e),
                    code="VALIDATION_ERROR",
                    details=getattr(e, "details", None)
                    or {"field": getattr(e, "field", None)},
                )

            blocked_venv = reject_if_write_under_project_venv(absolute_path, root_dir)
            if blocked_venv is not None:
                return blocked_venv

            text = absolute_path.read_text(encoding="utf-8", errors="replace")
            all_lines = text.splitlines(keepends=False)

            anchor_head = kwargs.get("anchor_head")
            anchor_tail = kwargs.get("anchor_tail")
            anchor_node_id = kwargs.get("anchor_node_id")
            if anchor_node_id is not None and (
                anchor_head is not None or anchor_tail is not None
            ):
                return ErrorResult(
                    message=(
                        "anchor_node_id is mutually exclusive with "
                        "anchor_head/anchor_tail"
                    ),
                    code="VALIDATION_ERROR",
                    details={
                        "fields": ["anchor_node_id", "anchor_head", "anchor_tail"]
                    },
                )
            if (anchor_head is None) != (anchor_tail is None):
                return ErrorResult(
                    message="anchor_head and anchor_tail must be supplied together",
                    code="VALIDATION_ERROR",
                    details={"fields": ["anchor_head", "anchor_tail"]},
                )
            if anchor_node_id is not None:
                if not isinstance(anchor_node_id, str):
                    return ErrorResult(
                        message="anchor_node_id must be a string",
                        code="VALIDATION_ERROR",
                        details={"field": "anchor_node_id"},
                    )
                if absolute_path.suffix.lower() not in {".py", ".pyi", ".pyw"}:
                    return ErrorResult(
                        message=(
                            "anchor_node_id is only valid for Python files "
                            "(.py/.pyi/.pyw)"
                        ),
                        code="VALIDATION_ERROR",
                        details={"file_path": file_path},
                    )
                try:
                    check_cst_anchor(absolute_path, start_line, anchor_node_id)
                except AnchorMismatch as e:
                    return ErrorResult(
                        message=str(e),
                        code="ANCHOR_MISMATCH",
                        details=e.details,
                    )
            elif anchor_head is not None or anchor_tail is not None:
                if not isinstance(anchor_head, str) or not isinstance(anchor_tail, str):
                    return ErrorResult(
                        message="anchor_head and anchor_tail must be strings",
                        code="VALIDATION_ERROR",
                        details={"fields": ["anchor_head", "anchor_tail"]},
                    )
                try:
                    check_text_anchor(
                        all_lines,
                        start_line,
                        end_line,
                        anchor_head,
                        anchor_tail,
                    )
                except AnchorMismatch as e:
                    return ErrorResult(
                        message=str(e),
                        code="ANCHOR_MISMATCH",
                        details=e.details,
                    )

            config_data = self._get_raw_config()
            allow_on_healthy = config_data.get("code_analysis", {}).get(
                "allow_line_commands_on_healthy_files", False
            )
            if healthy_parse_blocks_line_ops(
                text,
                allow_healthy_line_ops=allow_healthy_line_ops,
                allow_line_commands_on_healthy_files=bool(allow_on_healthy),
                file_path=file_path,
            ):
                return ErrorResult(
                    message=LINE_CMD_DISALLOWED_MSG,
                    code="USE_CST_COMMANDS",
                    details={
                        "file_path": file_path,
                        "cst_commands": [
                            "cst_load_file",
                            "cst_modify_tree",
                            "cst_modify_tree",
                        ],
                    },
                )
            total = len(all_lines)
            if total == 0:
                return ErrorResult(
                    message="File is empty",
                    code="EMPTY_FILE",
                    details={"file_path": file_path},
                )

            low = max(0, min(start_line - 1, total - 1))
            high = max(0, min(end_line - 1, total - 1))
            if low > high:
                low, high = high, low

            new_content_lines = all_lines[:low] + new_lines + all_lines[high + 1 :]
            source_code = "\n".join(new_content_lines)

            backup_uuid: Optional[str] = None
            backup_manager = BackupManager(root_dir)
            try:
                rel = str(absolute_path.relative_to(root_dir))
            except ValueError:
                rel = str(absolute_path)

            with file_lock(absolute_path):
                if backup:
                    backup_uuid = backup_manager.create_backup(
                        absolute_path,
                        command="replace_file_lines",
                        comment=f"Before replace_file_lines {start_line}-{end_line}",
                    )
                    if not backup_uuid:
                        return ErrorResult(
                            message=(
                                "Backup to old_code (versions) is mandatory before write; "
                                "create_backup failed. Aborting replace_file_lines."
                            ),
                            code="BACKUP_REQUIRED",
                            details={"file_path": str(absolute_path)},
                        )

                try:
                    absolute_path.write_text(source_code, encoding="utf-8")
                except Exception:
                    if backup_uuid:
                        backup_manager.restore_file(rel, backup_uuid)
                    raise

            git_ok, git_err = commit_after_write(
                root_dir.resolve(),
                [absolute_path],
                "replace_file_lines",
                commit_message_override=None,
                config_data=BaseMCPCommand._get_raw_config(),
            )
            if not git_ok and git_err:
                logger.warning("Git commit after replace_file_lines: %s", git_err)

            return SuccessResult(
                data={
                    "success": True,
                    "file_path": str(absolute_path),
                    "relative_path": rel,
                    "backup_uuid": backup_uuid,
                    "start_line": start_line,
                    "end_line": end_line,
                    "replaced_line_count": high - low + 1,
                    "new_line_count": len(new_lines),
                }
            )

        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        except Exception as e:
            logger.exception("replace_file_lines failed: %s", e)
            return ErrorResult(
                message=f"replace_file_lines failed: {e}",
                code="REPLACE_FILE_LINES_ERROR",
            )
