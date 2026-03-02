"""
Ops-based flow for compose_cst_module: apply_replace_ops and optionally write.

Runs the ops path (build ReplaceOp list, apply patches, validate, backup, apply).
Used by ComposeCSTModuleCommand.execute() when ops are provided.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import difflib
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.backup_manager import BackupManager
from ..core.cst_module import apply_replace_ops
from ..core.exceptions import CSTModulePatchError
from ..core.git_integration import commit_after_write
from .base_mcp_command import BaseMCPCommand
from .compose_cst_db import backup_file_data
from .compose_cst_writer import apply_changes as writer_apply_changes
from .compose_cst_writer import validate_and_write_temp

logger = logging.getLogger(__name__)


async def run_ops_mode(
    command: Any,
    project_id: str,
    file_path: str,
    root_path: Path,
    ops: List[Dict[str, Any]],
    apply: bool,
    create_backup: bool,
    return_diff: bool,
    commit_message: Optional[str],
    t_start: float,
    t_prev: float,
) -> SuccessResult | ErrorResult:
    """
    Execute ops-based compose: build ReplaceOp list, apply_replace_ops, optionally write.

    When apply=false, only return diff/stats. When apply=true, backup + validate + write.
    """
    target_path = (root_path / file_path).resolve()
    if target_path.suffix != ".py":
        return ErrorResult(
            message="Target file must be a .py file",
            code="INVALID_FILE",
            details={"file_path": str(target_path)},
        )

    try:
        replace_ops = command._ops_from_params(ops)
    except ValueError as e:
        return ErrorResult(
            message=str(e),
            code="INVALID_OPS",
            details={"ops": ops},
        )

    if target_path.exists():
        try:
            source = target_path.read_text(encoding="utf-8")
        except Exception as e:
            return ErrorResult(
                message=f"Failed to read file: {e}",
                code="FILE_READ_ERROR",
                details={"file_path": str(target_path)},
            )
    else:
        source = ""

    try:
        new_source, stats = apply_replace_ops(source, replace_ops)
    except CSTModulePatchError as e:
        return ErrorResult(
            message=str(e),
            code="CST_REPLACE_ERROR",
            details=getattr(e, "details", {}),
        )

    new_source = new_source.rstrip("\n\r") + "\n"

    data: Dict[str, Any] = {
        "success": True,
        "file_path": str(target_path),
        "stats": stats,
    }
    if return_diff:
        diff_lines = difflib.unified_diff(
            source.splitlines(keepends=True),
            new_source.splitlines(keepends=True),
            fromfile=file_path,
            tofile=file_path,
        )
        data["diff"] = "".join(diff_lines)

    if not apply:
        data["applied"] = False
        data["message"] = "Preview only; no file written"
        return SuccessResult(data=data)

    file_exists = target_path.exists()
    temp_file, validation_error, validation_results = validate_and_write_temp(
        new_source, target_path
    )
    if validation_error:
        return validation_error

    database = command._open_database_from_config(auto_analyze=False)
    backup_manager: Optional[BackupManager] = None
    backup_uuid: Optional[str] = None
    file_data_backup: Optional[Dict[str, Any]] = None
    file_id: Optional[int] = None

    try:
        if file_exists:
            from ..core.path_normalization import normalize_path_simple

            normalized_path = normalize_path_simple(str(target_path))
            file_rows = database.select(
                "files",
                where={"path": normalized_path, "project_id": project_id},
                limit=1,
            )
            if file_rows:
                file_record = file_rows[0]
                file_id = file_record["id"]
                file_data_backup = backup_file_data(database, file_id)

        if create_backup and file_exists:
            backup_manager = BackupManager(root_path)
            backup_uuid = backup_manager.create_backup(
                target_path,
                command="compose_cst_module",
                comment=commit_message or "",
            )

        transaction_id = database.begin_transaction()
        if not transaction_id:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            return ErrorResult(
                message="Database transaction could not be started",
                code="TRANSACTION_ERROR",
                details={"hint": "Database driver may be busy or unavailable"},
            )

        try:
            result = writer_apply_changes(
                database=database,
                transaction_id=transaction_id,
                project_id=project_id,
                root_path=root_path,
                target_path=target_path,
                source_code=new_source,
                file_id=file_id,
                file_data_backup=file_data_backup,
                backup_uuid=backup_uuid,
                backup_manager=backup_manager,
                temp_file=temp_file,
                commit_message=commit_message,
            )
            if isinstance(result, SuccessResult) and result.data:
                result.data["stats"] = stats
                if return_diff and "diff" not in result.data:
                    result.data["diff"] = data.get("diff")
                if validation_results:
                    result.data["validation_results"] = {
                        vt: {
                            "success": vr.success,
                            "error_message": vr.error_message,
                            "errors_count": len(vr.errors),
                        }
                        for vt, vr in validation_results.items()
                    }
            if isinstance(result, SuccessResult):
                commit_after_write(
                    root_path,
                    [target_path],
                    "compose_cst_module",
                    commit_message_override=commit_message,
                    config_data=BaseMCPCommand._get_raw_config(),
                )
            logger.info(
                "[PROFILE] compose_cst_module (ops) total elapsed=%.3fs",
                time.perf_counter() - t_start,
            )
            return result
        except Exception as err:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            raise err
    finally:
        database.disconnect()
