"""
MCP command: replace_file_lines

Replace a range of lines in a file (for fixing syntax errors without full CST parse).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.backup_manager import BackupManager
from ..core.file_lock import file_lock
from ..core.exceptions import ValidationError
from ..database_client.file_data_batch import update_file_data_atomic_batch
from ..database_client.objects.base import BaseObject
from ..database_client.objects.file import File
from ..path_normalization import normalize_path_simple

logger = logging.getLogger(__name__)


class ReplaceFileLinesCommand(BaseMCPCommand):
    """Replace a range of lines in a project file; backup and update DB."""

    name = "replace_file_lines"
    version = "1.0.0"
    descr = (
        "Replace a range of lines in a file (1-based). Use to fix syntax errors "
        "when cst_load_file fails. Creates backup and updates indexes."
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

            # 0-based indices; clamp to file range
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
                        command="replace_file_lines",
                        comment=f"Before replace_file_lines {start_line}-{end_line}",
                    )
                    if not backup_uuid:
                        logger.warning("Failed to create backup, continuing anyway")

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
            logger.exception("replace_file_lines failed: %s", e)
            return ErrorResult(
                message=f"replace_file_lines failed: {e}",
                code="REPLACE_FILE_LINES_ERROR",
            )
