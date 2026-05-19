"""
MCP commands: fs_copy, fs_move, fs_remove

Filesystem copy/move/delete under project root (no code-index updates).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .base_mcp_command_resolve_path import resolve_under_project_root
from .project_text_file_guard import reject_if_write_under_project_venv
from ..core.backup_manager import BackupManager
from ..core.exceptions import ValidationError
from ..core.file_write_history import file_lock_many
from ..core.git_integration import commit_after_write

logger = logging.getLogger(__name__)


def _rel_under(root: Path, p: Path) -> str:
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


class FsCopyCommand(BaseMCPCommand):
    name = "fs_copy"
    version = "1.0.0"
    descr = (
        "Copy a file within the project (``cp``). Uses version history (backup before "
        "overwrite) and optional git commit when ``git_commit_on_write`` is enabled. "
        "Does not update the code index; run update_indexes or rely on the file watcher."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID."},
                "source_path": {
                    "type": "string",
                    "description": "Source file path relative to project root.",
                },
                "dest_path": {
                    "type": "string",
                    "description": "Destination file path relative to project root.",
                },
                "overwrite": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, replace existing destination file (with backup when backup=true).",
                },
                "backup": {
                    "type": "boolean",
                    "default": True,
                    "description": "When overwriting, backup existing destination via BackupManager.",
                },
            },
            "required": ["project_id", "source_path", "dest_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        source_path: str,
        dest_path: str,
        overwrite: bool = False,
        backup: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        try:
            root = self._resolve_project_root(project_id).resolve()
            try:
                src = resolve_under_project_root(
                    root, source_path, require_exists=True, must_be_file=True
                )
                dst = resolve_under_project_root(
                    root, dest_path, require_exists=False, must_be_file=None
                )
            except ValidationError as e:
                return ErrorResult(
                    message=str(e),
                    code="VALIDATION_ERROR",
                    details=getattr(e, "details", None) or {},
                )

            blocked = reject_if_write_under_project_venv(src, root)
            if blocked:
                return blocked
            blocked = reject_if_write_under_project_venv(dst, root)
            if blocked:
                return blocked

            if dst.exists() and dst.is_dir():
                return ErrorResult(
                    message=f"Destination is a directory: {dst}",
                    code="IS_DIRECTORY",
                    details={"dest_path": dest_path},
                )
            if dst.exists() and not overwrite:
                return ErrorResult(
                    message=f"Destination exists: {dst}",
                    code="DEST_EXISTS",
                    details={"dest_path": dest_path},
                )

            backup_uuid: Optional[str] = None
            bm = BackupManager(root)
            with file_lock_many([src, dst]):
                if dst.exists() and overwrite and backup:
                    backup_uuid = bm.create_backup(
                        dst, command="fs_copy", comment="Before fs_copy overwrite"
                    )
                    if not backup_uuid:
                        return ErrorResult(
                            message="Backup required before overwrite; create_backup failed.",
                            code="BACKUP_REQUIRED",
                            details={"dest_path": str(dst)},
                        )

                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

            git_ok, git_err = commit_after_write(
                root,
                [dst],
                "fs_copy",
                commit_message_override=None,
                config_data=BaseMCPCommand._get_raw_config(),
            )
            if not git_ok and git_err:
                logger.warning("Git commit after fs_copy: %s", git_err)

            return SuccessResult(
                data={
                    "success": True,
                    "source_path": _rel_under(root, src),
                    "dest_path": _rel_under(root, dst),
                    "dest_backup_uuid": backup_uuid,
                }
            )
        except Exception as e:
            return self._handle_error(e, "FS_COPY_ERROR", "fs_copy")

    @classmethod
    def metadata(cls: type["FsCopyCommand"]) -> Dict[str, Any]:
        from .command_metadata_helpers import (
            build_command_metadata,
            parameters_from_schema,
            project_file_error_cases,
            simple_success_return,
        )

        return build_command_metadata(
            cls,
            detailed_description=cls.descr,
            parameters=parameters_from_schema(cls.get_schema()),
            usage_examples=[
                {
                    "description": "Copy within project",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "source_path": "src/a.py",
                        "dest_path": "src/a_copy.py",
                    },
                    "explanation": "Optional backup of destination when overwriting.",
                },
            ],
            error_cases=project_file_error_cases(),
            return_value=simple_success_return(
                data_fields={"source_path": "Relative path", "dest_path": "Relative path"},
            ),
            best_practices=[
                "Paths must stay inside the project root.",
                "Run update_indexes after copy if indexes must reflect new file.",
            ],
        )


class FsMoveCommand(BaseMCPCommand):
    name = "fs_move"
    version = "1.0.0"
    descr = (
        "Move/rename a file within the project (``mv``). Records history: backs up the "
        "source file (and the destination when overwriting). Optional git commit stages "
        "both old and new paths when ``git_commit_on_write`` is enabled. "
        "Does not update DB file rows; run update_indexes or rely on the watcher."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID."},
                "source_path": {
                    "type": "string",
                    "description": "Source file path relative to project root.",
                },
                "dest_path": {
                    "type": "string",
                    "description": "Destination file path relative to project root.",
                },
                "overwrite": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, replace existing destination (with backup when backup=true).",
                },
                "backup": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true: backup the source path before the move (history at old "
                        "location), and if the destination file exists and overwrite is true, "
                        "backup the destination before replace."
                    ),
                },
            },
            "required": ["project_id", "source_path", "dest_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        source_path: str,
        dest_path: str,
        overwrite: bool = False,
        backup: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        try:
            root = self._resolve_project_root(project_id).resolve()
            try:
                src = resolve_under_project_root(
                    root, source_path, require_exists=True, must_be_file=True
                )
                dst = resolve_under_project_root(
                    root, dest_path, require_exists=False, must_be_file=None
                )
            except ValidationError as e:
                return ErrorResult(
                    message=str(e),
                    code="VALIDATION_ERROR",
                    details=getattr(e, "details", None) or {},
                )

            blocked = reject_if_write_under_project_venv(src, root)
            if blocked:
                return blocked
            blocked = reject_if_write_under_project_venv(dst, root)
            if blocked:
                return blocked

            if src.resolve() == dst.resolve():
                return ErrorResult(
                    message="Source and destination are the same path.",
                    code="SAME_PATH",
                    details={},
                )

            if dst.exists() and dst.is_dir():
                return ErrorResult(
                    message=f"Destination is a directory: {dst}",
                    code="IS_DIRECTORY",
                    details={"dest_path": dest_path},
                )
            if dst.exists() and not overwrite:
                return ErrorResult(
                    message=f"Destination exists: {dst}",
                    code="DEST_EXISTS",
                    details={"dest_path": dest_path},
                )

            dest_backup_uuid: Optional[str] = None
            src_backup_uuid: Optional[str] = None
            bm = BackupManager(root)
            rel_src = _rel_under(root, src)
            rel_dst = _rel_under(root, dst)

            with file_lock_many([src, dst]):
                if dst.exists() and overwrite and backup:
                    dest_backup_uuid = bm.create_backup(
                        dst,
                        command="fs_move",
                        comment="Before fs_move overwrite destination",
                    )
                    if not dest_backup_uuid:
                        return ErrorResult(
                            message="Backup required before overwrite; create_backup failed.",
                            code="BACKUP_REQUIRED",
                            details={"dest_path": str(dst)},
                        )

                if backup:
                    src_backup_uuid = bm.create_backup(
                        src,
                        command="fs_move",
                        comment="Before fs_move (source path)",
                    )
                    if not src_backup_uuid:
                        return ErrorResult(
                            message=(
                                "Backup of source before move is required when backup=true; "
                                "create_backup failed."
                            ),
                            code="BACKUP_REQUIRED",
                            details={"source_path": source_path},
                        )

                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))

            git_ok, git_err = commit_after_write(
                root,
                [root / rel_src, root / rel_dst],
                "fs_move",
                commit_message_override=None,
                config_data=BaseMCPCommand._get_raw_config(),
            )
            if not git_ok and git_err:
                logger.warning("Git commit after fs_move: %s", git_err)

            return SuccessResult(
                data={
                    "success": True,
                    "dest_path": rel_dst,
                    "source_backup_uuid": src_backup_uuid,
                    "dest_backup_uuid": dest_backup_uuid,
                }
            )
        except Exception as e:
            return self._handle_error(e, "FS_MOVE_ERROR", "fs_move")

    @classmethod
    def metadata(cls: type["FsMoveCommand"]) -> Dict[str, Any]:
        from .command_metadata_helpers import (
            build_command_metadata,
            parameters_from_schema,
            project_file_error_cases,
            simple_success_return,
        )

        return build_command_metadata(
            cls,
            detailed_description=cls.descr,
            parameters=parameters_from_schema(cls.get_schema()),
            usage_examples=[
                {
                    "description": "Rename within project",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "source_path": "src/old.py",
                        "dest_path": "src/new.py",
                    },
                    "explanation": "Backs up source (and destination when overwriting).",
                },
            ],
            error_cases=project_file_error_cases(),
            return_value=simple_success_return(
                data_fields={"source_path": "Relative path", "dest_path": "Relative path"},
            ),
            best_practices=["Does not update DB file rows; run update_indexes if needed."],
        )


class FsRemoveCommand(BaseMCPCommand):
    name = "fs_remove"
    version = "1.0.0"
    descr = (
        "Remove a file under the project root (``rm`` file). Backs up to old_code before "
        "unlink (when backup=true); optional git commit when ``git_commit_on_write`` is enabled. "
        "Does not touch DB rows — use repair_database / update_indexes as needed. "
        "For recycle-bin semantics use delete_file."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID."},
                "file_path": {
                    "type": "string",
                    "description": "File path relative to project root (files only).",
                },
                "backup": {
                    "type": "boolean",
                    "default": True,
                    "description": "Backup to old_code before unlink.",
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        backup: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        try:
            root = self._resolve_project_root(project_id).resolve()
            try:
                target = resolve_under_project_root(
                    root, file_path, require_exists=True, must_be_file=True
                )
            except ValidationError as e:
                return ErrorResult(
                    message=str(e),
                    code="VALIDATION_ERROR",
                    details=getattr(e, "details", None) or {},
                )

            blocked = reject_if_write_under_project_venv(target, root)
            if blocked:
                return blocked

            backup_uuid: Optional[str] = None
            bm = BackupManager(root)
            with file_lock_many([target]):
                if backup:
                    backup_uuid = bm.create_backup(
                        target, command="fs_remove", comment="Before fs_remove"
                    )
                    if not backup_uuid:
                        return ErrorResult(
                            message="Backup required before remove; create_backup failed.",
                            code="BACKUP_REQUIRED",
                            details={"file_path": file_path},
                        )

                target.unlink()

            git_ok, git_err = commit_after_write(
                root,
                [target],
                "fs_remove",
                commit_message_override=None,
                config_data=BaseMCPCommand._get_raw_config(),
            )
            if not git_ok and git_err:
                logger.warning("Git commit after fs_remove: %s", git_err)

            return SuccessResult(
                data={
                    "success": True,
                    "removed_path": _rel_under(root, target),
                    "backup_uuid": backup_uuid,
                }
            )
        except Exception as e:
            return self._handle_error(e, "FS_REMOVE_ERROR", "fs_remove")

    @classmethod
    def metadata(cls: type["FsRemoveCommand"]) -> Dict[str, Any]:
        from .command_metadata_helpers import (
            build_command_metadata,
            parameters_from_schema,
            project_file_error_cases,
            simple_success_return,
        )

        return build_command_metadata(
            cls,
            detailed_description=cls.descr,
            parameters=parameters_from_schema(cls.get_schema()),
            usage_examples=[
                {
                    "description": "Remove a file",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "tmp/scratch.txt",
                    },
                    "explanation": "Optional backup before delete when backup=true.",
                },
            ],
            error_cases=project_file_error_cases(),
            return_value=simple_success_return(),
            best_practices=["Prefer soft-delete commands when audit trail is required."],
        )
