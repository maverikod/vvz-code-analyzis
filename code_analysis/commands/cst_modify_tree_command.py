"""
MCP command: cst_modify_tree

Modify CST tree with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .project_text_file_guard import reject_if_write_under_project_venv
from .cst_modify_tree_schema import get_cst_modify_tree_schema
from .cst_modify_tree_helpers import (
    InvalidNodeIdError,
    _expand_replace_many_operations,
)
from .cst_modify_tree_metadata import get_cst_modify_tree_metadata
from .cst_modify_tree_ops_build import build_tree_operations
from ..core.cst_tree.models import TreeNodeMetadata, TreeOperation, TreeOperationType
from ..core.cst_tree.tree_builder import (
    _attach_disk_snapshot,
    get_tree,
    rollback_tree_to_code,
)
from ..core.cst_tree.tree_modifier import modify_tree
from ..core.cst_tree.tree_save_verification import (
    CST_REPLAY_MISMATCH,
    FILE_CHANGED_SINCE_LOAD,
    SaveVerificationError,
    TREE_MODULE_CORRUPT,
    WRITE_VERIFY_FAILED,
    assert_tree_module_integrity,
)
from ..core.cst_tree.tree_saver import save_tree_to_file

logger = logging.getLogger(__name__)

# Re-export for callers that import from this module
__all__ = ["CSTModifyTreeCommand", "InvalidNodeIdError"]


class CSTModifyTreeCommand(BaseMCPCommand):
    """Modify CST tree with atomic operations."""

    name = "cst_modify_tree"
    version = "1.0.0"
    descr = "Modify CST tree with atomic operations (replace, insert, delete)"
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return get_cst_modify_tree_schema()

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate params and reject unknown project_id when present."""
        params = super().validate_params(params)
        if params.get("project_id"):
            BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    async def execute(
        self,
        tree_id: str,
        operations: List[Dict[str, Any]],
        preview: bool = False,
        project_id: Optional[str] = None,
        file_path: Optional[str] = None,
        validate: bool = True,
        backup: bool = True,
        commit_message: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        t_start = time.perf_counter()
        try:
            t0 = time.perf_counter()
            original_tree = get_tree(tree_id)
            try:
                assert_tree_module_integrity(original_tree)
            except SaveVerificationError as _integrity_exc:
                return ErrorResult(
                    message=(
                        f"Tree {tree_id} has corrupt in-memory module "
                        f"(SHA256 mismatch: {_integrity_exc.code}). "
                        "Reload the tree via cst_load_file before modifying."
                    ),
                    code=TREE_MODULE_CORRUPT,
                    details=dict(_integrity_exc.details),
                )
            if not original_tree:
                return ErrorResult(
                    message=f"Tree not found: {tree_id}",
                    code="TREE_NOT_FOUND",
                    details={"tree_id": tree_id},
                )

            # Expand replace_many into multiple replace ops (all validated before apply)
            try:
                operations = _expand_replace_many_operations(operations)
            except ValueError as e:
                return ErrorResult(
                    message=str(e),
                    code="INVALID_OPERATION",
                    details={
                        "hint": "replace_many requires replacements with selector and code/code_lines"
                    },
                )

            tree_operations_list, build_err = build_tree_operations(
                original_tree, operations
            )
            if build_err is not None:
                return build_err
            tree_operations = tree_operations_list

            original_code = original_tree.module.code
            index_snapshot = dict(original_tree.metadata_map)
            logger.info(
                "[TIMING] command=cst_modify_tree step=convert_ops elapsed_sec=%.4f",
                time.perf_counter() - t0,
            )
            t_mod = time.perf_counter()
            # Combined save runs replay verify with disk source; remap needs pre-modify ids
            # when a replace removes targets from the live metadata_map (e.g. whole ClassDef).
            will_combined_save = (not preview) and bool(project_id and file_path)
            pre_modify_metadata_snapshot: Optional[Dict[str, TreeNodeMetadata]] = None
            if will_combined_save:
                pre_modify_metadata_snapshot = dict(original_tree.metadata_map)
            if preview:
                from difflib import unified_diff

                from .cst_modify_tree_preview_guard import (
                    diff_span_exceeds_guard,
                    original_changed_line_span,
                )

                preview_err: Optional[ErrorResult] = None
                preview_data: Optional[Dict[str, Any]] = None
                try:
                    modified_tree = modify_tree(tree_id, tree_operations)
                    modified_code = modified_tree.module.code
                    logger.info(
                        "[TIMING] command=cst_modify_tree step=modify_tree elapsed_sec=%.4f total_elapsed_sec=%.4f",
                        time.perf_counter() - t_mod,
                        time.perf_counter() - t_start,
                    )

                    diff_lines = list(
                        unified_diff(
                            original_code.splitlines(keepends=True),
                            modified_code.splitlines(keepends=True),
                            fromfile="original",
                            tofile="modified",
                            lineterm="",
                        )
                    )
                    diff = "".join(diff_lines)

                    validation_result: Dict[str, Any] = {
                        "syntax_valid": True,
                        "compiles": True,
                        "error": None,
                    }
                    try:
                        compile(modified_code, "<string>", "exec")
                    except SyntaxError as e:
                        validation_result = {
                            "syntax_valid": False,
                            "compiles": False,
                            "error": str(e),
                            "line": e.lineno if e.lineno is not None else None,
                            "offset": e.offset if e.offset is not None else None,
                        }

                    replace_targets = tuple(
                        op.node_id
                        for op in tree_operations
                        if op.action == TreeOperationType.REPLACE and op.node_id
                    )
                    unsafe_msg = diff_span_exceeds_guard(
                        original_code,
                        modified_code,
                        original_tree,
                        replace_targets,
                        slack_lines=1,
                    )
                    if unsafe_msg:
                        preview_err = ErrorResult(
                            message=unsafe_msg,
                            code="DIFF_SPAN_EXCEEDS_GUARD",
                            details={
                                "tree_id": tree_id,
                                "hint": "Preview refused: diff touches lines outside the "
                                "enclosing statement for the replace target(s).",
                            },
                        )
                    else:
                        ch_span = original_changed_line_span(
                            original_code, modified_code
                        )
                        preview_data = {
                            "success": True,
                            "preview": True,
                            "preview_only": True,
                            "file_written": False,
                            "tree_id": tree_id,
                            "operations_count": len(operations),
                            "changes": [
                                {
                                    "operation": op_dict.get("action"),
                                    "node_id": op_dict.get("node_id")
                                    or op_dict.get("start_node_id"),
                                    "description": f"{op_dict.get('action')} operation",
                                }
                                for op_dict in operations
                            ],
                            "diff": diff,
                            "validation": validation_result,
                            "changed_span": (
                                {
                                    "original_start_line": ch_span[0],
                                    "original_end_line": ch_span[1],
                                }
                                if ch_span is not None
                                else None
                            ),
                        }
                except ValueError as e:
                    preview_err = ErrorResult(
                        message=f"Invalid operation: {e}",
                        code="INVALID_OPERATION",
                        details={"tree_id": tree_id, "error": str(e)},
                    )
                finally:
                    if not rollback_tree_to_code(
                        tree_id,
                        original_code,
                        index_metadata_for_code=index_snapshot,
                    ):
                        logger.error(
                            "cst_modify_tree preview: failed to restore in-memory tree %s",
                            tree_id,
                        )
                if preview_err is not None:
                    return preview_err
                if preview_data is None:
                    return ErrorResult(
                        message="cst_modify_tree preview produced no result data",
                        code="CST_MODIFY_ERROR",
                        details={"tree_id": tree_id},
                    )
                return SuccessResult(data=preview_data)

            modified_tree = modify_tree(tree_id, tree_operations)
            modified_code = modified_tree.module.code
            logger.info(
                "[TIMING] command=cst_modify_tree step=modify_tree elapsed_sec=%.4f total_elapsed_sec=%.4f",
                time.perf_counter() - t_mod,
                time.perf_counter() - t_start,
            )

            # Build modified_nodes for verification (when multiple nodes affected)
            modified_nodes: List[Dict[str, Any]] = []
            for op in tree_operations:
                entry: Dict[str, Any] = {
                    "node_id": op.node_id,
                    "action": (
                        op.action.value
                        if hasattr(op.action, "value")
                        else str(op.action)
                    ),
                }
                if op.action == TreeOperationType.REPLACE and (
                    op.code or op.code_lines
                ):
                    entry["code"] = (
                        "\n".join(op.code_lines) if op.code_lines else (op.code or "")
                    )
                elif op.action == TreeOperationType.DELETE:
                    entry["code"] = ""
                    entry["removed"] = True
                modified_nodes.append(entry)

            # Normal mode: apply changes
            data = {
                "success": True,
                "preview": False,
                "preview_only": False,
                "file_written": False,  # Updated to True if saved to file below
                "tree_id": modified_tree.tree_id,
                "operations_applied": len(tree_operations),
                "modified_nodes": modified_nodes,
            }

            # Optional: save to file in the same request
            if project_id and file_path:
                database = self._open_database_from_config(auto_analyze=False)
                try:
                    absolute_file_path = self._resolve_file_path_from_project(
                        database, project_id, file_path
                    )
                    project = database.get_project(project_id)
                    if not project:
                        rollback_tree_to_code(
                            tree_id,
                            original_code,
                            index_metadata_for_code=index_snapshot,
                        )
                        return ErrorResult(
                            message=f"Project {project_id} not found",
                            code="PROJECT_NOT_FOUND",
                            details={"project_id": project_id},
                        )
                    project_root = Path(project.root_path)
                    blocked_venv = reject_if_write_under_project_venv(
                        absolute_file_path, project_root
                    )
                    if blocked_venv is not None:
                        rollback_tree_to_code(
                            tree_id,
                            original_code,
                            index_metadata_for_code=index_snapshot,
                        )
                        return blocked_venv
                    try:
                        save_result = await asyncio.to_thread(
                            save_tree_to_file,
                            tree_id=tree_id,
                            file_path=str(absolute_file_path),
                            root_dir=project_root,
                            project_id=project_id,
                            database=database,
                            validate=validate,
                            backup=backup,
                            commit_message=commit_message,
                            tree_operations=tree_operations,
                            pre_modify_metadata_map=pre_modify_metadata_snapshot,
                        )
                    except SaveVerificationError as save_exc:
                        resynced_from_disk = bool(
                            save_exc.code == FILE_CHANGED_SINCE_LOAD
                            and save_exc.details.get("resynced_tree_from_disk")
                        )
                        if not resynced_from_disk:
                            rollback_tree_to_code(
                                tree_id,
                                original_code,
                                index_metadata_for_code=index_snapshot,
                            )
                        data["modify_applied"] = False
                        data["save_applied"] = False
                        data["file_written"] = False
                        data["save_error"] = str(save_exc)
                        data["save_error_cause"] = str(save_exc)
                        if save_exc.code in (
                            FILE_CHANGED_SINCE_LOAD,
                            CST_REPLAY_MISMATCH,
                            WRITE_VERIFY_FAILED,
                        ):
                            data["save_error_code"] = save_exc.code
                            data["save_error_details"] = dict(save_exc.details)
                        return SuccessResult(data=data)
                    except Exception as save_exc:
                        rollback_tree_to_code(
                            tree_id,
                            original_code,
                            index_metadata_for_code=index_snapshot,
                        )
                        data["modify_applied"] = False
                        data["save_applied"] = False
                        data["file_written"] = False
                        data["save_error"] = str(save_exc)
                        data["save_error_cause"] = str(save_exc)
                        return SuccessResult(data=data)
                    if not save_result.get("success"):
                        rollback_tree_to_code(
                            tree_id,
                            original_code,
                            index_metadata_for_code=index_snapshot,
                        )
                        save_err = save_result.get("error", "Save failed")
                        data["modify_applied"] = False
                        data["save_applied"] = False
                        data["file_written"] = False
                        data["save_error"] = save_err
                        data["save_error_cause"] = save_result.get(
                            "error_details", save_err
                        )
                        return SuccessResult(data=data)
                    data["save_applied"] = True
                    data["file_written"] = True
                    data["file_path"] = str(absolute_file_path)
                    if save_result.get("backup_uuid"):
                        data["backup_uuid"] = save_result["backup_uuid"]
                    # BUG FIX: refresh module_source_sha256_hex after combined save
                    _saved_tree = get_tree(tree_id)
                    if _saved_tree is not None:
                        _attach_disk_snapshot(_saved_tree, _saved_tree.module.code)
                finally:
                    database.disconnect()

            return SuccessResult(data=data)

        except InvalidNodeIdError as e:
            return ErrorResult(
                message=str(e),
                code="INVALID_NODE_ID",
                details={
                    "tree_id": tree_id,
                    "hint": "Mutation target IDs must be non-empty UUID4 (from cst_find_node or cst_get_node_info). Use __root__ only for parent_node_id.",
                },
            )
        except ValueError as e:
            # Extract detailed error information for better error messages
            error_msg = str(e)
            error_details = {"tree_id": tree_id, "error": error_msg}

            # Try to extract node context from error message
            if "Node" in error_msg and "was not replaced" in error_msg:
                # Parse error for additional context
                if "Node type:" in error_msg:
                    error_details["hint"] = (
                        "Check that the node is in a replaceable context (Module or IndentedBlock body)"
                    )
                if "Try using replace_range" in error_msg:
                    error_details["suggestion"] = (
                        "Consider using replace_range operation for replacing multiple statements"
                    )

            return ErrorResult(
                message=f"Invalid operation: {error_msg}",
                code="INVALID_OPERATION",
                details=error_details,
            )
        except Exception as e:
            logger.exception("cst_modify_tree failed: %s", e)
            return ErrorResult(
                message=f"cst_modify_tree failed: {e}", code="CST_MODIFY_ERROR"
            )

    @classmethod
    def metadata(cls: type["CSTModifyTreeCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        Returns:
            Dictionary with command metadata.
        """
        return get_cst_modify_tree_metadata()
