"""
MCP command: write_project_text_lines

Replace a range of lines in a non-code text file. Python and other blocked
program-source suffixes are rejected — see ``project_text_file_guard``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Type

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .project_text_file_guard import (
    reject_if_source_code_text_path,
    reject_if_write_under_project_venv,
)
from .registration import (
    MCP_FILE_MANAGEMENT_REGISTRY_HELP,
    REGISTRY_SCHEMA_DISCOVERY_SHORT,
)
from ..core.backup_manager import BackupManager
from ..core.git_integration import commit_after_write
from ..core.file_handlers.text_handler import (
    TEXT_SUFFIXES,
    compute_replace_lines_single_range,
    join_lines_unix,
    persist_plain_text_file_metadata,
    validate_write_range,
)
from ..core.file_lock import file_lock
from ..core.exceptions import ValidationError
from ..core.path_normalization import normalize_path_simple

logger = logging.getLogger(__name__)


def _reject_if_not_plain_text_path(file_path: str) -> ErrorResult | None:
    """Return an error when a path is not an allowed plain-text file."""
    suffix = Path(file_path).suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return None
    return ErrorResult(
        message=(
            "write_project_text_lines supports only plain text files "
            f"with suffixes: {', '.join(sorted(TEXT_SUFFIXES))}. "
            "Use JSON/YAML/Python-specific commands for structured or code files."
        ),
        code="TEXT_FILE_SUFFIX_NOT_ALLOWED",
        details={
            "file_path": file_path,
            "suffix": suffix,
            "allowed_suffixes": sorted(TEXT_SUFFIXES),
        },
    )


class WriteProjectTextLinesCommand(BaseMCPCommand):
    """Replace lines in non-code text files; Python and other source paths are rejected."""

    name = "write_project_text_lines"
    version = "1.0.0"
    descr = (
        "Replaces a line range (1-based) for non-code text files. Python (.py, .pyi, …) and "
        "other blocked program source suffixes are not supported; use CST or line commands "
        "for Python as documented." + " " + MCP_FILE_MANAGEMENT_REGISTRY_HELP
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
                "overwriting. Updates the ``files`` table row (line count, mtime) after a successful "
                "write — no Python parse or code-index batch update. Each string in "
                "new_lines is one logical line; lines are joined with '\\n'. "
                + REGISTRY_SCHEMA_DISCOVERY_SHORT
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
                        "Single literal path relative to project root (no globs). Must not be "
                        "Python or other blocked program-source suffixes (see error codes)."
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
                "plain-text-safe ``files`` metadata only.\n\n"
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
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "README.md",
                        "start_line": 1,
                        "end_line": 1,
                        "new_lines": ["# Title"],
                        "backup": True,
                    },
                    "explanation": "Creates backup when backup=true (default).",
                },
                {
                    "description": "Replace lines 2–3 in notes.txt",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "notes.txt",
                        "start_line": 2,
                        "end_line": 3,
                        "new_lines": ["a", "b"],
                    },
                    "explanation": "Python paths are rejected; use CST for .py files.",
                },
            ],
            "return_value": {
                "success": {
                    "description": "File updated on disk and DB metadata refreshed.",
                    "example": {"success": True, "file_path": "README.md"},
                },
                "error": {
                    "description": "Validation, backup, or write failure.",
                    "code": "PYTHON_FILE_FORBIDDEN | BACKUP_REQUIRED | …",
                },
            },
            "error_cases": {
                "PYTHON_FILE_FORBIDDEN": {
                    "description": "Target is a .py file.",
                    "solution": "Use cst_modify_tree / cst_save_tree instead.",
                },
                "BACKUP_REQUIRED": {
                    "description": "backup=true but backup failed.",
                    "solution": "Fix old_code permissions or set backup=false if allowed.",
                },
            },
            "best_practices": [
                "Use line ranges inclusive (1-based).",
                "Do not embed newline characters inside new_lines items.",
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

            plain_text_error = _reject_if_not_plain_text_path(file_path)
            if plain_text_error is not None:
                return plain_text_error

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

            try:
                validate_write_range(start_line, end_line, total)
            except ValueError as e:
                return ErrorResult(
                    message=str(e),
                    code="INVALID_RANGE",
                    details={
                        "start_line": start_line,
                        "end_line": end_line,
                        "file_path": file_path,
                        "error": str(e),
                    },
                )

            try:
                new_content_lines = compute_replace_lines_single_range(
                    all_lines,
                    start_line,
                    end_line,
                    new_lines,
                )
            except ValueError as e:
                return ErrorResult(
                    message=str(e),
                    code="INVALID_RANGE",
                    details={
                        "start_line": start_line,
                        "end_line": end_line,
                        "file_path": file_path,
                        "error": str(e),
                    },
                )
            source_code = join_lines_unix(new_content_lines)

            backup_uuid = None
            normalized_for_lock = normalize_path_simple(str(absolute_path))

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
                        comment=(
                            f"Before write_project_text_lines "
                            f"{start_line}-{end_line}"
                        ),
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

                def _restore_file_from_backup() -> None:
                    if not backup_uuid or not absolute_path.exists():
                        return
                    backup_manager = BackupManager(root_dir)
                    try:
                        rel = str(absolute_path.relative_to(root_dir))
                    except ValueError:
                        rel = str(absolute_path)
                    backup_manager.restore_file(rel, backup_uuid)

                try:
                    meta_result = persist_plain_text_file_metadata(
                        database=database,
                        project_id=project_id,
                        absolute_path=absolute_path,
                        normalized_path=normalized_for_lock,
                        source_code=source_code,
                    )

                    if not meta_result.get("success"):
                        _restore_file_from_backup()
                        return ErrorResult(
                            message="Failed to update file metadata: "
                            + str(meta_result.get("error", "unknown")),
                            code="UPDATE_FILE_DATA_ERROR",
                            details=meta_result,
                        )

                    file_id = meta_result.get("file_id")

                    git_ok, git_err = commit_after_write(
                        root_dir.resolve(),
                        [absolute_path],
                        "write_project_text_lines",
                        commit_message_override=None,
                        config_data=BaseMCPCommand._get_raw_config(),
                    )
                    if not git_ok and git_err:
                        logger.warning(
                            "Git commit after write_project_text_lines: %s", git_err
                        )

                    return SuccessResult(
                        data={
                            "success": True,
                            "file_path": str(absolute_path),
                            "file_id": file_id,
                            "backup_uuid": backup_uuid,
                            "start_line": start_line,
                            "end_line": end_line,
                            "replaced_line_count": end_line - start_line + 1,
                            "new_line_count": len(new_lines),
                            "metadata_update": meta_result,
                        }
                    )
                except Exception:
                    _restore_file_from_backup()
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
