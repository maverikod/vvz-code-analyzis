"""
Text save handler for universal_file_save command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..core.backup_manager import BackupManager
from ..core.file_handlers.base import FileHandlerRequest, FileHandlerResult
from ..core.file_handlers.text_handler import (
    TextFileHandler,
    persist_plain_text_file_metadata,
)
from ..core.file_lock import file_lock
from ..core.path_normalization import normalize_path_simple


def run_text_save(
    *,
    req: FileHandlerRequest,
    database: Any,
    absolute_path: Path,
    root_dir: Path,
    backup: bool,
    dry_run: bool,
) -> FileHandlerResult:
    """Text save with BackupManager (handler does not) and files-table metadata.

    Args:
        req: File handler request.
        database: Database connection.
        absolute_path: Resolved absolute path to file.
        root_dir: Project root directory.
        backup: Whether to create backup before write.
        dry_run: If True, no write or side effects.

    Returns:
        FileHandlerResult with save outcome.
    """

    def _restore(rel: str, uuid_: str) -> None:
        bm = BackupManager(root_dir)
        bm.restore_file(rel, uuid_)

    with file_lock(
        absolute_path,
        mode="full",
        database=database,
        project_id=req.project_id,
        file_path=req.file_path,
    ):
        normalized_path = normalize_path_simple(str(absolute_path))

        backup_uuid: Optional[str] = None
        if not dry_run and backup and absolute_path.exists():
            bm = BackupManager(root_dir)
            try:
                rel = str(absolute_path.relative_to(root_dir.resolve()))
            except ValueError:
                rel = str(absolute_path)
            backup_uuid = bm.create_backup(
                absolute_path,
                command="universal_file_save",
                comment=f"Before universal_file_save {req.file_path}",
            )
            if not backup_uuid:
                return FileHandlerResult(
                    success=False,
                    handler_id=req.handler_id,
                    operation=req.operation,
                    file_path=req.file_path,
                    project_id=req.project_id,
                    dry_run=False,
                    changed=False,
                    message=(
                        "Backup to old_code (versions) is mandatory before write; "
                        "create_backup failed. Aborting universal_file_save."
                    ),
                    code="BACKUP_REQUIRED",
                    details={
                        "file_path": req.file_path,
                        "resolved_path": str(absolute_path),
                    },
                )

        fr = TextFileHandler().save(req)
        if not fr.success:
            return fr

        if dry_run:
            return fr

        meta = persist_plain_text_file_metadata(
            database=database,
            project_id=req.project_id,
            absolute_path=absolute_path,
            normalized_path=normalized_path,
            source_code=absolute_path.read_text(encoding="utf-8", errors="replace"),
        )
        if not meta.get("success"):
            if backup_uuid:
                try:
                    rel = str(absolute_path.relative_to(root_dir.resolve()))
                except ValueError:
                    rel = str(absolute_path)
                _restore(rel, backup_uuid)
            return FileHandlerResult(
                success=False,
                handler_id=req.handler_id,
                operation=req.operation,
                file_path=req.file_path,
                project_id=req.project_id,
                dry_run=False,
                changed=False,
                message="Failed to update file metadata: "
                + str(meta.get("error", "unknown")),
                code="UPDATE_FILE_DATA_ERROR",
                details=meta,
            )
        out = dict(fr.data or {})
        out["metadata_update"] = meta
        if backup_uuid:
            out["backup_uuid"] = backup_uuid
        return FileHandlerResult(
            success=True,
            handler_id=fr.handler_id,
            operation=fr.operation,
            file_path=fr.file_path,
            project_id=fr.project_id,
            dry_run=fr.dry_run,
            changed=fr.changed,
            data=out,
        )
