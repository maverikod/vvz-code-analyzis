"""
MCP command: compose_cst_module

Applies module-level block replacements using LibCST and validates the result by
compiling the resulting module source.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.backup_manager import BackupManager
from ..core.git_integration import is_git_repository, create_git_commit
from ..core.cst_module import (
    ReplaceOp,
    InsertOp,
    CreateOp,
    Selector,
    apply_replace_ops,
    apply_insert_ops,
    apply_create_ops,
    unified_diff,
)
from ..core.cst_module.validation import validate_file_in_temp

logger = logging.getLogger(__name__)


class ComposeCSTModuleCommand(BaseMCPCommand):
    """
    Compose/patch a module using CST operations.

    This is intended for "logical blocks" workflows:
    - choose blocks (functions/classes/statements) by selectors
    - replace them with new code snippets
    - normalize imports to the top
    - validate via compile()
    - create git commits automatically (if git repository detected)

    Git Integration:
    - If root_dir is a git repository, commit_message parameter is REQUIRED
    - Automatically creates git commit with provided message after successful changes
    - Backup is created before changes, comment is stored in backup index
    """

    name = "compose_cst_module"
    version = "1.0.0"
    descr = "Replace module-level blocks using LibCST, compile the result, and optionally create git commit"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target python file path (absolute or relative to root_dir)",
                },
                "ops": {
                    "type": "array",
                    "description": "List of operations (replace/insert/create)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "operation_type": {
                                "type": "string",
                                "enum": ["replace", "insert", "create"],
                                "default": "replace",
                                "description": "Type of operation: replace (default), insert (add before/after), create (create new node)",
                            },
                            "selector": {
                                "type": ["object", "null"],
                                "description": "Selector for target node (null for insert/create at end)",
                                "properties": {
                                    "kind": {
                                        "type": "string",
                                        "enum": [
                                            "module",
                                            "function",
                                            "class",
                                            "method",
                                            "range",
                                            "block_id",
                                            "node_id",
                                            "cst_query",
                                        ],
                                    },
                                    "name": {"type": "string"},
                                    "start_line": {"type": "integer"},
                                    "start_col": {"type": "integer"},
                                    "end_line": {"type": "integer"},
                                    "end_col": {"type": "integer"},
                                    "block_id": {"type": "string"},
                                    "node_id": {"type": "string"},
                                    "query": {"type": "string"},
                                    "match_index": {"type": "integer"},
                                },
                                "required": ["kind"],
                                "additionalProperties": False,
                            },
                            "new_code": {
                                "type": "string",
                                "description": "Code snippet: for replace (replacement, empty=delete), for insert/create (new node code)",
                            },
                            "position": {
                                "type": "string",
                                "enum": [
                                    "before",
                                    "after",
                                    "end",
                                    "end_of_module",
                                    "after_selector",
                                    "before_selector",
                                    "end_of_class",
                                    "end_of_function",
                                ],
                                "default": "after",
                                "description": "Position for insert/create: before/after/end (insert), end_of_module/after_selector/before_selector/end_of_class/end_of_function (create)",
                            },
                            "file_docstring": {
                                "type": "string",
                                "description": "Required when kind='module': file-level docstring",
                            },
                        },
                        "required": ["new_code"],
                        "allOf": [
                            {
                                "if": {
                                    "properties": {
                                        "selector": {
                                            "properties": {"kind": {"const": "module"}}
                                        }
                                    }
                                },
                                "then": {
                                    "required": ["file_docstring", "new_code"],
                                    "properties": {
                                        "file_docstring": {
                                            "type": "string",
                                            "minLength": 1,
                                            "description": "File-level docstring (required and must not be empty for module creation)",
                                        },
                                        "new_code": {
                                            "type": "string",
                                            "minLength": 1,
                                            "description": "First node code - function or class (required and must not be empty for module creation)",
                                        },
                                    },
                                },
                            }
                        ],
                        "additionalProperties": False,
                    },
                },
                "apply": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, write changes to file (after successful compile)",
                },
                "create_backup": {
                    "type": "boolean",
                    "default": True,
                    "description": "If apply=true, create a backup in .code_mapper_backups",
                },
                "return_source": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, return the resulting source text (can be large)",
                },
                "return_diff": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, return unified diff",
                },
                "commit_message": {
                    "type": "string",
                    "description": (
                        "Commit message for git commit. "
                        "REQUIRED if root_dir is a git repository. "
                        "If provided and root_dir is a git repository, automatically creates a git commit "
                        "with this message after successfully applying changes. "
                        "The message is also stored in backup index for version history tracking."
                    ),
                },
            },
            "required": ["root_dir", "file_path", "ops"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        ops: list[dict[str, Any]],
        apply: bool = False,
        create_backup: bool = True,
        return_source: bool = False,
        return_diff: bool = True,
        commit_message: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = self._validate_root_dir(root_dir)

            # Check if git repository and validate commit_message
            is_git = is_git_repository(root_path)
            if is_git and not commit_message:
                return ErrorResult(
                    message="commit_message is required when working in a git repository",
                    code="COMMIT_MESSAGE_REQUIRED",
                    details={"root_dir": str(root_path)},
                )

            # Resolve file path (may not exist if creating new file)
            target = Path(file_path)
            if not target.is_absolute():
                target = root_path / target
            target = target.resolve()

            if target.suffix != ".py":
                return ErrorResult(
                    message="Target file must be a .py file",
                    code="INVALID_FILE",
                    details={"file_path": str(target)},
                )

            # Handle file creation from scratch
            if not target.exists():
                # Check if we have a "module" selector to create from scratch
                has_module_selector = any(
                    op.get("selector", {}).get("kind") == "module" for op in ops
                )
                if has_module_selector:
                    # Create module from scratch
                    old_source = ""
                else:
                    return ErrorResult(
                        message=(
                            "Target file does not exist. "
                            "To create a new file, use selector with kind='module'"
                        ),
                        code="FILE_NOT_FOUND",
                        details={"file_path": str(target)},
                    )
            else:
                old_source = target.read_text(encoding="utf-8")

            # Separate operations by type
            replace_ops: list[ReplaceOp] = []
            insert_ops: list[InsertOp] = []
            create_ops: list[CreateOp] = []

            for op in ops:
                op_type = op.get("operation_type", "replace")
                sel_dict = op.get("selector")

                selector = None
                if sel_dict:
                    selector = Selector(
                        kind=str(sel_dict.get("kind")),
                        name=sel_dict.get("name"),
                        start_line=sel_dict.get("start_line"),
                        start_col=sel_dict.get("start_col"),
                        end_line=sel_dict.get("end_line"),
                        end_col=sel_dict.get("end_col"),
                        block_id=sel_dict.get("block_id"),
                        node_id=sel_dict.get("node_id"),
                        query=sel_dict.get("query"),
                        match_index=sel_dict.get("match_index"),
                    )

                new_code = str(op.get("new_code", ""))
                position = op.get("position", "after")
                file_docstring = op.get("file_docstring")

                if op_type == "replace":
                    if selector is None:
                        return ErrorResult(
                            message="Selector is required for replace operation",
                            code="INVALID_OPERATION",
                            details={"operation_type": op_type},
                        )
                    replace_ops.append(
                        ReplaceOp(
                            selector=selector,
                            new_code=new_code,
                            file_docstring=file_docstring,
                        )
                    )
                elif op_type == "insert":
                    insert_ops.append(
                        InsertOp(
                            selector=selector,
                            new_code=new_code,
                            position=position,
                            file_docstring=file_docstring,
                        )
                    )
                elif op_type == "create":
                    create_ops.append(
                        CreateOp(
                            selector=selector,
                            new_code=new_code,
                            position=position,
                            file_docstring=file_docstring,
                        )
                    )
                else:
                    return ErrorResult(
                        message=f"Unknown operation type: {op_type}",
                        code="INVALID_OPERATION",
                        details={"operation_type": op_type},
                    )

            # Apply operations in order: replace, then insert, then create
            current_source = old_source
            all_stats: dict[str, Any] = {
                "replaced": 0,
                "removed": 0,
                "inserted": 0,
                "created": 0,
                "unmatched": [],
            }

            if replace_ops:
                current_source, replace_stats = apply_replace_ops(
                    current_source, replace_ops
                )
                all_stats["replaced"] = replace_stats.get("replaced", 0)
                all_stats["removed"] = replace_stats.get("removed", 0)
                all_stats["unmatched"].extend(replace_stats.get("unmatched", []))

            if insert_ops:
                current_source, insert_stats = apply_insert_ops(
                    current_source, insert_ops
                )
                all_stats["inserted"] = insert_stats.get("inserted", 0)
                all_stats["unmatched"].extend(insert_stats.get("unmatched", []))

            if create_ops:
                current_source, create_stats = apply_create_ops(
                    current_source, create_ops
                )
                all_stats["created"] = create_stats.get("created", 0)
                all_stats["unmatched"].extend(create_stats.get("unmatched", []))

            new_source = current_source
            stats = all_stats

            # Create temporary file for validation
            import tempfile
            import shutil

            tmp_path = None
            tmp_path_moved = False

            try:
                # Create temporary file
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", delete=False, encoding="utf-8"
                ) as tmp_file:
                    tmp_file.write(new_source)
                    tmp_path = Path(tmp_file.name)

                # Validate entire file in temporary file
                validation_success, validation_error, validation_results = (
                    validate_file_in_temp(
                        source_code=new_source,
                        temp_file_path=tmp_path,
                        validate_linter=True,
                        validate_type_checker=True,
                    )
                )

                if not validation_success:
                    # Return error with validation details
                    payload: dict[str, Any] = {
                        "success": False,
                        "message": validation_error or "Validation failed",
                        "validation_results": {
                            k: {
                                "success": v.success,
                                "error_message": v.error_message,
                                "errors": v.errors,
                            }
                            for k, v in validation_results.items()
                        },
                        "stats": stats,
                    }
                    if return_diff:
                        payload["diff"] = unified_diff(
                            old_source, new_source, str(target)
                        )
                    if return_source:
                        payload["source"] = new_source
                    return ErrorResult(
                        message=validation_error or "Validation failed",
                        code="VALIDATION_ERROR",
                        details=payload,
                    )

                # Validation passed - temporary file is ready
                # If apply=True, we will move it to target location and add to database in transaction
                logger.info(
                    f"Validation passed. Temporary file ready: {tmp_path}, "
                    f"apply={apply}, target={target}"
                )
            except Exception as e:
                logger.error(f"Error during validation: {e}", exc_info=True)
                # Clean up temporary file if it exists
                if tmp_path and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                return ErrorResult(
                    message=f"Validation error: {e}",
                    code="VALIDATION_ERROR",
                    details={"stats": stats},
                )

            backup_uuid = None
            git_commit_success = False
            git_error = None
            file_created_in_this_session = (
                False  # Track if file was created in this session
            )

            if apply:
                # Verify temporary file exists before proceeding
                if not tmp_path or not tmp_path.exists():
                    return ErrorResult(
                        message=(
                            "Temporary file does not exist after validation. "
                            "This should not happen if validation passed."
                        ),
                        code="TEMP_FILE_MISSING",
                        details={"tmp_path": str(tmp_path) if tmp_path else None},
                    )

                # Begin transaction and atomic update process
                database = self._open_database(str(root_path), auto_analyze=False)
                backup_manager = None

                try:
                    # Create backup using BackupManager before applying changes (if file exists)
                    if target.exists():
                        backup_manager = BackupManager(root_path)
                        # Extract related files from ops (files mentioned in selectors)
                        related_files = []
                        for op in ops:
                            selector = op.get("selector", {})
                            name = selector.get("name", "")
                            if name and "." in name:
                                # Extract class/module name from selector
                                parts = name.split(".")
                                if len(parts) > 1:
                                    related_files.append(parts[0])

                        backup_uuid = backup_manager.create_backup(
                            target,
                            command="compose_cst_module",
                            related_files=related_files if related_files else None,
                            comment=commit_message or "",
                        )
                        if backup_uuid:
                            logger.info(
                                f"Backup created before CST compose: {backup_uuid}"
                            )

                    # Begin transaction
                    database.begin_transaction()

                    # Update database in transaction
                    project_id = self._get_project_id(
                        database, root_path, kwargs.get("project_id")
                    )
                    if project_id:
                        try:
                            rel_path = str(target.relative_to(root_path))
                        except ValueError:
                            rel_path = str(target)

                        # Step 1: Move temporary file to target location
                        # This ensures file exists on disk for add_file() validation
                        abs_path = target.resolve()
                        file_existed_before = target.exists()

                        # Ensure target directory exists
                        target.parent.mkdir(parents=True, exist_ok=True)

                        # Move temporary file to target (creates or overwrites)
                        shutil.move(str(tmp_path), str(target))
                        tmp_path_moved = True
                        if not file_existed_before:
                            file_created_in_this_session = True

                        # Step 2: Check if file exists in database, add if needed
                        file_record = database.get_file_by_path(
                            str(abs_path), project_id
                        )
                        if not file_record:
                            file_record = database.get_file_by_path(
                                rel_path, project_id
                            )

                        if not file_record:
                            # File doesn't exist in database - add it
                            import time

                            dataset_id = database.get_or_create_dataset(
                                project_id=project_id,
                                root_path=str(root_path),
                            )
                            lines = len(new_source.splitlines())
                            file_mtime = time.time()
                            has_docstring = new_source.strip().startswith(
                                '"""'
                            ) or new_source.strip().startswith("'''")
                            database.add_file(
                                path=rel_path,
                                lines=lines,
                                last_modified=file_mtime,
                                has_docstring=has_docstring,
                                project_id=project_id,
                                dataset_id=dataset_id,
                            )

                        # Step 3: Update database atomically (AST, CST, entities)
                        update_result = database.update_file_data_atomic(
                            file_path=str(abs_path),
                            project_id=project_id,
                            root_dir=root_path,
                            source_code=new_source,
                        )

                        if not update_result.get("success"):
                            raise Exception(
                                f"Failed to update database: {update_result.get('error')}"
                            )

                        # Commit transaction (BEFORE git commit)
                        database.commit_transaction()

                        # Git commit after successful transaction (if git repository and commit_message provided)
                        if is_git and commit_message:
                            git_commit_success, git_error = create_git_commit(
                                root_path, target, commit_message
                            )
                            if not git_commit_success:
                                # Git commit is not critical - transaction already committed
                                logger.warning(
                                    f"Failed to create git commit: {git_error}"
                                )
                            else:
                                logger.info(
                                    f"Git commit created successfully: {commit_message}"
                                )

                        logger.info(
                            f"Database updated after CST compose: "
                            f"AST={update_result.get('ast_updated')}, "
                            f"CST={update_result.get('cst_updated')}, "
                            f"entities={update_result.get('entities_updated')}"
                        )

                except Exception:
                    # Rollback transaction on error
                    try:
                        database.rollback_transaction()
                    except Exception:
                        pass

                    # If file was created on disk but error occurred, remove it
                    # Only remove if it was created in this session
                    # TEMPORARILY DISABLED for debugging - to see if file is created
                    # if file_created_in_this_session and target.exists():
                    #     try:
                    #         # Check if file is empty or was just created
                    #         file_size = target.stat().st_size
                    #         logger.info(
                    #             f"Removing newly created file due to error: {target}, size: {file_size} bytes"
                    #         )
                    #         target.unlink()
                    #         logger.info(f"Removed newly created file: {target}")
                    #     except Exception as remove_error:
                    #         logger.error(
                    #             f"Failed to remove newly created file: {remove_error}",
                    #             exc_info=True,
                    #         )
                    if file_created_in_this_session and target.exists():
                        logger.warning(
                            f"File was created but error occurred. Keeping file for debugging: {target}"
                        )

                    # Restore file from backup if backup was created
                    if backup_uuid and backup_manager and target.exists():
                        try:
                            try:
                                rel_path = str(target.relative_to(root_path))
                            except ValueError:
                                rel_path = str(target)

                            restore_success, restore_message = (
                                backup_manager.restore_file(rel_path, backup_uuid)
                            )
                            if restore_success:
                                logger.info(
                                    f"File restored from backup: {restore_message}"
                                )
                            else:
                                logger.error(
                                    f"Failed to restore file from backup: {restore_message}"
                                )
                        except Exception as restore_error:
                            logger.error(
                                f"Failed to restore backup: {restore_error}",
                                exc_info=True,
                            )

                    raise

                finally:
                    database.close()

                    # Clean up temporary file only if it wasn't moved
                    if not tmp_path_moved and tmp_path and tmp_path.exists():
                        tmp_path.unlink(missing_ok=True)

            data: dict[str, Any] = {
                "success": True,
                "message": (
                    "CST patch applied successfully"
                    if apply
                    else "CST patch preview generated"
                ),
                "file_path": str(target),
                "applied": apply,
                "backup_uuid": backup_uuid,
                "compiled": True,
                "stats": stats,
            }

            # Add git commit info if applicable
            if is_git:
                data["git_commit"] = {
                    "success": git_commit_success,
                    "error": git_error,
                }
            if return_diff:
                data["diff"] = unified_diff(old_source, new_source, str(target))
            if return_source:
                data["source"] = new_source

            return SuccessResult(data=data)
        except Exception as e:
            return self._handle_error(e, "CST_COMPOSE_ERROR", "compose_cst_module")

    @classmethod
    def metadata(cls: type["ComposeCSTModuleCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

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
                "The compose_cst_module command applies module-level block replacements using LibCST "
                "and validates the result by compiling the resulting module source. "
                "This command provides atomic, transaction-safe file modifications with comprehensive validation.\n\n"
                "DETAILED OPERATION FLOW:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Resolves file_path (absolute or relative to root_dir)\n"
                "3. Checks if root_dir is a git repository using is_git_repository()\n"
                "4. If git repository detected (is_git=True), validates commit_message is provided\n"
                "   - If commit_message is missing, returns COMMIT_MESSAGE_REQUIRED error immediately\n"
                "   - Operation does not proceed if commit_message is required but missing\n"
                "5. Loads existing source code (or empty string for new files with kind='module')\n"
                "6. Applies CST operations (replace/insert/create) in order:\n"
                "   - Replace operations are applied first\n"
                "   - Insert operations are applied second\n"
                "   - Create operations are applied last\n"
                "7. Creates temporary file with new source code\n"
                "8. Validates ENTIRE file in temporary file (not original):\n"
                "   - Compilation check (syntax validation via compile_module)\n"
                "   - Docstring validation (file, class, method, function level)\n"
                "   - Linter check (flake8) - optional, enabled by default\n"
                "   - Type checker (mypy) - optional, enabled by default\n"
                "9. If validation fails, returns VALIDATION_ERROR with detailed results\n"
                "10. If apply=true and validation succeeds:\n"
                "    - Creates backup using BackupManager (stored in {root_dir}/old_code/ with UUID)\n"
                "    - Backup includes comment (commit_message if provided) for history tracking\n"
                "    - Begins database transaction\n"
                "    - Updates database atomically (AST, CST, entities) using update_file_data_atomic\n"
                "    - Atomically moves temporary file to target location\n"
                "    - Commits database transaction\n"
                "    - If git repository and commit_message provided, creates git commit\n"
                "    - Git commit is performed AFTER successful transaction commit\n"
                "    - If git commit fails, operation still succeeds (data is saved, transaction committed)\n"
                "11. If any error occurs during apply:\n"
                "    - Database transaction is rolled back\n"
                "    - File is restored from backup (if backup was created)\n"
                "    - Temporary file is cleaned up\n"
                "\n"
                "ATOMICITY AND TRANSACTIONS:\n"
                "All database operations are performed within a transaction to ensure atomicity:\n"
                "- Database transaction begins before any updates\n"
                "- All file data (AST, CST, entities) is updated atomically\n"
                "- If any error occurs, transaction is rolled back\n"
                "- File is only moved after successful database update\n"
                "- Transaction is committed before git commit (git commit is not part of transaction)\n"
                "\n"
                "VALIDATION PROCESS:\n"
                "Validation is performed on the ENTIRE file in a temporary location:\n"
                "- Compilation: Checks Python syntax via compile_module()\n"
                "- Docstrings: Validates file, class, method, and function docstrings\n"
                "- Linter: Runs flake8 on entire file (can be disabled with validate_linter=False)\n"
                "- Type Checker: Runs mypy on entire file (can be disabled with validate_type_checker=False)\n"
                "- Validation results include detailed error messages for each type\n"
                "- If compilation fails, other validations are skipped\n"
                "\n"
                "BACKUP SYSTEM:\n"
                "Uses BackupManager for file backups:\n"
                "- Backup is stored in {root_dir}/old_code/ directory with UUID\n"
                "- Backup includes metadata: command name, comment (commit_message), timestamp\n"
                "- Backup is created BEFORE applying changes\n"
                "- If operation fails, file is automatically restored from backup\n"
                "- Backup UUID is returned in response for tracking\n"
                "- Old system (write_with_backup) is NOT used in this command\n"
                "\n"
                "GIT INTEGRATION:\n"
                "Automatic git repository detection and commit creation:\n"
                "- Automatically detects if root_dir is a git repository\n"
                "- If git repository detected (is_git=True), commit_message becomes REQUIRED\n"
                "- commit_message validation happens at the START of execute(), before any operations\n"
                "- If commit_message is missing in git repository, operation fails immediately\n"
                "- Git commit is created AFTER successful database transaction commit\n"
                "- Git commit stages the modified file and creates commit with provided message\n"
                "- If git commit fails, operation still succeeds (data is saved, transaction committed)\n"
                "- Git commit error is logged as warning and returned in response\n"
                "- If root_dir is NOT a git repository (is_git=False):\n"
                "  - commit_message is optional and ignored\n"
                "  - Git commit is not performed\n"
                "  - Operation succeeds normally (data is saved)\n"
                "\n"
                "SAFETY FEATURES:\n"
                "- Comprehensive validation before file modification\n"
                "- Automatic backup creation before changes\n"
                "- Database transactions for atomicity\n"
                "- Automatic rollback on any error\n"
                "- File restoration from backup on error\n"
                "- Temporary file cleanup in all cases\n"
                "- Preview mode (apply=false) to see changes without modifying file\n"
                "- Import normalization (moves imports to top)\n"
                "\n"
                "IMPORTANT NOTES:\n"
                "- commit_message is REQUIRED when working in git repository (is_git=True)\n"
                "- Operations preserve code formatting and comments\n"
                "- Can create new files from scratch (use selector with kind='module')\n"
                "  * For new files: operation_type='create', selector.kind='module', position='end_of_module' REQUIRED\n"
                "  * file_docstring is REQUIRED and must be non-empty for new files\n"
                "  * new_code must include file docstring at the beginning (matching file_docstring)\n"
                "  * new_code must contain at least one function or class (cannot be empty)\n"
                "- Can delete code blocks (use empty new_code string)\n"
                "- Backup UUID and git commit status are returned in response\n"
                "- All operations are atomic: either all succeed or all fail\n"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "This directory is checked for git repository status. "
                        "If it is a git repository (detected via is_git_repository()), "
                        "commit_message parameter becomes REQUIRED. "
                        "Database file (code_analysis.db) is expected in this directory. "
                        "Backup directory (old_code/) is created in this directory."
                    ),
                },
                "file_path": {
                    "description": (
                        "Target Python file path. Can be absolute or relative to root_dir. "
                        "If file does not exist, use selector with kind='module' to create new file. "
                        "File must have .py extension. "
                        "For new files, old_source is empty string and operations create file from scratch."
                    ),
                },
                "ops": {
                    "description": (
                        "List of CST operations to apply. Operations are applied in order: "
                        "replace operations first, then insert operations, then create operations. "
                        "Each operation can target different code blocks using selectors. "
                        "Selector types: module, function, class, method, range, block_id, node_id, cst_query. "
                        "Operation types: replace (default), insert, create. "
                        "For replace: new_code replaces selected block (empty string deletes). "
                        "For insert: new_code is inserted before/after selected block. "
                        "For create: new_code creates new node at specified position.\n\n"
                        "CREATING NEW FILES (file does not exist):\n"
                        "- Use operation_type='create' with selector.kind='module'\n"
                        "- position='end_of_module' is REQUIRED for new files\n"
                        "- file_docstring is REQUIRED and must be non-empty (minLength=1)\n"
                        "- new_code is REQUIRED and must be non-empty (minLength=1)\n"
                        "- new_code must include file docstring at the beginning (matching file_docstring)\n"
                        "- new_code must contain at least one function or class\n"
                        '- Example: {"operation_type": "create", "selector": {"kind": "module"}, '
                        '"position": "end_of_module", "file_docstring": "File docstring", '
                        '"new_code": \'"""File docstring"""\\n\\ndef main():\\n    pass\'}'
                    ),
                },
                "apply": {
                    "description": (
                        "If true, writes changes to file after successful validation. "
                        "Process includes: backup creation, database transaction, file update, git commit. "
                        "If false, only returns preview (diff, source) without modifying file or database. "
                        "Preview mode is safe and does not require commit_message even in git repository."
                    ),
                },
                "create_backup": {
                    "description": (
                        "If true and apply=true, creates backup using BackupManager. "
                        "Backup is stored in {root_dir}/old_code/ directory with UUID. "
                        "Backup includes metadata: command name, comment (commit_message if provided), timestamp. "
                        "Backup is created BEFORE applying changes. "
                        "If operation fails, file is automatically restored from backup. "
                        "Backup UUID is returned in response for tracking."
                    ),
                },
                "commit_message": {
                    "description": (
                        "Commit message for git commit. "
                        "REQUIRED if root_dir is a git repository (is_git=True). "
                        "If root_dir is a git repository and commit_message is missing, "
                        "operation fails immediately with COMMIT_MESSAGE_REQUIRED error. "
                        "If provided and root_dir is a git repository, automatically creates a git commit "
                        "with this message after successfully applying changes and committing database transaction. "
                        "The message is also stored in backup index for version history tracking. "
                        "If root_dir is NOT a git repository (is_git=False), this parameter is optional and ignored. "
                        "Git commit is performed AFTER database transaction commit. "
                        "If git commit fails, operation still succeeds (data is saved)."
                    ),
                },
                "return_diff": {
                    "description": (
                        "If true, includes unified diff in response showing changes made to the file. "
                        "Diff format is standard unified diff (like git diff). "
                        "Useful for previewing changes before applying (apply=false)."
                    ),
                },
                "return_source": {
                    "description": (
                        "If true, includes full resulting source code in response. "
                        "Can be large for big files. "
                        "Useful for previewing complete result or for further processing."
                    ),
                },
            },
            "examples": [
                {
                    "description": "Preview changes without applying (apply=false, no commit_message needed)",
                    "code": {
                        "root_dir": "/path/to/project",
                        "file_path": "code_analysis/main.py",
                        "ops": [
                            {
                                "operation_type": "replace",
                                "selector": {"kind": "function", "name": "my_function"},
                                "new_code": 'def my_function(param: int) -> str:\n    """Updated function."""\n    return str(param)',
                            }
                        ],
                        "apply": False,
                        "return_diff": True,
                        "return_source": False,
                    },
                },
                {
                    "description": "Apply changes in git repository (commit_message REQUIRED)",
                    "code": {
                        "root_dir": "/path/to/project",
                        "file_path": "code_analysis/main.py",
                        "ops": [
                            {
                                "operation_type": "replace",
                                "selector": {"kind": "function", "name": "my_function"},
                                "new_code": 'def my_function(param: int) -> str:\n    """Updated function."""\n    return str(param)',
                            }
                        ],
                        "apply": True,
                        "commit_message": "Refactor: update my_function signature and return type",
                    },
                },
                {
                    "description": "Apply changes WITHOUT git repository (commit_message optional)",
                    "code": {
                        "root_dir": "/path/to/project",
                        "file_path": "code_analysis/main.py",
                        "ops": [
                            {
                                "operation_type": "replace",
                                "selector": {"kind": "function", "name": "my_function"},
                                "new_code": 'def my_function(param: int) -> str:\n    """Updated function."""\n    return str(param)',
                            }
                        ],
                        "apply": True,
                        # commit_message not required, git commit not performed
                    },
                },
                {
                    "description": "Create new file from scratch (kind='module') - REQUIRES position='end_of_module'",
                    "code": {
                        "root_dir": "/path/to/project",
                        "file_path": "new_module.py",
                        "ops": [
                            {
                                "operation_type": "create",
                                "selector": {"kind": "module"},
                                "position": "end_of_module",
                                "file_docstring": "New module for testing.\n\nAuthor: Vasiliy Zdanovskiy\nemail: vasilyvz@gmail.com",
                                "new_code": 'class NewClass:\n    """Class description."""\n    \n    def __init__(self):\n        """Initialize."""\n        pass',
                            }
                        ],
                        "apply": True,
                        "commit_message": "Add new module with NewClass",
                    },
                    "note": "CRITICAL: When creating new file, position='end_of_module' is REQUIRED. file_docstring must be non-empty. new_code must contain at least one function or class.",
                },
                {
                    "description": "Create new file with main() entry point (complete example)",
                    "code": {
                        "root_dir": "/path/to/project",
                        "file_path": "main.py",
                        "ops": [
                            {
                                "operation_type": "create",
                                "selector": {"kind": "module"},
                                "position": "end_of_module",
                                "file_docstring": "Main entry point for application.\n\nAuthor: Vasiliy Zdanovskiy\nemail: vasilyvz@gmail.com",
                                "new_code": '"""\nMain entry point for application.\n\nAuthor: Vasiliy Zdanovskiy\nemail: vasilyvz@gmail.com\n"""\n\nfrom __future__ import annotations\n\nimport sys\nfrom local_module import connect  # type: ignore[import-not-found]\n\n\ndef main() -> int:\n    """\n    Main entry point for the application.\n    \n    Returns:\n        Exit code (0 for success, non-zero for error).\n    """\n    try:\n        api = connect()\n        print(f"Version: {api.info(\'version\')}")\n        return 0\n    except Exception as e:\n        print(f"Error: {e}", file=sys.stderr)\n        return 1\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n',
                            }
                        ],
                        "apply": True,
                        "commit_message": "Add main entry point with main() function",
                    },
                    "note": "When creating new file: 1) file_docstring is REQUIRED and must match docstring in new_code, 2) position='end_of_module' is REQUIRED, 3) new_code must include file docstring at the beginning, 4) Use type: ignore comments for local imports if mypy validation fails",
                },
                {
                    "description": "Multiple operations (replace + insert + create)",
                    "code": {
                        "root_dir": "/path/to/project",
                        "file_path": "code_analysis/main.py",
                        "ops": [
                            {
                                "operation_type": "replace",
                                "selector": {
                                    "kind": "function",
                                    "name": "old_function",
                                },
                                "new_code": 'def old_function() -> None:\n    """Updated old function."""\n    pass',
                            },
                            {
                                "operation_type": "insert",
                                "selector": {
                                    "kind": "function",
                                    "name": "old_function",
                                },
                                "position": "after",
                                "new_code": 'def new_helper() -> str:\n    """Helper function."""\n    return "help"',
                            },
                            {
                                "operation_type": "create",
                                "selector": {"kind": "module"},
                                "position": "end_of_module",
                                "new_code": 'def module_level_function() -> int:\n    """Module level function."""\n    return 42',
                            },
                        ],
                        "apply": True,
                        "commit_message": "Refactor: update old_function, add helpers",
                    },
                },
                {
                    "description": "Handle validation errors (syntax error in new_code)",
                    "code": {
                        "root_dir": "/path/to/project",
                        "file_path": "code_analysis/main.py",
                        "ops": [
                            {
                                "operation_type": "replace",
                                "selector": {"kind": "function", "name": "my_function"},
                                "new_code": "def my_function(:  # Invalid syntax - missing closing parenthesis",
                            }
                        ],
                        "apply": True,
                        "commit_message": "Fix function",
                    },
                    "note": "This will return VALIDATION_ERROR with detailed compilation error. File is not modified.",
                },
                {
                    "description": "Delete code block (empty new_code)",
                    "code": {
                        "root_dir": "/path/to/project",
                        "file_path": "code_analysis/main.py",
                        "ops": [
                            {
                                "operation_type": "replace",
                                "selector": {
                                    "kind": "function",
                                    "name": "deprecated_function",
                                },
                                "new_code": "",  # Empty string deletes the function
                            }
                        ],
                        "apply": True,
                        "commit_message": "Remove deprecated_function",
                    },
                },
            ],
            "error_codes": {
                "COMMIT_MESSAGE_REQUIRED": {
                    "description": (
                        "commit_message is required when working in a git repository. "
                        "This error occurs when root_dir is detected as a git repository (is_git=True) "
                        "but commit_message parameter is not provided."
                    ),
                    "when_occurs": "is_git=True and commit_message is None or empty",
                    "how_to_fix": "Provide commit_message parameter when working in git repository",
                    "example": "commit_message is required when working in a git repository",
                },
                "VALIDATION_ERROR": {
                    "description": (
                        "File validation failed. This includes compilation, docstring, linter, or type checker errors. "
                        "Validation is performed on the ENTIRE file in a temporary location before any changes are applied."
                    ),
                    "when_occurs": "Any validation step fails (compilation, docstrings, linter, type checker)",
                    "types": {
                        "compile": "Compilation/syntax errors",
                        "docstrings": "Missing or invalid docstrings",
                        "linter": "Flake8 linting errors",
                        "type_checker": "Mypy type checking errors",
                    },
                    "response_structure": "validation_results dictionary with details for each validation type",
                    "how_to_fix": "Fix errors reported in validation_results and retry",
                    "example": "Compilation failed: SyntaxError: invalid syntax at line 10",
                },
                "COMPILE_ERROR": {
                    "description": "Compilation failed after CST patch. Python syntax error in resulting code.",
                    "when_occurs": "Syntax errors, indentation errors, or other Python parsing errors",
                    "causes": [
                        "Syntax errors: missing parentheses, brackets, quotes",
                        "Indentation errors: inconsistent indentation",
                        "Invalid Python syntax in new_code",
                    ],
                    "how_to_fix": "Fix syntax errors in new_code or operations",
                    "examples": [
                        "SyntaxError: invalid syntax",
                        "IndentationError: expected an indented block",
                        "SyntaxError: unexpected EOF while parsing",
                    ],
                },
                "DOCSTRING_VALIDATION_ERROR": {
                    "description": (
                        "Docstring validation failed. File, class, method, or function is missing required docstring "
                        "or docstring format is invalid."
                    ),
                    "when_occurs": "Missing or invalid docstrings in file, classes, methods, or functions",
                    "requirements": {
                        "file": "File-level docstring with Author and email",
                        "classes": "Class docstring",
                        "methods": "Method docstring",
                        "functions": "Function docstring",
                    },
                    "how_to_fix": "Add or fix docstrings according to project standards",
                    "example": "Missing docstring for function 'my_function' at line 10",
                },
                "LINTER_ERROR": {
                    "description": "Linter (flake8) errors found in validated file.",
                    "when_occurs": "Flake8 detects code quality issues",
                    "types": {
                        "E": "Error (syntax, indentation, etc.)",
                        "W": "Warning (code style)",
                        "F": "Pyflakes errors (unused imports, undefined names, etc.)",
                    },
                    "examples": [
                        "E501: line too long (80 > 79 characters)",
                        "F401: 'os' imported but unused",
                        "E302: expected 2 blank lines, found 1",
                    ],
                    "how_to_fix": "Fix linter errors according to flake8 rules",
                },
                "TYPE_CHECK_ERROR": {
                    "description": "Type checker (mypy) errors found in validated file.",
                    "when_occurs": "Mypy detects type inconsistencies or missing type annotations",
                    "types": [
                        "Incompatible types in assignment",
                        "Missing type annotation",
                        "Incompatible return type",
                        "Unsupported operand types",
                    ],
                    "examples": [
                        "Incompatible types in assignment: expected 'int', got 'str'",
                        "Missing return type annotation",
                        "Incompatible return type: expected 'int', got 'str'",
                    ],
                    "how_to_fix": "Fix type errors according to mypy requirements",
                },
                "TRANSACTION_ERROR": {
                    "description": "Database transaction error. Internal error in transaction management.",
                    "when_occurs": "Transaction management issues (nested transactions, commit without begin, etc.)",
                    "errors": [
                        "Transaction already active: attempting to begin transaction while one is active",
                        "No active transaction: attempting to commit/rollback without active transaction",
                    ],
                    "how_to_fix": "This is an internal error. Check transaction usage in code.",
                },
                "BACKUP_ERROR": {
                    "description": "Error creating or restoring backup file.",
                    "when_occurs": "BackupManager fails to create or restore backup",
                    "causes": [
                        "File not found",
                        "Permission denied",
                        "Disk space full",
                        "Invalid backup UUID",
                    ],
                    "how_to_fix": "Check file permissions, disk space, and backup directory access",
                },
                "GIT_COMMIT_ERROR": {
                    "description": (
                        "Error creating git commit. This is NOT critical - operation still succeeds, "
                        "data is saved, transaction is committed. Git commit is performed after successful transaction."
                    ),
                    "when_occurs": "Git commit fails after successful file update and database transaction",
                    "causes": [
                        "Failed to stage file",
                        "Failed to create commit",
                        "Git repository corruption",
                        "Permission denied",
                    ],
                    "important": "Operation is still considered successful. Data is saved, transaction committed.",
                    "how_to_fix": "Check git repository status, permissions, and manually create commit if needed",
                },
                "FILE_NOT_FOUND": {
                    "description": "Target file does not exist and no module creation operation provided.",
                    "when_occurs": "file_path does not exist and no operation has selector with kind='module'",
                    "how_to_fix": "Use selector with kind='module' to create new file, or provide existing file path",
                },
                "INVALID_FILE": {
                    "description": "Target file is not a Python file (.py extension required).",
                    "when_occurs": "file_path does not have .py extension",
                    "how_to_fix": "Use .py file extension",
                },
                "INVALID_OPERATION": {
                    "description": "Unknown or invalid operation type or selector.",
                    "when_occurs": "Invalid operation_type or selector configuration",
                    "how_to_fix": "Use valid operation types (replace, insert, create) and valid selector kinds",
                },
            },
            "git_integration": {
                "automatic_detection": (
                    "Git repository is automatically detected using is_git_repository(root_dir). "
                    "Checks for .git directory or git config in root_dir."
                ),
                "commit_message_requirement": (
                    "If git repository is detected (is_git=True), commit_message becomes REQUIRED. "
                    "Validation happens at the START of execute() method, before any operations. "
                    "If commit_message is missing, operation fails immediately with COMMIT_MESSAGE_REQUIRED error."
                ),
                "commit_process": (
                    "Git commit is created AFTER successful database transaction commit. "
                    "Process: 1) File is updated, 2) Database transaction is committed, 3) Git commit is created. "
                    "Git commit stages the modified file and creates commit with provided message."
                ),
                "error_handling": (
                    "If git commit fails, operation still succeeds. "
                    "Data is saved, database transaction is committed, file is updated. "
                    "Git commit error is logged as warning and returned in response. "
                    "User can manually create commit if needed."
                ),
                "without_git": (
                    "If root_dir is NOT a git repository (is_git=False): "
                    "commit_message is optional and ignored, git commit is not performed, "
                    "operation succeeds normally (data is saved)."
                ),
                "examples": {
                    "with_git": "root_dir is git repo → commit_message REQUIRED → git commit created after success",
                    "without_git": "root_dir is not git repo → commit_message optional → no git commit",
                },
            },
            "atomicity": {
                "database_transactions": (
                    "All database operations are performed within a transaction. "
                    "Transaction begins before updates, commits after successful file update. "
                    "If any error occurs, transaction is rolled back."
                ),
                "validation_in_temp": (
                    "Validation is performed on ENTIRE file in temporary file, not original. "
                    "This ensures validation happens before any changes to original file."
                ),
                "atomic_file_move": (
                    "File is moved atomically using temporary file and backup. "
                    "Process: 1) Create temp file with new content, 2) Validate temp file, "
                    "3) Update database in transaction, 4) Move temp file to target, 5) Commit transaction."
                ),
                "backup_system": (
                    "BackupManager creates backup BEFORE applying changes. "
                    "Backup is stored in {root_dir}/old_code/ with UUID. "
                    "If operation fails, file is automatically restored from backup."
                ),
                "operation_order": (
                    "1. Validate commit_message (if git repo), "
                    "2. Apply CST operations, "
                    "3. Create temporary file, "
                    "4. Validate entire file in temp, "
                    "5. If apply=true: create backup, begin transaction, update database, move file, commit transaction, git commit"
                ),
            },
            "safety_features": {
                "validation": (
                    "Comprehensive validation before file modification: "
                    "compilation, docstrings, linter, type checker. "
                    "Validation happens in temporary file, not original."
                ),
                "backup": (
                    "Automatic backup creation before changes using BackupManager. "
                    "Backup includes metadata for history tracking."
                ),
                "transactions": (
                    "Database transactions ensure atomicity. "
                    "All database operations succeed or fail together."
                ),
                "rollback": (
                    "Automatic rollback on any error: "
                    "database transaction rollback, file restoration from backup."
                ),
                "cleanup": (
                    "Temporary file cleanup in all cases (success or failure). "
                    "No leftover temporary files."
                ),
                "preview": (
                    "Preview mode (apply=false) allows seeing changes without modifying file. "
                    "Safe to use, does not require commit_message even in git repository."
                ),
            },
            "see_also": [
                "BackupManager: System for file backups with metadata",
                "update_file_data_atomic: Atomic database update method",
                "validate_file_in_temp: File validation in temporary location",
                "is_git_repository: Git repository detection",
                "create_git_commit: Git commit creation",
            ],
        }
