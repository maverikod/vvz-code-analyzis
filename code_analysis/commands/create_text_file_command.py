"""
MCP command: create_text_file

Legacy plain-text creation aligned with universal save ordering: registry
validation and source guards before mkdir, backup, write, DB, or indexing.
Only documented plain-text suffixes routed to the text handler (.md/.txt/.rst/.adoc).
JSON/YAML/Python use universal_file_save or CST — not this command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Type

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .project_text_file_guard import (
    reject_if_source_code_text_path,
    reject_if_write_under_project_venv,
)
from ..core.backup_manager import BackupManager
from ..core.git_integration import commit_after_write
from ..core.exceptions import ValidationError
from ..core.file_handlers.registry import (
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
    HANDLER_YAML,
    RegistryError,
    resolve_handler,
)
from ..core.file_handlers.text_handler import persist_plain_text_file_metadata
from ..core.file_lock import file_lock
from ..core.path_normalization import normalize_path_simple

logger = logging.getLogger(__name__)


def _reject_if_not_plain_text_handler(
    *, handler_id: str, file_path: str
) -> ErrorResult:
    """When registry maps to structured/code handlers — must use universal save / CST."""
    if handler_id == HANDLER_JSON:
        return ErrorResult(
            message=(
                "create_text_file is only for configured plain-text files (.md, .txt, "
                ".rst, .adoc). To create JSON files, use universal_file_save with parseable JSON "
                "content."
            ),
            code="JSON_CREATE_USE_UNIVERSAL_FILE_SAVE",
            details={
                "file_path": file_path,
                "handler_id": HANDLER_JSON,
                "use_command": "universal_file_save",
            },
        )
    if handler_id == HANDLER_YAML:
        return ErrorResult(
            message=(
                "create_text_file is only for configured plain-text files (.md, .txt, "
                ".rst, .adoc). To create YAML files, use universal_file_save with YAML content."
            ),
            code="YAML_CREATE_USE_UNIVERSAL_FILE_SAVE",
            details={
                "file_path": file_path,
                "handler_id": HANDLER_YAML,
                "use_command": "universal_file_save",
            },
        )
    if handler_id == HANDLER_PYTHON:
        return ErrorResult(
            message=(
                "Python source files cannot be created with create_text_file; use "
                "cst_create_file, universal_file_save, or other CST/Python "
                "commands instead."
            ),
            code="PYTHON_FILE_FORBIDDEN",
            details={
                "file_path": file_path,
                "handler_id": HANDLER_PYTHON,
                "reason": "legacy_text_create_blocked",
            },
        )
    return ErrorResult(
        message=(
            f"create_text_file received unexpected registry handler after validation: "
            f"{handler_id!r}"
        ),
        code="INTERNAL_ERROR",
        details={"file_path": file_path, "handler_id": handler_id},
    )


class CreateTextFileMCPCommand(BaseMCPCommand):
    """Create a new plain-text file; registry + guards run before mkdir/backup/write/DB."""

    name = "create_text_file"
    version = "1.1.0"
    descr = (
        "Create a new plain-text file in project root (.md/.txt/.rst/.adoc only). "
        "JSON/YAML/Python require universal_file_save or CST commands. Validates before "
        "creating directories or files; optional backup when overwriting."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID.",
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Single literal relative file path inside the project (no wildcards; "
                        "plain-text suffix only: .md / .txt / .rst / .adoc)."
                    ),
                },
                "content": {
                    "type": "string",
                    "default": "",
                    "description": "Initial text content to write to the file.",
                },
                "create_dirs": {
                    "type": "boolean",
                    "default": True,
                    "description": "Create parent directories if they do not exist.",
                },
                "overwrite": {
                    "type": "boolean",
                    "default": False,
                    "description": "Overwrite the file if it already exists.",
                },
                "encoding": {
                    "type": "string",
                    "default": "utf-8",
                    "description": "Text encoding used when writing the file.",
                },
                "backup": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "If true (default), create BackupManager snapshot before overwriting "
                        "an existing file."
                    ),
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["CreateTextFileMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The create_text_file command creates a single plain-text documentation file "
                "using suffixes routed to HANDLER_TEXT only (see registry).\n\n"
                "Ordering (fail-fast):\n"
                "1. Path shape checks (relative, no traversal).\n"
                "2. project_text_file_guard (Python / blocked program-source paths).\n"
                '3. resolve_handler(..., "save") — must yield the text handler; JSON/YAML/Python '
                "return handler-specific guidance to use universal_file_save/CST.\n"
                "4. Open DB and resolve absolute path.\n"
                "5. Reject writes under project-local .venv.\n"
                "6. Optional mkdir; existing directory target → error.\n"
                "7. File lock → optional backup → write → persist_plain_text_file_metadata "
                "(files row only; no AST/CST/entity indexing).\n"
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID the file belongs to.",
                    "type": "string",
                    "required": True,
                },
                "file_path": {
                    "description": (
                        "Path relative to project root; suffix must map to HANDLER_TEXT."
                    ),
                    "type": "string",
                    "required": True,
                },
                "content": {
                    "description": "Initial content to write; defaults to empty string.",
                    "type": "string",
                    "required": False,
                    "default": "",
                },
                "create_dirs": {
                    "description": "Create missing parent directories when true.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "overwrite": {
                    "description": "Allow overwrite when target file already exists.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "encoding": {
                    "description": "Text encoding used for write operation.",
                    "type": "string",
                    "required": False,
                    "default": "utf-8",
                },
                "backup": {
                    "description": "Backup existing file via BackupManager before overwrite.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
            },
            "usage_examples": [
                {
                    "description": "Create empty README.md",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "README.md",
                    },
                },
                {
                    "description": "Create nested Markdown with parents",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "docs/a/note.md",
                        "content": "# Title\n",
                        "create_dirs": True,
                    },
                },
                {
                    "description": "Overwrite existing",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "notes.txt",
                        "content": "new content",
                        "overwrite": True,
                    },
                },
            ],
            "error_codes": (
                "PYTHON_FILE_FORBIDDEN | CODE_FILE_FORBIDDEN | UNSUPPORTED_FILE_EXTENSION | "
                "UNSUPPORTED_FILE_OPERATION | JSON_CREATE_USE_UNIVERSAL_FILE_SAVE | "
                "YAML_CREATE_USE_UNIVERSAL_FILE_SAVE | INVALID_FILE_PATH | DIRECTORY_NOT_FOUND | "
                "FILE_ALREADY_EXISTS | PATH_IS_DIRECTORY | PERMISSION_ERROR | BACKUP_REQUIRED | "
                "UPDATE_FILE_DATA_ERROR | PROJECT_NOT_FOUND | PROJECT_VENV_WRITE_FORBIDDEN | "
                "CREATE_TEXT_FILE_ERROR | VALIDATION_ERROR"
            ),
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        content: str = "",
        create_dirs: bool = True,
        overwrite: bool = False,
        encoding: str = "utf-8",
        backup: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Create or overwrite a plain-text file safely; metadata via text-safe pipeline only."""
        try:
            raw_path = (file_path or "").strip()
            if not raw_path:
                return ErrorResult(
                    code="INVALID_FILE_PATH",
                    message="file_path must be a non-empty relative path.",
                )

            rel_path = Path(raw_path)
            if rel_path.is_absolute():
                return ErrorResult(
                    code="INVALID_FILE_PATH",
                    message="Absolute file_path is not allowed. Use project-relative path.",
                )
            if any(part == ".." for part in rel_path.parts):
                return ErrorResult(
                    code="INVALID_FILE_PATH",
                    message="Path traversal is not allowed in file_path.",
                )
            if rel_path.name in {"", ".", ".."}:
                return ErrorResult(
                    code="INVALID_FILE_PATH",
                    message="file_path must point to a file path, not project root.",
                )

            structured = reject_if_source_code_text_path(raw_path)
            if structured is not None:
                return structured

            try:
                handler_id = resolve_handler(raw_path, "save")
            except RegistryError as e:
                return ErrorResult(
                    message=str(e),
                    code=e.code,
                    details=e.details,
                )

            if handler_id != HANDLER_TEXT:
                return _reject_if_not_plain_text_handler(
                    handler_id=handler_id,
                    file_path=raw_path,
                )

            database = self._open_database_from_config(auto_analyze=False)

            absolute_path = self._resolve_file_path_from_project(
                database,
                project_id,
                raw_path,
                require_exists=False,
            )
            project = database.get_project(project_id)
            if not project:
                return ErrorResult(
                    message=f"Project {project_id} not found",
                    code="PROJECT_NOT_FOUND",
                    details={"project_id": project_id},
                )
            root_dir = Path(project.root_path).resolve()

            blocked_venv = reject_if_write_under_project_venv(absolute_path, root_dir)
            if blocked_venv is not None:
                return blocked_venv

            parent_dir = absolute_path.parent
            parent_created = False
            if not parent_dir.exists():
                if not create_dirs:
                    return ErrorResult(
                        code="DIRECTORY_NOT_FOUND",
                        message=(
                            "Parent directory does not exist and create_dirs is false: "
                            f"{parent_dir}"
                        ),
                    )
                try:
                    parent_dir.mkdir(parents=True, exist_ok=True)
                    parent_created = True
                except PermissionError as e:
                    return ErrorResult(
                        code="PERMISSION_ERROR",
                        message=f"Permission denied while creating parent directory: {e}",
                    )

            if absolute_path.exists() and absolute_path.is_dir():
                return ErrorResult(
                    code="PATH_IS_DIRECTORY",
                    message=f"Target path is a directory: {absolute_path}",
                )

            target_exists_before = absolute_path.exists()
            if target_exists_before and not overwrite:
                return ErrorResult(
                    code="FILE_ALREADY_EXISTS",
                    message=f"File already exists: {absolute_path}",
                )

            text_content = content if content is not None else ""
            try:
                payload = text_content.encode(encoding)
            except (LookupError, UnicodeEncodeError, ValueError) as e:
                return ErrorResult(
                    code="CREATE_TEXT_FILE_ERROR",
                    message=(f"Cannot encode content with encoding={encoding!r}: {e}"),
                    details={"encoding": encoding},
                )

            backup_uuid: Optional[str] = None

            with file_lock(absolute_path):
                if backup and absolute_path.exists() and overwrite:
                    bm = BackupManager(root_dir)
                    try:
                        rel_b = str(absolute_path.relative_to(root_dir))
                    except ValueError:
                        rel_b = str(absolute_path)
                    backup_uuid = bm.create_backup(
                        absolute_path,
                        command="create_text_file",
                        comment=f"Before create_text_file overwrite {raw_path}",
                    )
                    if not backup_uuid:
                        return ErrorResult(
                            message=(
                                "Backup to old_code (versions) is mandatory before overwrite; "
                                "create_backup failed. Aborting create_text_file."
                            ),
                            code="BACKUP_REQUIRED",
                            details={
                                "file_path": raw_path,
                                "resolved_path": str(absolute_path),
                            },
                        )

                try:
                    absolute_path.write_bytes(payload)
                except PermissionError as e:
                    return ErrorResult(
                        code="PERMISSION_ERROR",
                        message=f"Permission denied while writing file: {e}",
                    )

                source_for_meta = absolute_path.read_text(
                    encoding=encoding,
                    errors="replace",
                )
                normalized_path = normalize_path_simple(str(absolute_path))
                meta = persist_plain_text_file_metadata(
                    database=database,
                    project_id=project_id,
                    absolute_path=absolute_path,
                    normalized_path=normalized_path,
                    source_code=source_for_meta,
                )
                if not meta.get("success"):

                    def _restore(rel: str, uuid_: str) -> None:
                        bm_r = BackupManager(root_dir)
                        bm_r.restore_file(rel, uuid_)

                    if backup_uuid:
                        try:
                            rel_rb = str(absolute_path.relative_to(root_dir.resolve()))
                        except ValueError:
                            rel_rb = str(absolute_path)
                        try:
                            _restore(rel_rb, backup_uuid)
                        except Exception:
                            logger.exception(
                                "create_text_file rollback after metadata failure"
                            )

                    return ErrorResult(
                        message="Failed to update file metadata: "
                        + str(meta.get("error", "unknown")),
                        code="UPDATE_FILE_DATA_ERROR",
                        details=meta,
                    )

            rel_posix = absolute_path.relative_to(root_dir).as_posix()
            target_exists_after = absolute_path.exists()
            overwritten = target_exists_before and overwrite
            created = not target_exists_before and target_exists_after

            payload_out = {
                "success": True,
                "project_id": project_id,
                "file_path": rel_posix,
                "absolute_path": str(absolute_path),
                "created": created,
                "overwritten": overwritten,
                "bytes_written": len(payload),
                "encoding": encoding,
                "parent_created": parent_created,
                "metadata_update": meta,
            }
            if backup_uuid:
                payload_out["backup_uuid"] = backup_uuid
            git_ok, git_err = commit_after_write(
                root_dir.resolve(),
                [absolute_path],
                "create_text_file",
                commit_message_override=None,
                config_data=BaseMCPCommand._get_raw_config(),
            )
            if not git_ok and git_err:
                logger.warning("Git commit after create_text_file: %s", git_err)
            return SuccessResult(data=payload_out)

        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        except Exception as e:
            return self._handle_error(e, "CREATE_TEXT_FILE_ERROR", "create_text_file")
