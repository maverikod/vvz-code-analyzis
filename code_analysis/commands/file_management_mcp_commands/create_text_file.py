"""
MCP command wrappers for file management operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..project_text_file_guard import reject_if_write_under_project_venv


class CreateTextFileMCPCommand(BaseMCPCommand):
    """Create a new text file inside an existing project with safe path checks."""

    name = "create_text_file"
    version = "1.0.0"
    descr = (
        "Create a new text file in project root (optionally create parents); can "
        "overwrite existing file when overwrite=true."
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
                    "description": "Relative file path inside the project.",
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
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["CreateTextFileMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The create_text_file command creates a text file inside an existing project "
                "using a strictly validated project-relative path.\n\n"
                "Operation flow:\n"
                "1. Resolves project root by project_id\n"
                "2. Validates file_path is relative and does not contain traversal\n"
                "3. Resolves target path and verifies containment in project root\n"
                "4. Rejects writes into project local virtual environment\n"
                "5. Optionally creates missing parent directories\n"
                "6. Handles existing target according to overwrite flag\n"
                "7. Writes content with requested encoding\n"
                "8. Returns write statistics and effective flags\n\n"
                "Safety notes:\n"
                "- Absolute paths are rejected\n"
                "- '..' traversal segments are rejected\n"
                "- Resolved path must remain inside project root\n"
                "- Directory targets are rejected\n"
                "- Existing files require overwrite=true\n\n"
                "Database/indexing note:\n"
                "- This command creates the file on disk only. Index/DB sync is handled by "
                "existing watcher/indexing flow."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID the file belongs to.",
                    "type": "string",
                    "required": True,
                },
                "file_path": {
                    "description": "Path relative to project root where the file will be created.",
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
            },
            "usage_examples": [
                {
                    "description": "Create empty file in project root",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "notes.txt",
                    },
                    "explanation": "Creates notes.txt with empty content.",
                },
                {
                    "description": "Create nested file with auto parent directories",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "notes/a/b/sample.txt",
                        "content": "alpha\nbeta\n",
                        "create_dirs": True,
                    },
                    "explanation": "Creates missing notes/a/b and writes provided content.",
                },
                {
                    "description": "Overwrite existing file",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "notes/sample.txt",
                        "content": "new content",
                        "overwrite": True,
                    },
                    "explanation": "Replaces existing file content in-place.",
                },
            ],
            "error_cases": {
                "INVALID_PROJECT_ID": {
                    "description": "Project is missing or not found.",
                },
                "INVALID_FILE_PATH": {
                    "description": "Absolute path, traversal, or path outside project root.",
                },
                "DIRECTORY_NOT_FOUND": {
                    "description": "Parent directory is missing while create_dirs=false.",
                },
                "FILE_ALREADY_EXISTS": {
                    "description": "Target file already exists and overwrite=false.",
                },
                "PATH_IS_DIRECTORY": {
                    "description": "Target path exists and is a directory.",
                },
                "PERMISSION_ERROR": {
                    "description": "Insufficient filesystem permissions for mkdir/write.",
                },
                "CREATE_TEXT_FILE_ERROR": {
                    "description": "Unhandled command error.",
                },
            },
            "return_value": {
                "success": {
                    "description": "File was created or overwritten successfully.",
                    "data": {
                        "success": "Always True on success",
                        "project_id": "Echo of request project_id",
                        "file_path": "Normalized relative path in project",
                        "absolute_path": "Resolved absolute path on disk",
                        "created": "True when target file did not exist before write",
                        "overwritten": "True when existing file was replaced",
                        "bytes_written": "Number of bytes written to disk",
                        "encoding": "Encoding used for write",
                        "parent_created": "True when parent directories were created",
                    },
                },
                "error": {
                    "description": "Command failed with a specific error code.",
                    "code": (
                        "INVALID_PROJECT_ID | INVALID_FILE_PATH | DIRECTORY_NOT_FOUND | "
                        "FILE_ALREADY_EXISTS | PATH_IS_DIRECTORY | PERMISSION_ERROR | "
                        "CREATE_TEXT_FILE_ERROR"
                    ),
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Pass project-relative file_path only.",
                "Use create_dirs=true for nested paths.",
                "Keep overwrite=false by default to avoid accidental replacement.",
                "Use read_project_text_file after creation to verify content.",
            ],
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        content: str = "",
        create_dirs: bool = True,
        overwrite: bool = False,
        encoding: str = "utf-8",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Create a text file safely inside the resolved project root."""
        try:
            try:
                project_root = self._resolve_project_root(project_id).resolve()
            except Exception:
                return ErrorResult(
                    code="INVALID_PROJECT_ID",
                    message=f"Project with ID {project_id!r} is invalid or not found.",
                )

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

            target_path = (project_root / rel_path).resolve()
            try:
                target_path.relative_to(project_root)
            except ValueError:
                return ErrorResult(
                    code="INVALID_FILE_PATH",
                    message="Resolved path escapes project root.",
                )

            blocked_venv = reject_if_write_under_project_venv(target_path, project_root)
            if blocked_venv is not None:
                return blocked_venv

            parent_dir = target_path.parent
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

            if target_path.exists() and target_path.is_dir():
                return ErrorResult(
                    code="PATH_IS_DIRECTORY",
                    message=f"Target path is a directory: {target_path}",
                )

            target_exists = target_path.exists()
            if target_exists and not overwrite:
                return ErrorResult(
                    code="FILE_ALREADY_EXISTS",
                    message=f"File already exists: {target_path}",
                )

            text_content = content if content is not None else ""
            try:
                payload = text_content.encode(encoding)
            except Exception as e:
                return ErrorResult(
                    code="CREATE_TEXT_FILE_ERROR",
                    message=f"Failed to encode content with encoding={encoding!r}: {e}",
                )

            try:
                target_path.write_bytes(payload)
            except PermissionError as e:
                return ErrorResult(
                    code="PERMISSION_ERROR",
                    message=f"Permission denied while writing file: {e}",
                )

            rel_posix = target_path.relative_to(project_root).as_posix()
            return SuccessResult(
                data={
                    "success": True,
                    "project_id": project_id,
                    "file_path": rel_posix,
                    "absolute_path": str(target_path),
                    "created": not target_exists,
                    "overwritten": bool(target_exists and overwrite),
                    "bytes_written": len(payload),
                    "encoding": encoding,
                    "parent_created": parent_created,
                }
            )
        except Exception as e:
            return self._handle_error(e, "CREATE_TEXT_FILE_ERROR", "create_text_file")
