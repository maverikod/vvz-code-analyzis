"""
MCP command: write_project_text_lines

Replace a range of lines in a non-code text file. Python and other blocked
program-source suffixes are rejected — see ``project_text_file_guard``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Type

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .project_text_file_guard import (
    reject_if_source_code_text_path,
    reject_if_write_under_project_venv,
)
from ..core.backup_manager import BackupManager
from ..core.file_lock import file_lock
from ..core.exceptions import ValidationError
from ..core.database_client.file_data_batch import update_file_data_atomic_batch
from ..core.database_client.objects.base import BaseObject
from ..core.database_client.objects.file import File
from ..core.path_normalization import normalize_path_simple

logger = logging.getLogger(__name__)


class WriteProjectTextLinesCommand(BaseMCPCommand):
    """Replace lines in non-code text files; Python and other source paths are rejected."""

    name = "write_project_text_lines"
    version = "1.0.0"
    descr = (
        "Replaces a line range (1-based) for non-code text files. Python (.py, .pyi, …) and "
        "other blocked program source suffixes are not supported; use CST or line commands "
        "for Python as documented."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "title": "write_project_text_lines",
            "description": (
                "Replace a contiguous line range in a non-code text file. **Python** paths return "
                "`PYTHON_FILE_FORBIDDEN`; other blocked program-source suffixes return "
                "`CODE_FILE_FORBIDDEN`. When backup is true (default), creates a version backup before "
                "overwriting. Updates indexed file metadata after a successful write. Each string in "
                "new_lines is one logical line; lines are joined with '\\n'."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID (from create_project or list_projects). "
                        "Must exist in the database."
                    ),
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Path relative to project root. Must not be Python or other blocked "
                        "program-source suffixes (see error codes)."
                    ),
                    "examples": ["README.md", "config/app.toml", "notes.txt"],
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line (1-based, inclusive)",
                    "minimum": 1,
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line (1-based, inclusive)",
                    "minimum": 1,
                },
                "new_lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Line strings that replace the inclusive range [start_line, end_line]. "
                        "Do not include newline characters inside items; the file is rejoined with '\\n'."
                    ),
                },
                "backup": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "If true (default), create a backup via BackupManager before overwriting; "
                        "failure to backup aborts the command when backup is required."
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
            "examples": [
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "file_path": "README.md",
                    "start_line": 1,
                    "end_line": 1,
                    "new_lines": ["# Title"],
                    "backup": True,
                },
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "file_path": "notes.txt",
                    "start_line": 2,
                    "end_line": 3,
                    "new_lines": ["replaced-a", "replaced-b"],
                },
            ],
        }

    @classmethod
    def metadata(cls: Type["WriteProjectTextLinesCommand"]) -> Dict[str, Any]:
        """Structured discovery/help; JSON parameters remain authoritative in get_schema()."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "For **non-code** paths: replaces lines with optional backup and DB update. "
                "**Python** and other blocked program-source suffixes are rejected (see error "
                "codes).\n\n"
                "Performs optional backup, file write under lock, then updates DB via "
                "update_file_data_atomic_batch.\n\n"
                "An empty file yields EMPTY_FILE. If backup=true and backup creation fails, returns "
                "BACKUP_REQUIRED."
            ),
            "parameters": {
                "project_id": {
                    "description": "Registered project UUID.",
                    "required": True,
                },
                "file_path": {
                    "description": (
                        "Path relative to project root. Python and other blocked source suffixes → error."
                    ),
                    "required": True,
                },
                "start_line": {
                    "description": "Start of range (1-based, inclusive).",
                    "required": True,
                },
                "end_line": {
                    "description": "End of range (1-based, inclusive).",
                    "required": True,
                },
                "new_lines": {
                    "description": "Replacement lines for the range; one string per line, no embedded newlines.",
                    "required": True,
                },
                "backup": {
                    "description": "Create backup before write (default true).",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Replace first line only in README.md",
                    "params": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "README.md",
                        "start_line": 1,
                        "end_line": 1,
                        "new_lines": ["# Title"],
                        "backup": True,
                    },
                },
                {
                    "description": "Replace lines 2–3 in notes.txt (default backup=true)",
                    "params": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "notes.txt",
                        "start_line": 2,
                        "end_line": 3,
                        "new_lines": ["a", "b"],
                    },
                },
            ],
            "error_codes": [
                "PYTHON_FILE_FORBIDDEN",
                "CODE_FILE_FORBIDDEN",
                "INVALID_RANGE",
                "FILE_NOT_FOUND",
                "EMPTY_FILE",
                "BACKUP_REQUIRED",
                "UPDATE_FILE_DATA_ERROR",
                "VALIDATION_ERROR",
                "WRITE_PROJECT_TEXT_LINES_ERROR",
            ],
            "error_codes_note": (
                "PYTHON_FILE_FORBIDDEN: Python source paths — use CST or replace_file_lines as "
                "appropriate. CODE_FILE_FORBIDDEN: other blocked program-source suffixes."
            ),
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        start_line: int,
        end_line: int,
        new_lines: List[str],
        backup: bool = True,
        **kwargs: Any,
    ) -> SuccessResult:
        try:
            blocked = reject_if_source_code_text_path(file_path)
            if blocked is not None:
                return blocked

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

            database = self._open_database_from_config(auto_analyze=False)
            absolute_path = self._resolve_file_path_from_project(
                database, project_id, file_path
            )
            project = database.get_project(project_id)
            if not project:
                return ErrorResult(
                    message=f"Project {project_id} not found",
                    code="PROJECT_NOT_FOUND",
                    details={"project_id": project_id},
                )
            root_dir = Path(project.root_path)

            blocked_venv = reject_if_write_under_project_venv(absolute_path, root_dir)
            if blocked_venv is not None:
                return blocked_venv

            if not absolute_path.exists():
                return ErrorResult(
                    message=f"File not found: {absolute_path}",
                    code="FILE_NOT_FOUND",
                    details={
                        "file_path": file_path,
                        "resolved_path": str(absolute_path),
                    },
                )

            text = absolute_path.read_text(encoding="utf-8", errors="replace")
            all_lines = text.splitlines(keepends=False)
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

            backup_uuid = None
            with file_lock(absolute_path):
                if backup:
                    backup_manager = BackupManager(root_dir)
                    try:
                        rel = str(absolute_path.relative_to(root_dir))
                    except ValueError:
                        rel = str(absolute_path)
                    backup_uuid = backup_manager.create_backup(
                        absolute_path,
                        command="write_project_text_lines",
                        comment=f"Before write_project_text_lines {start_line}-{end_line}",
                    )
                    if not backup_uuid:
                        return ErrorResult(
                            message=(
                                "Backup to old_code (versions) is mandatory before write; "
                                "create_backup failed. Aborting write_project_text_lines."
                            ),
                            code="BACKUP_REQUIRED",
                            details={"file_path": str(absolute_path)},
                        )

                absolute_path.write_text(source_code, encoding="utf-8")

                transaction_id = database.begin_transaction()
                try:
                    normalized_path = normalize_path_simple(str(absolute_path))
                    existing = database.select(
                        "files",
                        where={
                            "path": normalized_path,
                            "project_id": project_id,
                        },
                    )
                    lines_count = len(new_content_lines)
                    stripped = source_code.lstrip()
                    has_docstring = stripped.startswith('"""') or stripped.startswith(
                        "'''"
                    )
                    last_modified = datetime.fromtimestamp(
                        absolute_path.stat().st_mtime
                    )

                    if existing:
                        file_record = existing[0]
                        file_obj = File(
                            id=file_record["id"],
                            project_id=project_id,
                            path=normalized_path,
                            lines=lines_count,
                            last_modified=last_modified,
                            has_docstring=has_docstring,
                        )
                        database.update_file(file_obj)
                        file_id = file_obj.id
                    else:
                        file_obj = File(
                            project_id=project_id,
                            path=normalized_path,
                            lines=lines_count,
                            last_modified=last_modified,
                            has_docstring=has_docstring,
                        )
                        created = database.create_file(file_obj)
                        file_id = created.id

                    file_mtime = BaseObject._to_timestamp(last_modified) or 0.0
                    update_result = update_file_data_atomic_batch(
                        database=database,
                        file_id=file_id,
                        project_id=project_id,
                        source_code=source_code,
                        file_path=str(absolute_path),
                        file_mtime=file_mtime,
                        transaction_id=transaction_id,
                    )
                    database.commit_transaction(transaction_id)

                    if not update_result.get("success"):
                        return ErrorResult(
                            message="Failed to update file data: "
                            + update_result.get("error", "unknown"),
                            code="UPDATE_FILE_DATA_ERROR",
                            details=update_result,
                        )

                    return SuccessResult(
                        data={
                            "success": True,
                            "file_path": str(absolute_path),
                            "file_id": file_id,
                            "backup_uuid": backup_uuid,
                            "start_line": start_line,
                            "end_line": end_line,
                            "replaced_line_count": high - low + 1,
                            "new_line_count": len(new_lines),
                            "update_result": update_result,
                        }
                    )
                except Exception:
                    database.rollback_transaction(transaction_id)
                    if backup_uuid and absolute_path.exists():
                        backup_manager = BackupManager(root_dir)
                        try:
                            rel = str(absolute_path.relative_to(root_dir))
                        except ValueError:
                            rel = str(absolute_path)
                        backup_manager.restore_file(rel, backup_uuid)
                    raise

        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        except Exception as e:
            logger.exception("write_project_text_lines failed: %s", e)
            return ErrorResult(
                message=f"write_project_text_lines failed: {e}",
                code="WRITE_PROJECT_TEXT_LINES_ERROR",
            )
