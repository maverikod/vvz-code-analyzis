"""
MCP command: compose_cst_module

Applies CST tree to file with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.backup_manager import BackupManager
from .compose_cst_db import backup_file_data
from .compose_cst_ops_flow import run_ops_mode
from .compose_cst_tree_flow import run_tree_id_flow
from .compose_cst_validation import (
    SUPPORTED_SELECTOR_KINDS,
    ops_from_params,
    selector_from_dict,
)
from .cst_compose_module_metadata import get_compose_cst_module_metadata
from .compose_cst_writer import (
    apply_changes as writer_apply_changes,
    handle_rollback as writer_handle_rollback,
    update_file_record as writer_update_file_record,
    validate_and_write_temp as writer_validate_and_write_temp,
)

logger = logging.getLogger(__name__)

__all__ = ["ComposeCSTModuleCommand", "SUPPORTED_SELECTOR_KINDS"]


class ComposeCSTModuleCommand(BaseMCPCommand):
    """
    Compose/patch a module using CST tree.

    Attaches a branch (tree_id) to a node in a file or overwrites/creates a file.

    Process:
    1. Check project exists
    2. Get CST tree (branch) from tree_id and check it's not empty
    3. If node_id is specified → load file, find node, insert branch code into node
    4. If node_id is empty → overwrite file with branch (or create new file)
    5. Write to temporary file
    6. Validate temporary file (compile, flake8, mypy, docstrings)
    7. If validation fails, return errors
    8. Check if file exists in database, backup data if exists
    9. Begin database transaction
    10. Delete all old data (clear_file_data)
    11. Add new data (update_file_data_atomic)
    12. Atomically replace file
    13. Commit transaction
    14. Git commit (if commit_message provided)
    15. On any error: rollback transaction and restore data from backup

    Validations:
    - Project existence
    - Node existence (if node_id provided)
    - Branch is not empty
    - Compilation (syntax check)
    - Flake8 (linting)
    - MyPy (type checking)
    - Docstrings:
      * File-level docstring
      * Class docstrings
      * Method docstrings
    """

    name = "compose_cst_module"
    version = "2.0.0"
    descr = "Apply CST tree to file with atomic operations"
    category = "refactor"
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
                    "description": "Project ID (UUID4). Required.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target python file path (relative to project root)",
                },
                "tree_id": {
                    "type": "string",
                    "description": "CST tree ID from cst_load_file (branch to attach). Use either tree_id or ops, not both.",
                },
                "node_id": {
                    "type": "string",
                    "description": "Node ID (UUID4) to attach branch to (tree_id mode only). If empty - overwrite file with branch. Must be valid UUID4.",
                },
                "ops": {
                    "type": "array",
                    "description": "List of replace operations (ops mode). Each item: { selector: { kind, ... }, new_code [, file_docstring ] }. Selector kinds: module, function, class, method, range, block_id, node_id (UUID4), cst_query. When ops contain node_id selector, tree_id is required.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "selector": {"type": "object"},
                            "new_code": {"type": "string"},
                            "file_docstring": {"type": "string"},
                        },
                        "required": ["selector", "new_code"],
                    },
                },
                "apply": {
                    "type": "boolean",
                    "description": "If true (default), write result to file. If false, only compute and return diff/stats (ops mode).",
                    "default": True,
                },
                "create_backup": {
                    "type": "boolean",
                    "description": "If true (default), create file backup before writing (ops mode, when apply=true).",
                    "default": True,
                },
                "return_diff": {
                    "type": "boolean",
                    "description": "If true, include unified diff in response (ops mode). When apply=false, returns diff without writing.",
                    "default": False,
                },
                "commit_message": {
                    "type": "string",
                    "description": "Optional git commit message",
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["ComposeCSTModuleCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models (delegates to metadata module)."""
        return get_compose_cst_module_metadata(cls)

    @staticmethod
    def _selector_from_dict(d: Dict[str, Any]):
        """Build Selector from request dict. Delegates to compose_cst_validation."""
        return selector_from_dict(d)

    @classmethod
    def _ops_from_params(cls, ops_list: Any) -> List:
        """Build list of ReplaceOp from request ops array. Delegates to compose_cst_validation."""
        return ops_from_params(ops_list)

    def _backup_file_data(self, database: Any, file_id: int):
        """Backup all file data from database. Delegates to compose_cst_db."""
        return backup_file_data(database, file_id)

    def _validate_and_write_temp(self, source_code: str, target_path: Path):
        """Write to temp file and validate. Delegates to compose_cst_writer."""
        return writer_validate_and_write_temp(source_code, target_path)

    def _update_file_record(
        self,
        database: Any,
        project_id: str,
        root_path: Path,
        target_path: Path,
        source_code: str,
        file_id: Optional[int],
    ) -> int:
        """Add or update file record. Delegates to compose_cst_writer."""
        return writer_update_file_record(
            database, project_id, root_path, target_path, source_code, file_id
        )

    def _handle_rollback(
        self,
        database: Any,
        file_id: Optional[int],
        file_data_backup: Optional[Dict[str, Any]],
        backup_uuid: Optional[str],
        backup_manager: Optional[BackupManager],
        root_path: Path,
        target_path: Path,
    ) -> None:
        """Handle rollback. Delegates to compose_cst_writer."""
        writer_handle_rollback(
            database,
            file_id,
            file_data_backup,
            backup_uuid,
            backup_manager,
            root_path,
            target_path,
        )

    def _apply_changes(
        self,
        database: Any,
        transaction_id: str,
        project_id: str,
        root_path: Path,
        target_path: Path,
        source_code: str,
        file_id: Optional[int],
        file_data_backup: Optional[Dict[str, Any]],
        backup_uuid: Optional[str],
        backup_manager: Optional[BackupManager],
        temp_file: Path,
        commit_message: Optional[str],
    ) -> SuccessResult | ErrorResult:
        """Apply changes within transaction. Delegates to compose_cst_writer."""
        return writer_apply_changes(
            database,
            transaction_id,
            project_id,
            root_path,
            target_path,
            source_code,
            file_id,
            file_data_backup,
            backup_uuid,
            backup_manager,
            temp_file,
            commit_message,
        )

    async def execute(
        self,
        project_id: str,
        file_path: str,
        tree_id: Optional[str] = None,
        node_id: Optional[str] = None,
        ops: Optional[List[Dict[str, Any]]] = None,
        apply: bool = True,
        create_backup: bool = True,
        return_diff: bool = False,
        commit_message: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute compose_cst_module command.

        Either tree_id (branch attach) or ops (selector-based patches) must be provided.
        """
        t_start = time.perf_counter()
        t_prev = t_start

        has_tree = tree_id is not None and str(tree_id).strip() != ""
        has_ops = ops is not None and len(ops) > 0
        if not has_ops and not has_tree:
            return ErrorResult(
                message="Either tree_id or ops is required",
                code="INVALID_PARAMS",
                details={
                    "hint": "Use tree_id (from cst_load_file) or ops (list of selector + new_code)"
                },
            )

        logger.info(
            "[CHAIN] compose_cst_module execute entry project_id=%s file_path=%s tree_id=%s ops_mode=%s",
            project_id,
            file_path,
            tree_id if has_tree else "N/A",
            has_ops,
        )
        try:
            root_path = self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)
            try:
                project = database.get_project(project_id)
                if not project:
                    return ErrorResult(
                        message=f"Project not found: {project_id}",
                        code="PROJECT_NOT_FOUND",
                        details={"project_id": project_id},
                    )
            finally:
                database.disconnect()
            _t = time.perf_counter()
            logger.info(
                "[PROFILE] compose_cst_module step=1 resolve_project_and_check elapsed=%.3fs",
                _t - t_prev,
            )
            t_prev = _t

            if has_ops:
                return await run_ops_mode(
                    self,
                    project_id=project_id,
                    file_path=file_path,
                    root_path=root_path,
                    ops=ops or [],
                    apply=apply,
                    create_backup=create_backup,
                    return_diff=return_diff,
                    commit_message=commit_message,
                    t_start=t_start,
                    t_prev=_t,
                    tree_id=tree_id,
                )

            return run_tree_id_flow(
                self,
                project_id=project_id,
                file_path=file_path,
                tree_id=tree_id or "",
                node_id=node_id,
                commit_message=commit_message,
                t_start=t_start,
                t_prev=_t,
            )

        except Exception as e:
            logger.error(
                "[CHAIN] compose_cst_module execute failed: %s",
                e,
                exc_info=True,
            )
            return self._handle_error(e, "CST_COMPOSE_ERROR", "compose_cst_module")
