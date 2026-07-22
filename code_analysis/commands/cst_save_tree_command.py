"""
MCP command: cst_save_tree

Save CST tree to file with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .project_text_file_guard import reject_if_write_under_project_venv
from ..core.cst_tree.tree_saver import save_tree_to_file
from ..core.cst_tree.tree_save_verification import SaveVerificationError
from ..core.cst_tree.tree_builder import reload_tree_from_file
from ..core.database_driver_pkg.domain.projects import get_project
from ..core.git_integration import commit_after_write
from ..core.database_client.exceptions import ConnectionError as DBConnectionError
from ..core.database_client.transient import (
    CATEGORY_RPC_CONNECT_REFUSED,
    CATEGORY_SQLITE_DB_LOCKED,
    MAX_ATTEMPTS,
    MAX_TOTAL_ELAPSED_SECONDS,
    compute_retry_delay,
    format_retry_summary_suffix,
    is_rpc_connect_refused_message,
    is_sqlite_db_locked,
)

logger = logging.getLogger(__name__)


class CSTSaveTreeCommand(BaseMCPCommand):
    """Save CST tree to file with atomic operations."""

    name = "cst_save_tree"
    version = "1.0.0"
    descr = "Save CST tree to file with atomic operations and rollback on errors"
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {
                "tree_id": {
                    "type": "string",
                    "description": "Tree ID from cst_load_file",
                },
                "project_id": {
                    "type": "string",
                    "description": "Project ID (UUID4). Required.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target file path (relative to project root)",
                },
                "validate": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Whether to validate file before saving. Default true. "
                        "Set false for controlled incremental edits (for example docstring-only pass), "
                        "then run format_code/lint_code/type_check_code explicitly. "
                        "With verification enabled, saving may fail if the file changed on disk since "
                        "load (FILE_CHANGED_SINCE_LOAD), edits do not replay identically "
                        "(CST_REPLAY_MISMATCH), or the written bytes do not match after replace "
                        "(WRITE_VERIFY_FAILED)—reload or reconcile before retrying."
                    ),
                },
                "backup": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to create backup",
                },
                "commit_message": {
                    "type": "string",
                    "description": "Optional git commit message",
                },
                "auto_reload": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Automatically reload tree from file after save (keeps tree_id valid). "
                        "Recommended for AI flows that perform multiple sequential edits."
                    ),
                },
            },
            "required": ["tree_id", "project_id", "file_path"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate params and reject unknown project_id immediately."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    async def execute(
        self,
        tree_id: str,
        project_id: str,
        file_path: str,
        validate: bool = True,
        backup: bool = True,
        commit_message: Optional[str] = None,
        auto_reload: bool = True,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """Execute cst_save_tree: save tree to file with lock check and retry logic.

        Args:
            tree_id: CST tree identifier from cst_load_file.
            project_id: Project UUID.
            file_path: Target file path relative to project root.
            validate: Validate syntax before and after save.
            backup: Create backup before overwriting.
            commit_message: Optional git commit message.
            auto_reload: Reload tree from file after save.
            **kwargs: Ignored extra keyword args.

        Returns:
            SuccessResult with save metadata, or ErrorResult with code.
        """
        logger.debug(
            "[SAVE_PATH] cst_save_tree enter tree_id=%s project_id=%s file_path=%s",
            tree_id,
            project_id,
            file_path,
        )
        t_start = time.perf_counter()
        t_retry_start = time.perf_counter()
        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    t0 = time.perf_counter()
                    database = self._open_database_from_config(auto_analyze=False)
                    try:
                        absolute_file_path = self._resolve_file_path_from_project(
                            database, project_id, file_path
                        )
                        project = get_project(database, project_id)
                        if not project:
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
                            return blocked_venv
                        logger.info(
                            "[TIMING] command=cst_save_tree step=resolve_path elapsed_sec=%.4f",
                            time.perf_counter() - t0,
                        )
                        logger.info(
                            "cst_save_tree path resolved",
                            extra={
                                "cst_save_stage": "path_resolved",
                                "project_id": project_id,
                                "tree_id": tree_id,
                                "file_path": str(absolute_file_path),
                                "attempt": attempt,
                                "validate": validate,
                                "backup": backup,
                            },
                        )
                        t0 = time.perf_counter()
                        logger.info(
                            "cst_save_tree save_tree_to_file thread enter",
                            extra={
                                "cst_save_stage": "save_thread_before",
                                "project_id": project_id,
                                "tree_id": tree_id,
                                "file_path": str(absolute_file_path),
                                "attempt": attempt,
                                "validate": validate,
                                "backup": backup,
                            },
                        )
                        try:
                            result = await asyncio.to_thread(
                                save_tree_to_file,
                                tree_id=tree_id,
                                file_path=str(absolute_file_path),
                                root_dir=project_root,
                                project_id=project_id,
                                database=database,
                                validate=validate,
                                backup=backup,
                                commit_message=commit_message,
                            )
                        except SaveVerificationError as exc:
                            logger.warning(
                                "cst_save_tree save verification failed code=%s tree_id=%s",
                                exc.code,
                                tree_id,
                                extra={
                                    "cst_save_stage": "save_verification_failed",
                                    "project_id": project_id,
                                    "tree_id": tree_id,
                                    "file_path": file_path,
                                    "verification_code": exc.code,
                                    "verification_details": dict(exc.details),
                                },
                            )
                            verification_details: Dict[str, Any] = {
                                "tree_id": tree_id,
                                "file_path": file_path,
                            }
                            verification_details.update(exc.details)
                            return ErrorResult(
                                message=f"Save verification failed: {exc.code}",
                                code=exc.code,
                                details=verification_details,
                            )
                        logger.info(
                            "cst_save_tree save_tree_to_file thread returned",
                            extra={
                                "cst_save_stage": "save_thread_after",
                                "project_id": project_id,
                                "tree_id": tree_id,
                                "file_path": str(absolute_file_path),
                                "attempt": attempt,
                            },
                        )
                        logger.info(
                            "[TIMING] command=cst_save_tree step=save_tree_to_file elapsed_sec=%.4f",
                            time.perf_counter() - t0,
                        )
                        if result.get("timings"):
                            for step_name, elapsed in sorted(result["timings"].items()):
                                logger.info(
                                    "[TIMING] command=cst_save_tree step=save_%s elapsed_sec=%.4f",
                                    step_name,
                                    elapsed,
                                )

                        if not result.get("success"):
                            err_msg = result.get("error", "Failed to save tree")
                            err_code = result.get("error_code", "CST_SAVE_ERROR")
                            # Propagate FILE_EDIT_LOCKED directly - no retry needed.
                            if err_code == "FILE_EDIT_LOCKED":
                                return ErrorResult(
                                    message=err_msg,
                                    code="FILE_EDIT_LOCKED",
                                    details={
                                        "file_path": file_path,
                                        "hint": (
                                            "Another process holds a write lock on this file. "
                                            "Wait for it to finish and retry cst_save_tree."
                                        ),
                                    },
                                )
                            if is_sqlite_db_locked(err_msg):
                                elapsed = time.perf_counter() - t_retry_start
                                if (
                                    attempt >= MAX_ATTEMPTS
                                    or elapsed >= MAX_TOTAL_ELAPSED_SECONDS
                                ):
                                    logger.error(
                                        "cst_save_tree retry exhausted category=%s attempts=%s elapsed_sec=%.2f",
                                        CATEGORY_SQLITE_DB_LOCKED,
                                        attempt,
                                        elapsed,
                                        extra={
                                            "cst_save_stage": "sqlite_lock_retry_exhausted",
                                            "project_id": project_id,
                                            "tree_id": tree_id,
                                            "file_path": str(absolute_file_path),
                                            "attempt": attempt,
                                            "exc_type": "SqliteLockedTransient",
                                        },
                                    )
                                    suffix = format_retry_summary_suffix(
                                        attempt, elapsed
                                    )
                                    return ErrorResult(
                                        message=f"{err_msg}{suffix}",
                                        code="CST_SAVE_ERROR",
                                        details=result,
                                    )
                                delay = compute_retry_delay(attempt)
                                logger.warning(
                                    "cst_save_tree transient db lock attempt=%s/%s category=%s next_delay_sec=%.2f",
                                    attempt,
                                    MAX_ATTEMPTS,
                                    CATEGORY_SQLITE_DB_LOCKED,
                                    delay,
                                    extra={
                                        "cst_save_stage": "sqlite_lock_retry",
                                        "project_id": project_id,
                                        "tree_id": tree_id,
                                        "file_path": str(absolute_file_path),
                                        "attempt": attempt,
                                    },
                                )
                                time.sleep(delay)
                                continue
                            if is_rpc_connect_refused_message(err_msg):
                                elapsed = time.perf_counter() - t_retry_start
                                if (
                                    attempt >= MAX_ATTEMPTS
                                    or elapsed >= MAX_TOTAL_ELAPSED_SECONDS
                                ):
                                    logger.error(
                                        "cst_save_tree retry exhausted category=%s attempts=%s elapsed_sec=%.2f",
                                        CATEGORY_RPC_CONNECT_REFUSED,
                                        attempt,
                                        elapsed,
                                        extra={
                                            "cst_save_stage": "rpc_connect_refused_exhausted_save_result",
                                            "failure_phase": "save_tree_result",
                                            "project_id": project_id,
                                            "tree_id": tree_id,
                                            "file_path": str(absolute_file_path),
                                            "attempt": attempt,
                                            "exc_type": "RpcConnectRefusedEmbedded",
                                        },
                                    )
                                    suffix = format_retry_summary_suffix(
                                        attempt, elapsed
                                    )
                                    return ErrorResult(
                                        message=f"{err_msg}{suffix}",
                                        code="CST_SAVE_ERROR",
                                        details=result,
                                    )
                                delay = compute_retry_delay(attempt)
                                logger.warning(
                                    "cst_save_tree transient connect refused "
                                    "(save result) attempt=%s/%s category=%s next_delay_sec=%.2f",
                                    attempt,
                                    MAX_ATTEMPTS,
                                    CATEGORY_RPC_CONNECT_REFUSED,
                                    delay,
                                    extra={
                                        "cst_save_stage": "rpc_connect_refused_retry_save_result",
                                        "failure_phase": "save_tree_result",
                                        "project_id": project_id,
                                        "tree_id": tree_id,
                                        "file_path": str(absolute_file_path),
                                        "attempt": attempt,
                                    },
                                )
                                time.sleep(delay)
                                continue
                            return ErrorResult(
                                message=err_msg,
                                code="CST_SAVE_ERROR",
                                details=result,
                            )

                        if auto_reload:
                            logger.info(
                                "cst_save_tree auto_reload before",
                                extra={
                                    "cst_save_stage": "auto_reload_before",
                                    "project_id": project_id,
                                    "tree_id": tree_id,
                                    "file_path": str(absolute_file_path),
                                },
                            )
                            t0 = time.perf_counter()
                            try:
                                reload_tree_from_file(tree_id=tree_id)
                                result["tree_reloaded"] = True
                            except Exception as reload_error:
                                logger.warning(
                                    "Failed to auto-reload tree after save: %s",
                                    reload_error,
                                    extra={
                                        "cst_save_stage": "auto_reload_error",
                                        "project_id": project_id,
                                        "tree_id": tree_id,
                                        "file_path": str(absolute_file_path),
                                        "exc_type": type(reload_error).__name__,
                                    },
                                )
                                result["tree_reloaded"] = False
                                result["reload_error"] = str(reload_error)
                            else:
                                logger.info(
                                    "cst_save_tree auto_reload after",
                                    extra={
                                        "cst_save_stage": "auto_reload_after",
                                        "project_id": project_id,
                                        "tree_id": tree_id,
                                        "file_path": str(absolute_file_path),
                                    },
                                )
                                logger.info(
                                    "[TIMING] command=cst_save_tree step=reload_tree elapsed_sec=%.4f",
                                    time.perf_counter() - t0,
                                )
                        else:
                            result["tree_reloaded"] = False

                        git_ok, git_err = commit_after_write(
                            project_root,
                            [Path(absolute_file_path)],
                            "cst_save_tree",
                            commit_message_override=commit_message,
                            config_data=BaseMCPCommand._get_raw_config(),
                        )
                        if not git_ok and git_err:
                            logger.warning(
                                "Git commit after cst_save_tree: %s", git_err
                            )

                        logger.info(
                            "[TIMING] command=cst_save_tree total_elapsed_sec=%.4f",
                            time.perf_counter() - t_start,
                        )
                        p = Path(absolute_file_path)
                        if p.exists():
                            result["file_size_bytes"] = p.stat().st_size
                            result["file_lines"] = len(
                                p.read_text(encoding="utf-8").splitlines()
                            )
                        if attempt > 1:
                            logger.info(
                                "cst_save_tree succeeded after %s attempts",
                                attempt,
                            )
                        return SuccessResult(data=result)
                    finally:
                        database.disconnect()

                except DBConnectionError:
                    # No-socket in-process driver (see core/database_client/factory.py):
                    # a raw connect-refused here cannot be a transient network blip, so
                    # there is nothing useful to retry — propagate to the generic handler
                    # below (stage-2 driver-prep: vestigial retry wrapper removed).
                    raise
        except Exception as e:
            logger.exception(
                "cst_save_tree failed: %s",
                e,
                extra={
                    "cst_save_stage": "execute_outer_error",
                    "project_id": project_id,
                    "tree_id": tree_id,
                    "file_path": file_path,
                    "exc_type": type(e).__name__,
                },
            )
            return ErrorResult(
                message=f"cst_save_tree failed: {e}", code="CST_SAVE_ERROR"
            )

    @classmethod
    def metadata(cls: type["CSTSaveTreeCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The cst_save_tree command saves a CST tree to a file with full atomicity guarantees. "
                "If any error occurs during the save process, all changes are rolled back and the "
                "file is restored from backup.\n\n"
                "Operation flow:\n"
                "1. Gets project from database using project_id\n"
                "2. Validates project is linked to watch directory\n"
                "3. Gets watch directory path from database\n"
                "4. Forms absolute path: watch_dir_path / project_name / file_path\n"
                "5. Validates original file (if exists) through compile()\n"
                "6. Creates backup via BackupManager (mandatory if file exists)\n"
                "7. Generates source code from CST tree\n"
                "8. Writes to temporary file\n"
                "9. Validates temporary file (compile, syntax check)\n"
                "10. Begins database transaction\n"
                "11. Atomically replaces file via os.replace()\n"
                "12. Updates database (add_file, update_file_data_atomic)\n"
                "13. Commits database transaction\n"
                "14. Creates git commit (if commit_message provided)\n"
                "15. On any error: rolls back transaction and restores from backup\n\n"
                "Atomicity Guarantees:\n"
                "- File is either completely updated or completely unchanged\n"
                "- Database is either completely updated or rolled back\n"
                "- No intermediate states are possible\n"
                "- Backup is automatically restored on any error\n\n"
                "Error Handling:\n"
                "- If validation fails: operation stops before any changes\n"
                "- Save verification (when enabled): FILE_CHANGED_SINCE_LOAD if disk bytes "
                "no longer match the snapshot from load; CST_REPLAY_MISMATCH if replaying "
                "operations on the original source does not match the working tree; "
                "WRITE_VERIFY_FAILED if the file read back after atomic replace does not "
                "match the generated source.\n"
                "- If file write fails: transaction rolled back, backup restored\n"
                "- If database update fails: transaction rolled back, backup restored\n"
                "- If git commit fails: file and database are already saved (non-critical)\n\n"
                "Use cases:\n"
                "- Save modified CST tree to file\n"
                "- Persist refactoring changes\n"
                "- Apply code transformations\n"
                "- Batch file updates with rollback safety\n\n"
                "Important notes:\n"
                "- All operations are atomic (either all succeed or all fail)\n"
                "- Backup is created before any changes\n"
                "- Database transaction ensures consistency\n"
                "- File system operation (os.replace) is atomic on most filesystems\n"
                "- Git commit is optional and non-critical (file is already saved)\n\n"
                "Recommended AI workflow:\n"
                "1. Use cst_modify_tree for in-memory changes\n"
                "2. Save with cst_save_tree\n"
                "3. Run format_code/lint_code/type_check_code on the saved file\n"
                "4. Run update_indexes after a batch of file changes"
            ),
            "parameters": {
                "tree_id": {
                    "description": "Tree ID from cst_load_file command",
                    "type": "string",
                    "required": True,
                },
                "project_id": {
                    "description": "Project ID (UUID4). Project must be linked to a watch directory.",
                    "type": "string",
                    "required": True,
                },
                "file_path": {
                    "description": "Target file path (relative to project root). Absolute path is formed as: watch_dir_path / project_name / file_path",
                    "type": "string",
                    "required": True,
                },
                "validate": {
                    "description": (
                        "Whether to validate file before saving. Default is True. "
                        "Verification failures return structured codes: FILE_CHANGED_SINCE_LOAD, "
                        "CST_REPLAY_MISMATCH, WRITE_VERIFY_FAILED."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "backup": {
                    "description": "Whether to create backup (for existing files backup is always created). Default is True.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "commit_message": {
                    "description": "Optional git commit message. If provided, creates git commit after saving.",
                    "type": "string",
                    "required": False,
                },
            },
            "return_value": {
                "success": {
                    "description": "Tree saved successfully",
                    "data": {
                        "success": "Always True on success",
                        "file_path": "Path to saved file",
                        "file_id": "File ID in database",
                        "backup_uuid": "UUID of created backup (if backup was created)",
                        "update_result": "Result from update_file_data_atomic",
                    },
                    "example": {
                        "success": True,
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "file_id": 123,
                        "backup_uuid": "backup-uuid-1234-5678",
                        "update_result": {
                            "success": True,
                            "ast_updated": True,
                            "cst_updated": True,
                            "entities_updated": 5,
                        },
                    },
                },
                "error": {
                    "description": "Save failed",
                    "data": {
                        "success": "Always False on error",
                        "file_path": "Path to file",
                        "backup_uuid": "UUID of backup (if created)",
                        "error": "Error message",
                    },
                    "example": {
                        "success": False,
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "backup_uuid": "backup-uuid-1234-5678",
                        "error": "Module validation failed: SyntaxError",
                    },
                },
            },
            "usage_examples": [
                {
                    "description": "Save tree with default options",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Saves tree to file with validation and backup enabled by default. "
                        "Absolute path is formed as: watch_dir_path / project_name / src/main.py. "
                        "File is validated, backup is created, and database is updated atomically. "
                        "If any step fails, all changes are rolled back."
                    ),
                },
                {
                    "description": "Save without validation",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/main.py",
                        "validate": False,
                    },
                    "explanation": (
                        "Saves tree without validation. Use with caution. "
                        "Backup is still created, and database is updated. "
                        "Useful when you're certain the code is valid."
                    ),
                },
                {
                    "description": "Save without backup",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/main.py",
                        "backup": False,
                    },
                    "explanation": (
                        "Saves tree without creating backup. "
                        "Use with caution - no automatic rollback if database update fails. "
                        "File is still saved atomically, but backup won't be available."
                    ),
                },
                {
                    "description": "Save with git commit",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/main.py",
                        "commit_message": "Refactor: update main function",
                    },
                    "explanation": (
                        "Saves tree and creates git commit with specified message. "
                        "Git commit is non-critical - if it fails, file and database are already saved. "
                        "Useful for tracking changes in version control."
                    ),
                },
                {
                    "description": "Save to new file",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/new_file.py",
                    },
                    "explanation": (
                        "Saves tree to a new file. No backup is created (file doesn't exist). "
                        "File is created, validated, and added to database atomically. "
                        "If any step fails, file is not created."
                    ),
                },
                {
                    "description": "Save with all options",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/main.py",
                        "validate": True,
                        "backup": True,
                        "commit_message": "Refactor: major update",
                    },
                    "explanation": (
                        "Saves tree with all options enabled. "
                        "File is validated, backup is created, database is updated, and git commit is created. "
                        "All operations are atomic - if any fails, all are rolled back (except git commit)."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "message": "Project {project_id} not found",
                    "solution": "Verify project_id is correct and project exists in database",
                },
                "FILE_CHANGED_SINCE_LOAD": {
                    "description": (
                        "On-disk file bytes no longer match the snapshot taken when the tree "
                        "was loaded (another process or editor changed the file)."
                    ),
                    "solution": (
                        "Reload with cst_load_file after resolving external changes, or save "
                        "with reconciled content."
                    ),
                },
                "CST_REPLAY_MISMATCH": {
                    "description": (
                        "Replaying recorded edits on the original source did not produce the "
                        "same code as the in-memory tree (internal consistency check)."
                    ),
                    "solution": (
                        "Reload the file and re-apply edits, or report if the issue persists."
                    ),
                },
                "WRITE_VERIFY_FAILED": {
                    "description": (
                        "After atomic replace, reading the file back did not match the "
                        "generated source (unexpected filesystem or encoding issue)."
                    ),
                    "solution": (
                        "Retry once; check disk health and concurrent writers on the same path."
                    ),
                },
                "CST_SAVE_ERROR": {
                    "description": "Error during save operation",
                    "examples": [
                        {
                            "case": "Validation fails",
                            "message": "cst_save_tree failed: Generated code has syntax errors",
                            "solution": (
                                "The CST tree produces invalid Python code. "
                                "Check tree modifications. "
                                "File is not modified, backup is not needed."
                            ),
                        },
                        {
                            "case": "Database update fails",
                            "message": "cst_save_tree failed: Failed to update file data",
                            "solution": (
                                "Database update failed. "
                                "Transaction is rolled back, file is restored from backup. "
                                "Check database connection and permissions."
                            ),
                        },
                        {
                            "case": "File write fails",
                            "message": "cst_save_tree failed: Failed to write temporary file",
                            "solution": (
                                "File system error. "
                                "Check disk space and file permissions. "
                                "No changes are made to file or database."
                            ),
                        },
                        {
                            "case": "Tree not found",
                            "message": "cst_save_tree failed: Tree not found: {tree_id}",
                            "solution": (
                                "Tree was not loaded or was removed from memory. "
                                "Use cst_load_file to load file into tree first."
                            ),
                        },
                    ],
                },
            },
            "best_practices": [
                "Always use validate=True (default) unless you're certain code is valid",
                "Always provide project_id - it is required and used to form absolute path",
                "Ensure project is linked to watch directory before using this command",
                "Use relative file_path from project root (e.g., 'src/main.py' not '/absolute/path')",
                "Always use backup=True (default) for safety",
                "Save tree immediately after modifications to avoid memory issues",
                "Check return value to ensure save was successful",
                "Use commit_message for version control integration",
                "All operations are atomic - either all succeed or all fail",
                "Backup is automatically restored on any error",
                "Database transaction ensures consistency",
                "File system operation (os.replace) is atomic on most filesystems",
            ],
        }
