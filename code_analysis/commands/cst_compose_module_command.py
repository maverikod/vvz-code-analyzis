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
                    "description": "Node ID to attach branch to (tree_id mode only). If empty - overwrite file with branch.",
                },
                "ops": {
                    "type": "array",
                    "description": "List of replace operations (ops mode). Each item: { selector: { kind, ... }, new_code [, file_docstring ] }. Selector kinds: module, function, class, method, range, block_id, node_id, cst_query.",
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
        """
        Get detailed command metadata for AI models.

        Returns:
            Dictionary with command metadata including usage_examples.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The compose_cst_module command applies CST changes to a file with atomic operations. "
                "Two modes: (1) tree_id + optional node_id — attach a branch (CST tree) to a node or overwrite file; "
                "(2) ops — list of selector + new_code patches (e.g. replace by function name, range, cst_query). "
                "Selector kinds: module, function, class, method, range, block_id, node_id, cst_query. "
                "When apply=true (default), validates (compile, flake8, mypy, docstrings), backs up, and writes. "
                "Use apply=false with return_diff=true to preview without writing."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID. Required.",
                    "type": "string",
                    "required": True,
                },
                "file_path": {
                    "description": "Target .py path relative to project root.",
                    "type": "string",
                    "required": True,
                },
                "tree_id": {
                    "description": "CST tree ID from cst_load_file (branch to attach). Use with node_id or omit to overwrite file.",
                    "type": "string",
                },
                "node_id": {
                    "description": "Node ID to attach branch to (tree_id mode). Empty = overwrite file with branch.",
                    "type": "string",
                },
                "ops": {
                    "description": "List of { selector: { kind, ... }, new_code [, file_docstring ] }. Use instead of tree_id for selector-based patches.",
                    "type": "array",
                },
                "apply": {
                    "description": "If true (default), write to file. If false, only return diff/stats.",
                    "type": "boolean",
                    "default": True,
                },
                "create_backup": {
                    "description": "Create backup before writing (when apply=true).",
                    "type": "boolean",
                    "default": True,
                },
                "return_diff": {
                    "description": "Include unified diff in response.",
                    "type": "boolean",
                    "default": False,
                },
                "commit_message": {
                    "description": "Optional git commit message.",
                    "type": "string",
                },
            },
            "return_value": {
                "success": {
                    "description": "On success: data with applied count, backup_uuid, diff (if requested)."
                },
                "error": {
                    "description": "On failure: code (e.g. INVALID_PARAMS, PROJECT_NOT_FOUND), message, details."
                },
            },
            "usage_examples": [
                {
                    "description": "Replace an import (ops mode, cst_query selector)",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "src/main.py",
                        "ops": [
                            {
                                "selector": {
                                    "kind": "cst_query",
                                    "query": "ImportFrom[module='.task_status']",
                                    "match_index": 0,
                                },
                                "new_code": "from ..task_status import TaskStatus",
                            }
                        ],
                        "apply": True,
                        "create_backup": True,
                    },
                    "explanation": (
                        "Replaces the first ImportFrom matching the CSTQuery. "
                        "Selector kinds for ops: module, function, class, method, range, block_id, node_id, cst_query."
                    ),
                },
                {
                    "description": "Replace code by line range (ops mode, range selector)",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "src/utils.py",
                        "ops": [
                            {
                                "selector": {
                                    "kind": "range",
                                    "start_line": 10,
                                    "end_line": 15,
                                },
                                "new_code": "# replaced lines 10-15",
                            }
                        ],
                        "apply": False,
                        "return_diff": True,
                    },
                    "explanation": (
                        "Replaces the block covering lines 10-15 (1-based). "
                        "apply=false returns diff without writing; use apply=true to write."
                    ),
                },
                {
                    "description": "Replace function by name (ops mode, function selector)",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "src/main.py",
                        "ops": [
                            {
                                "selector": {"kind": "function", "name": "old_helper"},
                                "new_code": "def old_helper():\n    return default",
                            }
                        ],
                    },
                    "explanation": (
                        "Replaces the function named old_helper with new code. "
                        "Selector kind 'function' requires 'name'."
                    ),
                },
                {
                    "description": "Attach branch to node (tree_id mode)",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "src/main.py",
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "node_id": "function:process_data:FunctionDef:10:0-30:0",
                    },
                    "explanation": (
                        "Inserts the CST tree (branch) from cst_load_file into the process_data function. "
                        "Omit node_id to overwrite the entire file with the branch."
                    ),
                },
            ],
        }

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
        if has_tree and has_ops:
            return ErrorResult(
                message="Provide either tree_id or ops, not both",
                code="INVALID_PARAMS",
                details={
                    "hint": "Use tree_id for branch attach or ops for selector-based patches"
                },
            )
        if not has_tree and not has_ops:
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
