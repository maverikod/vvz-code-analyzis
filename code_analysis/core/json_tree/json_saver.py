"""
Save JSON tree to file with backup and DB file metadata update (non-CST path).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..backup_manager import BackupManager
from ..file_lock import file_lock
from ..path_normalization import normalize_path_simple
from .tree_builder import get_tree

logger = logging.getLogger(__name__)


def _serialize_document(root_data: Any) -> str:
    """Return serialize document."""
    return json.dumps(root_data, indent=2, ensure_ascii=False) + "\n"


def _format_error(exc: BaseException) -> str:
    """Return format error."""
    msg = str(exc).strip()
    if msg:
        return msg
    return type(exc).__name__


def _rollback_written_file(
    *,
    target_path: Path,
    root_dir: Path,
    backup_uuid: Optional[str],
    backup_manager: Optional[BackupManager],
    existed_before: bool,
) -> None:
    """Undo filesystem effects after a failed save (best effort)."""
    if backup_uuid and backup_manager and target_path.exists():
        try:
            rel_path = str(target_path.relative_to(root_dir))
        except ValueError:
            rel_path = str(target_path)
        restore_success, restore_message = backup_manager.restore_file(
            rel_path, backup_uuid
        )
        if restore_success:
            logger.info("json_save_tree restored from backup: %s", restore_message)
        else:
            logger.error(
                "json_save_tree backup restore failed: %s",
                restore_message,
            )
        return
    if not existed_before and target_path.exists():
        try:
            target_path.unlink()
            logger.info(
                "json_save_tree removed newly created file after failure: %s",
                target_path,
            )
        except OSError as ex:
            logger.warning("Failed to remove file after failed save: %s", ex)


def save_json_tree_to_file(
    tree_id: str,
    file_path: str,
    root_dir: Path,
    project_id: str,
    database: Any,
    backup: bool = True,
    create_parent_dirs: bool = True,
    verbatim_content: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Atomic write (.tmp + replace), optional backup, files-table metadata only.

    JSON is not Python source: metadata sync uses ``persist_plain_text_file_metadata``
    (no AST/CST/entity batch indexing).

    ``verbatim_content``, when given, is written to disk byte-for-byte instead of a
    fresh ``json.dumps(tree.root_data)`` re-serialization. Used by the full-file
    ``JsonFileHandler.save()`` path so uploaded/edited bytes persist unchanged
    (comments/formatting outside JSON's own grammar do not apply, but key order,
    spacing, and any non-canonical-but-valid formatting the source used are
    preserved). Pointer/node-id mutation paths (``replace`` / ``delete``) do not
    pass this and keep re-serializing ``tree.root_data`` as before.

    Git commits are handled by the MCP command layer (commit_after_write / config).
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    target_path = Path(file_path)
    if not target_path.is_absolute():
        target_path = (root_dir / target_path).resolve()
    else:
        target_path = target_path.resolve()
    root_dir = root_dir.resolve()

    try:
        target_path.relative_to(root_dir)
    except ValueError:
        return {
            "success": False,
            "file_path": str(target_path),
            "backup_uuid": None,
            "error": "Resolved path escapes project root",
            "error_code": "INVALID_FILE_PATH",
        }

    if target_path.suffix.lower() != ".json":
        raise ValueError(f"Target must be .json: {target_path}")

    if create_parent_dirs:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    elif not target_path.parent.exists():
        return {
            "success": False,
            "file_path": str(target_path),
            "backup_uuid": None,
            "error": f"Parent directory does not exist: {target_path.parent}",
            "error_code": "PARENT_DIR_MISSING",
        }

    source_code = (
        verbatim_content if verbatim_content is not None else _serialize_document(tree.root_data)
    )
    backup_uuid: Optional[str] = None
    backup_manager: Optional[BackupManager] = None
    temp_file: Optional[Path] = None
    existed_before = target_path.exists()

    rel_lock_path = str(target_path.relative_to(root_dir))
    with file_lock(
        target_path,
        mode="full",
        database=database,
        project_id=project_id,
        file_path=rel_lock_path,
    ):
        try:
            if backup and existed_before:
                backup_manager = BackupManager(root_dir)
                backup_uuid = backup_manager.create_backup(
                    target_path,
                    command="json_save_tree",
                    comment=f"Before saving JSON tree {tree_id}",
                )
                if not backup_uuid:
                    raise RuntimeError(
                        "Backup to old_code (versions) is mandatory before write; "
                        "create_backup failed. Aborting json_save_tree."
                    )
            temp_file = Path(str(target_path) + ".tmp")
            temp_file.write_text(source_code, encoding="utf-8")
            os.replace(str(temp_file), str(target_path))
            temp_file = None

            normalized_path = normalize_path_simple(str(target_path))
            from ..file_handlers.text_handler import persist_plain_text_file_metadata

            meta = persist_plain_text_file_metadata(
                database=database,
                project_id=project_id,
                absolute_path=target_path,
                normalized_path=normalized_path,
                source_code=source_code,
            )
            if not meta.get("success"):
                _rollback_written_file(
                    target_path=target_path,
                    root_dir=root_dir,
                    backup_uuid=backup_uuid,
                    backup_manager=backup_manager,
                    existed_before=existed_before,
                )
                err = (
                    meta.get("error")
                    or meta.get("error_code")
                    or "Failed to update file metadata"
                )
                return {
                    "success": False,
                    "file_path": str(target_path),
                    "backup_uuid": backup_uuid,
                    "error": str(err),
                    "error_code": meta.get("error_code", "UPDATE_FILE_DATA_ERROR"),
                    "metadata_result": meta,
                }

            tree.file_path = str(target_path)

            return {
                "success": True,
                "file_path": str(target_path),
                "file_id": meta.get("file_id"),
                "backup_uuid": backup_uuid,
                "metadata_result": meta,
            }

        except Exception as e:
            _rollback_written_file(
                target_path=target_path,
                root_dir=root_dir,
                backup_uuid=backup_uuid,
                backup_manager=backup_manager,
                existed_before=existed_before,
            )
            logger.exception("json_save_tree failed: %s", e)
            return {
                "success": False,
                "file_path": str(target_path),
                "backup_uuid": backup_uuid,
                "error": _format_error(e),
                "error_code": "JSON_SAVE_ERROR",
            }
        finally:
            if temp_file is not None and temp_file.exists():
                try:
                    temp_file.unlink(missing_ok=True)
                except OSError as ex:
                    logger.warning("Failed to remove temp file: %s", ex)
