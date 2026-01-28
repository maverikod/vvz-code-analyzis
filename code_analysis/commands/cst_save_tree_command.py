"""
MCP command: cst_save_tree

Save CST tree to file with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.tree_saver import save_tree_to_file
from ..core.cst_tree.tree_builder import reload_tree_from_file

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
                "root_dir": {
                    "type": "string",
                    "description": "Server root directory (optional, for database access)",
                },
                "dataset_id": {
                    "type": "string",
                    "description": "Dataset ID (optional, will be created if not provided)",
                },
                "validate": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to validate file before saving",
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
                    "description": "Automatically reload tree from file after save (keeps tree_id valid)",
                },
            },
            "required": ["tree_id", "project_id", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        tree_id: str,
        project_id: str,
        file_path: str,
        root_dir: Optional[str] = None,
        dataset_id: Optional[str] = None,
        validate: bool = True,
        backup: bool = True,
        commit_message: Optional[str] = None,
        auto_reload: bool = True,
        **kwargs,
    ) -> SuccessResult:
        try:
            # Resolve server root_dir for database access
            if not root_dir:
                from ..core.storage_paths import (
                    load_raw_config,
                    resolve_storage_paths,
                )

                config_path = self._resolve_config_path()
                config_data = load_raw_config(config_path)
                storage = resolve_storage_paths(
                    config_data=config_data, config_path=config_path
                )
                root_dir = str(storage.config_dir.parent) if hasattr(storage, 'config_dir') else "/"

            # Get database connection
            database = self._open_database(root_dir, auto_analyze=False)
            try:
                # Resolve absolute file path using project_id and watch_dir/project_name
                absolute_file_path = self._resolve_file_path_from_project(
                    database, project_id, file_path
                )
                
                # Get project root from project
                project = database.get_project(project_id)
                if not project:
                    return ErrorResult(
                        message=f"Project {project_id} not found",
                        code="PROJECT_NOT_FOUND",
                        details={"project_id": project_id},
                    )
                
                project_root = Path(project.root_path)

                # Get or create dataset_id if not provided
                if not dataset_id:
                    from .base_mcp_command import BaseMCPCommand

                    dataset_id = BaseMCPCommand._get_or_create_dataset(
                        database, project_id, str(project_root)
                    )

                # Save tree to file
                result = save_tree_to_file(
                    tree_id=tree_id,
                    file_path=str(absolute_file_path),
                    root_dir=project_root,
                    project_id=project_id,
                    dataset_id=dataset_id,
                    database=database,
                    validate=validate,
                    backup=backup,
                    commit_message=commit_message,
                )

                if not result.get("success"):
                    return ErrorResult(
                        message=result.get("error", "Failed to save tree"),
                        code="CST_SAVE_ERROR",
                        details=result,
                    )

                # Automatically reload tree from file to sync with saved file
                if auto_reload:
                    try:
                        reload_tree_from_file(tree_id=tree_id)
                        result["tree_reloaded"] = True
                    except Exception as reload_error:
                        logger.warning(
                            f"Failed to auto-reload tree after save: {reload_error}"
                        )
                        result["tree_reloaded"] = False
                        result["reload_error"] = str(reload_error)
                else:
                    result["tree_reloaded"] = False

                return SuccessResult(data=result)
            finally:
                database.disconnect()

        except Exception as e:
            logger.exception("cst_save_tree failed: %s", e)
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
                "6. Creates backup via BackupManager (if file exists and backup=True)\n"
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
                "- Git commit is optional and non-critical (file is already saved)"
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
                "root_dir": {
                    "description": "Server root directory (optional, for database access). If not provided, will be resolved from config.",
                    "type": "string",
                    "required": False,
                },
                "dataset_id": {
                    "description": "Dataset ID (UUID4 string, optional, will be created if not provided)",
                    "type": "string",
                    "required": False,
                },
                "validate": {
                    "description": "Whether to validate file before saving. Default is True.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "backup": {
                    "description": "Whether to create backup before saving. Default is True.",
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
