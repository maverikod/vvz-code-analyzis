"""
Tree-id flow for compose_cst_module: attach branch or overwrite file.

Runs the tree_id path (get tree, generate source, validate, backup, apply).
Used by ComposeCSTModuleCommand.execute() when tree_id is provided.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.backup_manager import BackupManager
from ..core.cst_tree.tree_builder import get_tree, load_file_to_tree
from ..core.cst_tree.tree_metadata import get_node_metadata
from ..core.cst_tree.models import TreeOperation, TreeOperationType
from ..core.cst_tree.tree_modifier import modify_tree
from ..core.git_integration import commit_after_write
from ..core.uuid_validation import is_valid_uuid4
from .base_mcp_command import BaseMCPCommand
from .project_text_file_guard import reject_if_write_under_project_venv
from .compose_cst_db import backup_file_data
from .compose_cst_writer import apply_changes, validate_and_write_temp

logger = logging.getLogger(__name__)


def run_tree_id_flow(
    command: Any,
    project_id: str,
    file_path: str,
    tree_id: str,
    node_id: Optional[str],
    commit_message: Optional[str],
    t_start: float,
    t_prev: float,
) -> SuccessResult | ErrorResult:
    """
    Execute tree_id mode: get branch tree, generate source, validate, backup, apply.

    Args:
        command: ComposeCSTModuleCommand instance (for _resolve_project_root,
                 _open_database_from_config, _handle_error).
        project_id: Project ID.
        file_path: File path relative to project root.
        tree_id: CST tree ID (branch).
        node_id: Optional node ID to attach branch to.
        commit_message: Optional git commit message.
        t_start: Start timestamp for profiling.
        t_prev: Previous step timestamp for profiling.

    Returns:
        SuccessResult or ErrorResult.
    """
    root_path = command._resolve_project_root(project_id)
    target_path = (root_path / file_path).resolve()

    blocked = reject_if_write_under_project_venv(target_path, root_path)
    if blocked is not None:
        return blocked

    tree = get_tree(tree_id)
    if not tree:
        return ErrorResult(
            message=f"Tree not found: {tree_id}",
            code="TREE_NOT_FOUND",
            details={"tree_id": tree_id},
        )

    branch_code = tree.module.code.strip()
    if not branch_code:
        return ErrorResult(
            message="Branch (tree_id) must not be empty",
            code="EMPTY_BRANCH",
            details={"tree_id": tree_id},
        )

    _t = time.perf_counter()
    logger.info(
        "[PROFILE] compose_cst_module step=2 get_tree elapsed=%.3fs",
        _t - t_prev,
    )
    t_prev = _t

    if not target_path.exists():
        tree.file_path = str(target_path.resolve())

    if target_path.suffix != ".py":
        return ErrorResult(
            message="Target file must be a .py file",
            code="INVALID_FILE",
            details={"file_path": str(target_path)},
        )

    file_exists = target_path.exists()

    if node_id:
        if not is_valid_uuid4(node_id):
            return ErrorResult(
                message="node_id must be a valid UUID4",
                code="INVALID_NODE_ID",
                details={"node_id": node_id, "file_path": str(target_path)},
            )
        if not file_exists:
            return ErrorResult(
                message="File does not exist. Cannot attach branch to node in non-existent file.",
                code="FILE_NOT_FOUND",
                details={
                    "file_path": str(target_path),
                    "node_id": node_id,
                },
            )

        file_tree = load_file_to_tree(str(target_path))
        file_tree_id = file_tree.tree_id

        node_metadata = get_node_metadata(file_tree_id, node_id)
        if not node_metadata:
            return ErrorResult(
                message=f"Node not found: {node_id}",
                code="NODE_NOT_FOUND",
                details={"node_id": node_id, "file_path": str(target_path)},
            )

        operations = [
            TreeOperation(
                action=TreeOperationType.INSERT,
                target_node_id=node_id,
                code=branch_code,
                position="after",
            )
        ]
        modified_tree = modify_tree(file_tree_id, operations)
        source_code = modified_tree.module.code
    else:
        source_code = branch_code

    source_code = source_code.rstrip("\n\r") + "\n"
    _t = time.perf_counter()
    logger.info(
        "[PROFILE] compose_cst_module step=3_4 generate_source elapsed=%.3fs",
        _t - t_prev,
    )
    t_prev = _t

    temp_file_raw, validation_error, validation_results = validate_and_write_temp(
        source_code, target_path
    )
    temp_file: Optional[Path] = temp_file_raw
    _t = time.perf_counter()
    logger.info(
        "[PROFILE] compose_cst_module step=5 validate_and_write_temp elapsed=%.3fs",
        _t - t_prev,
    )
    t_prev = _t
    if validation_error:
        return validation_error

    logger.info(
        "[CHAIN] compose_cst_module opening database root_path=%s",
        root_path,
    )
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

        _t = time.perf_counter()
        logger.info(
            "[PROFILE] compose_cst_module step=6_7 open_db_and_backup_data elapsed=%.3fs",
            _t - t_prev,
        )
        t_prev = _t

        if file_exists:
            backup_manager = BackupManager(root_path)
            backup_uuid = backup_manager.create_backup(
                target_path,
                command="compose_cst_module",
                comment=commit_message or "",
            )
            if not backup_uuid:
                if temp_file and temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass
                return ErrorResult(
                    message=(
                        "Backup to old_code (versions) is mandatory before write; "
                        "create_backup failed. Aborting compose_cst_module."
                    ),
                    code="BACKUP_REQUIRED",
                    details={"file_path": str(target_path)},
                )
        _t = time.perf_counter()
        logger.info(
            "[PROFILE] compose_cst_module step=8 create_file_backup elapsed=%.3fs",
            _t - t_prev,
        )
        t_prev = _t

        logger.info("[CHAIN] compose_cst_module calling database.begin_transaction")
        _t_begin = time.perf_counter()
        transaction_id = database.begin_transaction()
        _t = time.perf_counter()
        logger.info(
            "[PROFILE] compose_cst_module step=9 begin_transaction elapsed=%.3fs",
            _t - _t_begin,
        )
        t_prev = _t
        logger.info(
            "[CHAIN] compose_cst_module begin_transaction returned transaction_id=%s",
            (
                (transaction_id[:8] + "...")
                if transaction_id and len(transaction_id) > 8
                else transaction_id
            ),
        )
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

        assert temp_file is not None  # ensured by early return on validation_error
        try:
            result = apply_changes(
                database=database,
                transaction_id=transaction_id,
                project_id=project_id,
                root_path=root_path,
                target_path=target_path,
                source_code=source_code,
                file_id=file_id,
                file_data_backup=file_data_backup,
                backup_uuid=backup_uuid,
                backup_manager=backup_manager,
                temp_file=temp_file,
                commit_message=commit_message,
            )
            _t = time.perf_counter()
            logger.info(
                "[PROFILE] compose_cst_module step=9_15 apply_changes elapsed=%.3fs",
                _t - t_prev,
            )
            temp_file = None  # File was moved; do not unlink in finally

            if validation_results and isinstance(result, SuccessResult):
                if result.data:
                    result.data["validation_results"] = {
                        validation_type: {
                            "success": val_result.success,
                            "error_message": val_result.error_message,
                            "errors_count": len(val_result.errors),
                        }
                        for validation_type, val_result in validation_results.items()
                    }

            if isinstance(result, SuccessResult):
                git_ok, git_err = commit_after_write(
                    root_path,
                    [target_path],
                    "compose_cst_module",
                    commit_message_override=commit_message,
                    config_data=BaseMCPCommand._get_raw_config(),
                )
                if not git_ok and git_err:
                    logger.warning(
                        "Git commit after compose_cst_module: %s",
                        git_err,
                    )

            logger.info(
                "[PROFILE] compose_cst_module total elapsed=%.3fs",
                time.perf_counter() - t_start,
            )
            logger.info(
                "[TIMING] command=compose_cst_module total_elapsed_sec=%.4f",
                time.perf_counter() - t_start,
            )
            return result

        except Exception as error:
            raise error

    finally:
        database.disconnect()

        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
            except Exception as cleanup_error:
                logger.warning("Failed to delete temporary file: %s", cleanup_error)
