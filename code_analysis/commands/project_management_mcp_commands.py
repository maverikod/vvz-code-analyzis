"""
Project management MCP commands.

This module provides commands for managing project identifiers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.database import CodeDatabase
from ..core.exceptions import DatabaseError, ValidationError
from ..core.project_resolution import (
    ProjectIdError,
    load_project_id,
    normalize_root_dir,
    require_matching_project_id,
)

logger = logging.getLogger(__name__)


class ChangeProjectIdMCPCommand(BaseMCPCommand):
    """
    Change project identifier in projectid file and database.

    This command updates the project identifier for a project:
    1. Validates the new project_id (must be UUID v4)
    2. Updates the projectid file in the project root
    3. Updates the project record in the database (if exists)

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "change_project_id"
    version = "1.0.0"
    descr = (
        "Change project identifier: update projectid file and database record. "
        "New project_id must be a valid UUID v4."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["ChangeProjectIdMCPCommand"],
    ) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        This schema is used by MCP Proxy for request validation.
        Keep it strict and deterministic.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": (
                "Change project identifier. Updates the projectid file in the project root "
                "and the project record in the database (if exists). "
                "The new project_id must be a valid UUID v4 format."
            ),
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": (
                        "Project root directory (contains projectid file and optionally "
                        "data/code_analysis.db). Must be an absolute path or relative to current working directory."
                    ),
                    "examples": ["/abs/path/to/project", "./project"],
                },
                "new_project_id": {
                    "type": "string",
                    "description": (
                        "New project identifier. Must be a valid UUID v4 format "
                        "(e.g., '8772a086-688d-4198-a0c4-f03817cc0e6c'). "
                        "This will replace the current project_id in both the projectid file and database."
                    ),
                    "examples": ["8772a086-688d-4198-a0c4-f03817cc0e6c"],
                },
                "old_project_id": {
                    "type": "string",
                    "description": (
                        "Optional current project_id for safety validation. "
                        "If provided, must match the current project_id in projectid file. "
                        "This prevents accidental changes if the projectid file was modified externally."
                    ),
                    "examples": ["61d708de-e9fe-11f0-b3c3-2ba372fd1d94"],
                },
                "update_database": {
                    "type": "boolean",
                    "description": (
                        "If True, update the project record in the database (if exists). "
                        "If False, only update the projectid file. Default: True."
                    ),
                    "default": True,
                    "examples": [True, False],
                },
            },
            "required": ["root_dir", "new_project_id"],
            "additionalProperties": False,
            "examples": [
                {
                    "root_dir": "/abs/path/to/project",
                    "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                },
                {
                    "root_dir": "/abs/path/to/project",
                    "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "old_project_id": "61d708de-e9fe-11f0-b3c3-2ba372fd1d94",
                    "update_database": True,
                },
            ],
        }

    @classmethod
    def metadata(cls: type["ChangeProjectIdMCPCommand"]) -> Dict[str, Any]:
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
                "The change_project_id command updates the project identifier for a project. "
                "This is a critical operation that affects both the projectid file and the database. "
                "\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Validates new_project_id is a valid UUID v4 format\n"
                "3. If old_project_id is provided, validates it matches current projectid file\n"
                "4. Updates projectid file in root_dir with new_project_id\n"
                "5. If update_database is True, updates project record in database (if exists)\n"
                "\n"
                "Safety features:\n"
                "- Validates new_project_id format (must be UUID v4)\n"
                "- Optional old_project_id validation prevents accidental changes\n"
                "- Database update is optional (can update only file)\n"
                "\n"
                "Important notes:\n"
                "- This command modifies project identity - use with caution\n"
                "- If database has existing project with old_project_id, it will be updated\n"
                "- If database has no project record, only file is updated\n"
                "- All future commands will use the new project_id\n"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative to current working directory. "
                        "Must contain a projectid file. The directory must exist and be accessible."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/my_project",
                        "./my_project",
                        "/var/lib/projects/code_analysis",
                    ],
                },
                "new_project_id": {
                    "description": (
                        "New project identifier in UUID v4 format. "
                        "Must be a valid UUID v4 (e.g., '8772a086-688d-4198-a0c4-f03817cc0e6c'). "
                        "This will become the new project identifier stored in projectid file and database."
                    ),
                    "type": "string",
                    "required": True,
                    "format": "uuid-v4",
                    "examples": [
                        "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "a1b2c3d4-e5f6-4789-a0b1-c2d3e4f5a6b7",
                    ],
                    "validation": (
                        "Must match UUID v4 format: 8-4-4-4-12 hexadecimal digits separated by hyphens. "
                        "Version field (13th character) must be '4'. "
                        "Variant field (17th character) must be one of '8', '9', 'a', or 'b'."
                    ),
                },
                "old_project_id": {
                    "description": (
                        "Optional current project_id for safety validation. "
                        "If provided, the command will verify that this matches the current value "
                        "in the projectid file before making changes. "
                        "This prevents accidental changes if the projectid file was modified externally. "
                        "If not provided, the command will proceed without this validation."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "61d708de-e9fe-11f0-b3c3-2ba372fd1d94",
                        None,
                    ],
                },
                "update_database": {
                    "description": (
                        "Whether to update the project record in the database. "
                        "If True (default), the command will update the project record in the database "
                        "if it exists. If False, only the projectid file will be updated. "
                        "Use False if you want to change the file without affecting the database, "
                        "or if the database doesn't exist yet."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                    "examples": [True, False],
                },
            },
            "usage_examples": [
                {
                    "description": "Basic usage: change project ID",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    },
                    "explanation": (
                        "Updates projectid file and database with new UUID v4 identifier. "
                        "No old_project_id validation is performed."
                    ),
                },
                {
                    "description": "Safe change with old_project_id validation",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "old_project_id": "61d708de-e9fe-11f0-b3c3-2ba372fd1d94",
                    },
                    "explanation": (
                        "Validates that current projectid file contains old_project_id before updating. "
                        "If mismatch, command fails with validation error."
                    ),
                },
                {
                    "description": "Update only file, not database",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "update_database": False,
                    },
                    "explanation": (
                        "Updates only the projectid file. Database is not modified. "
                        "Useful when database doesn't exist yet or you want to update file separately."
                    ),
                },
            ],
            "error_cases": {
                "INVALID_UUID_FORMAT": {
                    "description": "new_project_id is not a valid UUID format",
                    "example": "new_project_id='invalid-uuid'",
                    "solution": "Provide a valid UUID v4 format (e.g., '8772a086-688d-4198-a0c4-f03817cc0e6c')",
                },
                "INVALID_UUID_VERSION": {
                    "description": "new_project_id is not UUID v4 (wrong version)",
                    "example": "new_project_id='61d708de-e9fe-11f0-b3c3-2ba372fd1d94' (UUID v1)",
                    "solution": "Generate a new UUID v4 using uuid.uuid4() or online UUID generator",
                },
                "PROJECTID_FILE_NOT_FOUND": {
                    "description": "projectid file not found in root_dir",
                    "example": "root_dir='/path/to/project' but projectid file missing",
                    "solution": "Ensure projectid file exists in the project root directory",
                },
                "OLD_PROJECT_ID_MISMATCH": {
                    "description": "old_project_id provided but doesn't match current projectid file",
                    "example": "old_project_id='abc...' but file contains 'xyz...'",
                    "solution": (
                        "Either remove old_project_id parameter or provide the correct current value. "
                        "Check current value by reading root_dir/projectid file."
                    ),
                },
                "ROOT_DIR_NOT_FOUND": {
                    "description": "root_dir path doesn't exist or is not a directory",
                    "example": "root_dir='/nonexistent/path'",
                    "solution": "Provide a valid existing directory path",
                },
                "DATABASE_UPDATE_FAILED": {
                    "description": "Failed to update project record in database",
                    "example": "Database locked, corrupted, or project record not found",
                    "solution": (
                        "Check database integrity, ensure it's not locked by another process, "
                        "or set update_database=False to skip database update"
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "old_project_id": "Previous project_id from projectid file",
                        "new_project_id": "New project_id that was set",
                        "projectid_file_path": "Path to updated projectid file",
                        "database_updated": "Whether database was updated (True/False)",
                        "database_project_id": "New project_id in database (if updated)",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., VALIDATION_ERROR, DATABASE_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error details",
                },
            },
        }

    async def execute(
        self: "ChangeProjectIdMCPCommand",
        root_dir: str,
        new_project_id: str,
        old_project_id: Optional[str] = None,
        update_database: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute change project ID command.

        Args:
            self: Command instance.
            root_dir: Project root directory.
            new_project_id: New project identifier (UUID v4).
            old_project_id: Optional current project_id for validation.
            update_database: Whether to update database (default: True).
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with change summary or ErrorResult on failure.
        """
        try:
            # Step 1: Validate and normalize root_dir
            root_path = self._validate_root_dir(root_dir)
            projectid_path = root_path / "projectid"

            # Step 2: Validate new_project_id format (must be UUID v4)
            try:
                new_uuid = uuid.UUID(new_project_id)
                if new_uuid.version != 4:
                    return self._handle_error(
                        ValidationError(
                            f"Invalid UUID version: expected v4, got v{new_uuid.version}",
                            field="new_project_id",
                            details={"new_project_id": new_project_id},
                        ),
                        "VALIDATION_ERROR",
                        "change_project_id",
                    )
            except ValueError as e:
                return self._handle_error(
                    ValidationError(
                        f"Invalid UUID format: {str(e)}",
                        field="new_project_id",
                        details={"new_project_id": new_project_id},
                    ),
                    "VALIDATION_ERROR",
                    "change_project_id",
                )

            # Step 3: Load current project_id from file
            if not projectid_path.exists():
                return self._handle_error(
                    ValidationError(
                        f"projectid file not found: {projectid_path}",
                        field="root_dir",
                        details={"root_dir": str(root_dir), "projectid_path": str(projectid_path)},
                    ),
                    "PROJECTID_FILE_NOT_FOUND",
                    "change_project_id",
                )

            try:
                current_project_id = load_project_id(root_path)
            except ProjectIdError as e:
                return self._handle_error(
                    ValidationError(
                        f"Failed to load current project_id: {str(e)}",
                        field="root_dir",
                        details={"root_dir": str(root_dir), "error": str(e)},
                    ),
                    "PROJECTID_LOAD_ERROR",
                    "change_project_id",
                )

            # Step 4: Validate old_project_id if provided
            if old_project_id is not None:
                if old_project_id != current_project_id:
                    return self._handle_error(
                        ValidationError(
                            f"old_project_id mismatch: expected {current_project_id}, got {old_project_id}",
                            field="old_project_id",
                            details={
                                "old_project_id": old_project_id,
                                "current_project_id": current_project_id,
                            },
                        ),
                        "OLD_PROJECT_ID_MISMATCH",
                        "change_project_id",
                    )

            # Step 5: Update projectid file
            try:
                projectid_path.write_text(new_project_id + "\n", encoding="utf-8")
                logger.info(
                    f"Updated projectid file: {projectid_path} "
                    f"(old: {current_project_id}, new: {new_project_id})"
                )
            except Exception as e:
                return self._handle_error(
                    ValidationError(
                        f"Failed to write projectid file: {str(e)}",
                        field="root_dir",
                        details={"projectid_path": str(projectid_path), "error": str(e)},
                    ),
                    "PROJECTID_WRITE_ERROR",
                    "change_project_id",
                )

            # Step 6: Update database if requested
            database_updated = False
            database_project_id = None
            if update_database:
                try:
                    # Resolve database path from config
                    config_path = self._resolve_config_path()
                    from ..core.storage_paths import load_raw_config, resolve_storage_paths

                    config_data = load_raw_config(config_path)
                    storage = resolve_storage_paths(
                        config_data=config_data, config_path=config_path
                    )
                    db_path = storage.db_path

                    # Open database
                    database = self._open_database(str(root_path), auto_analyze=False)
                    try:
                        # Check if project exists with old ID
                        existing_project_id = database.get_project_id(str(root_path))
                        if existing_project_id:
                            if existing_project_id == current_project_id:
                                # Update project record
                                database._execute(
                                    """
                                    UPDATE projects 
                                    SET id = ?, updated_at = julianday('now')
                                    WHERE id = ?
                                    """,
                                    (new_project_id, current_project_id),
                                )
                                database._commit()
                                database_updated = True
                                database_project_id = new_project_id
                                logger.info(
                                    f"Updated project record in database: "
                                    f"{current_project_id} -> {new_project_id}"
                                )
                            else:
                                logger.warning(
                                    f"Project in database has different ID ({existing_project_id}) "
                                    f"than projectid file ({current_project_id}), skipping database update"
                                )
                        else:
                            # Project doesn't exist in database, create it with new ID
                            database.get_or_create_project(
                                str(root_path), name=root_path.name, project_id=new_project_id
                            )
                            database_updated = True
                            database_project_id = new_project_id
                            logger.info(
                                f"Created new project record in database with ID: {new_project_id}"
                            )
                    finally:
                        database.close()
                except Exception as e:
                    logger.warning(
                        f"Failed to update database (file was updated): {str(e)}", exc_info=True
                    )
                    # Don't fail the command if database update fails - file was already updated

            return SuccessResult(
                data={
                    "old_project_id": current_project_id,
                    "new_project_id": new_project_id,
                    "projectid_file_path": str(projectid_path),
                    "database_updated": database_updated,
                    "database_project_id": database_project_id,
                },
                message=f"Project ID changed: {current_project_id} -> {new_project_id}",
            )
        except Exception as e:
            return self._handle_error(e, "CHANGE_PROJECT_ID_ERROR", "change_project_id")


class DeleteProjectMCPCommand(BaseMCPCommand):
    """
    Delete a project and all its data.

    This command completely removes a project from the database:
    - All files and their associated data
    - All chunks and vector indexes
    - All duplicates
    - All datasets
    - The project record itself

    Use with caution - this operation cannot be undone.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "delete_project"
    version = "1.0.0"
    descr = (
        "Delete a project and all its data from the database. "
        "This operation cannot be undone."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["DeleteProjectMCPCommand"],
    ) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": (
                "Delete a project and all its data from the database. "
                "This operation cannot be undone."
            ),
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": (
                        "Project root directory (contains projectid file). "
                        "Must be an absolute path or relative to current working directory."
                    ),
                },
                "project_id": {
                    "type": "string",
                    "description": (
                        "Optional project ID (UUID v4). "
                        "If not provided, will be resolved from root_dir/projectid file."
                    ),
                },
                "dry_run": {
                    "type": "boolean",
                    "description": (
                        "If True, only show what would be deleted without actually deleting. "
                        "Default: False."
                    ),
                    "default": False,
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self: "DeleteProjectMCPCommand",
        root_dir: str,
        project_id: Optional[str] = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute delete project command.

        Args:
            self: Command instance.
            root_dir: Project root directory.
            project_id: Optional project ID.
            dry_run: If True, only show what would be deleted.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with deletion summary or ErrorResult on failure.
        """
        try:
            # Validate and normalize root_dir
            root_path = self._validate_root_dir(root_dir)

            # Open database
            database = self._open_database(str(root_path), auto_analyze=False)
            try:
                # Resolve project_id if not provided
                if not project_id:
                    project_id = database.get_project_id(str(root_path))
                    if not project_id:
                        return self._handle_error(
                            ValidationError(
                                f"Project not found for root_dir: {root_dir}",
                                field="root_dir",
                                details={"root_dir": str(root_dir)},
                            ),
                            "PROJECT_NOT_FOUND",
                            "delete_project",
                        )

                # Import and execute command
                from .project_deletion import DeleteProjectCommand

                cmd = DeleteProjectCommand(
                    database=database,
                    project_id=project_id,
                    dry_run=dry_run,
                )
                result = await cmd.execute()

                if not result.get("success"):
                    return self._handle_error(
                        DatabaseError(result.get("message", "Failed to delete project")),
                        result.get("error", "DELETION_ERROR"),
                        "delete_project",
                    )

                return SuccessResult(
                    data=result,
                    message=result.get("message", "Project deleted successfully"),
                )
            finally:
                database.close()
        except Exception as e:
            return self._handle_error(e, "DELETE_PROJECT_ERROR", "delete_project")

    @classmethod
    def metadata(cls: type["DeleteProjectMCPCommand"]) -> Dict[str, Any]:
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
                "The delete_project command completely removes a project and all its data from the database. "
                "This is a destructive operation that cannot be undone.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or from root_dir/projectid file)\n"
                "4. Retrieves project information and statistics\n"
                "5. If dry_run=True:\n"
                "   - Returns statistics about what would be deleted\n"
                "   - Does not perform actual deletion\n"
                "6. If dry_run=False:\n"
                "   - Deletes all project data from database:\n"
                "     * All files and their associated data (classes, functions, methods, imports, usages)\n"
                "     * All chunks and removes from FAISS vector index\n"
                "     * All duplicates\n"
                "     * All datasets\n"
                "     * All AST trees\n"
                "     * All CST trees\n"
                "     * The project record itself\n"
                "7. Returns deletion summary\n\n"
                "Deleted Data:\n"
                "- Files: All file records and metadata\n"
                "- Code entities: All classes, functions, methods\n"
                "- Imports: All import records\n"
                "- Usages: All usage records\n"
                "- Chunks: All code chunks and vector indexes\n"
                "- Duplicates: All duplicate records\n"
                "- Datasets: All dataset records\n"
                "- AST/CST: All AST and CST trees\n"
                "- Project record: The project itself\n\n"
                "Use cases:\n"
                "- Remove projects that are no longer needed\n"
                "- Clean up test projects\n"
                "- Free up database space\n"
                "- Remove orphaned projects\n\n"
                "Important notes:\n"
                "- This operation is PERMANENT and cannot be undone\n"
                "- Always use dry_run=True first to preview what will be deleted\n"
                "- Project files on disk are NOT deleted (only database records)\n"
                "- All related data is cascaded and removed\n"
                "- Use with extreme caution"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain projectid file. Used to resolve project_id if not provided."
                    ),
                    "type": "string",
                    "required": True,
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. If not provided, will be resolved from root_dir/projectid file. "
                        "If provided, must match the project_id in the file."
                    ),
                    "type": "string",
                    "required": False,
                },
                "dry_run": {
                    "description": (
                        "If True, only shows what would be deleted without actually deleting. "
                        "Default is False. ALWAYS use dry_run=True first to preview deletion."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Preview deletion (dry run)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "dry_run": True,
                    },
                    "explanation": (
                        "Shows statistics about what would be deleted without actually deleting. "
                        "Safe to run to preview deletion."
                    ),
                },
                {
                    "description": "Delete project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Permanently deletes project and all its data from database. "
                        "WARNING: This is permanent and cannot be undone."
                    ),
                },
                {
                    "description": "Delete project with explicit project_id",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    },
                    "explanation": (
                        "Deletes project with explicit project_id. "
                        "Useful when you want to ensure correct project is deleted."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered in database",
                    "solution": (
                        "Verify project exists. Run list_projects to see all projects. "
                        "Ensure projectid file exists and contains valid UUID."
                    ),
                },
                "DELETE_PROJECT_ERROR": {
                    "description": "General error during project deletion",
                    "example": "Database error, cascade deletion failure, or permission denied",
                    "solution": (
                        "Check database integrity, ensure database is not locked, "
                        "verify file permissions. Use dry_run=True first to identify issues."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Whether deletion was successful (always True for dry_run)",
                        "dry_run": "Whether this was a dry run",
                        "project_id": "Project UUID that was deleted (or would be deleted)",
                        "project_name": "Project name",
                        "root_path": "Project root path",
                        "files_count": "Number of files that were deleted",
                        "chunks_count": "Number of chunks that were deleted",
                        "datasets_count": "Number of datasets that were deleted",
                        "message": "Status message",
                    },
                    "example_dry_run": {
                        "success": True,
                        "dry_run": True,
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "project_name": "my_project",
                        "root_path": "/home/user/projects/my_project",
                        "files_count": 42,
                        "chunks_count": 100,
                        "datasets_count": 2,
                        "message": "Would delete project my_project (928bcf10-db1c-47a3-8341-f60a6d997fe7)",
                    },
                    "example_deleted": {
                        "success": True,
                        "dry_run": False,
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "project_name": "my_project",
                        "root_path": "/home/user/projects/my_project",
                        "files_count": 42,
                        "chunks_count": 100,
                        "datasets_count": 2,
                        "message": "Deleted project my_project (928bcf10-db1c-47a3-8341-f60a6d997fe7)",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, DELETE_PROJECT_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "ALWAYS use dry_run=True first to preview what will be deleted",
                "Verify project_id is correct before deletion",
                "Backup database before deleting important projects",
                "This operation is permanent - double-check before proceeding",
                "Project files on disk are NOT deleted, only database records",
                "Use list_projects to verify project exists before deletion",
            ],
        }


class DeleteUnwatchedProjectsMCPCommand(BaseMCPCommand):
    """
    Delete projects that are not in the list of watched directories.

    This command:
    1. Gets the list of watched directories from config
    2. Finds all projects in the database
    3. Identifies projects whose root_path is not in the watched directories
    4. Deletes those projects

    Use with caution - this operation cannot be undone.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "delete_unwatched_projects"
    version = "1.0.0"
    descr = (
        "Delete projects that are not in the list of watched directories. "
        "This operation cannot be undone."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["DeleteUnwatchedProjectsMCPCommand"],
    ) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": (
                "Delete projects that are not in the list of watched directories. "
                "This operation cannot be undone."
            ),
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": (
                        "Server root directory (contains config.json and data/code_analysis.db). "
                        "Must be an absolute path or relative to current working directory."
                    ),
                },
                "watched_dirs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of watched directory paths. "
                        "If not provided, will be read from config.json (code_analysis.worker.watch_dirs)."
                    ),
                },
                "dry_run": {
                    "type": "boolean",
                    "description": (
                        "If True, only show what would be deleted without actually deleting. "
                        "Default: False."
                    ),
                    "default": False,
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self: "DeleteUnwatchedProjectsMCPCommand",
        root_dir: str,
        watched_dirs: Optional[List[str]] = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute delete unwatched projects command.

        Args:
            self: Command instance.
            root_dir: Server root directory.
            watched_dirs: Optional list of watched directories.
            dry_run: If True, only show what would be deleted.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with deletion summary or ErrorResult on failure.
        """
        try:
            # Validate and normalize root_dir
            root_path = self._validate_root_dir(root_dir)

            # Get watched_dirs from config if not provided
            if watched_dirs is None:
                config_path = self._resolve_config_path()
                from ..core.storage_paths import load_raw_config

                config_data = load_raw_config(config_path)
                worker_config = config_data.get("code_analysis", {}).get("worker", {})
                watched_dirs = worker_config.get("watch_dirs", [])
                
                # Also check dynamic_watch_file
                dynamic_watch_file = worker_config.get("dynamic_watch_file")
                if dynamic_watch_file:
                    dynamic_path = Path(root_path) / dynamic_watch_file
                    if dynamic_path.exists():
                        try:
                            import json
                            with open(dynamic_path, "r", encoding="utf-8") as f:
                                dynamic_dirs = json.load(f)
                                if isinstance(dynamic_dirs, list):
                                    watched_dirs.extend(dynamic_dirs)
                        except Exception as e:
                            logger.warning(f"Failed to load dynamic watch dirs: {e}")

            if not watched_dirs:
                return self._handle_error(
                    ValidationError(
                        "No watched directories found in config and none provided",
                        field="watched_dirs",
                        details={"root_dir": str(root_dir)},
                    ),
                    "NO_WATCHED_DIRS",
                    "delete_unwatched_projects",
                )

            # Open database
            database = self._open_database(str(root_path), auto_analyze=False)
            try:
                # Import and execute command
                from .project_deletion import DeleteUnwatchedProjectsCommand

                cmd = DeleteUnwatchedProjectsCommand(
                    database=database,
                    watched_dirs=watched_dirs,
                    dry_run=dry_run,
                    server_root_dir=str(root_path),
                )
                result = await cmd.execute()

                return SuccessResult(
                    data=result,
                    message=result.get("message", "Unwatched projects processed"),
                )
            finally:
                database.close()
        except Exception as e:
            return self._handle_error(e, "DELETE_UNWATCHED_PROJECTS_ERROR", "delete_unwatched_projects")

    @classmethod
    def metadata(cls: type["DeleteUnwatchedProjectsMCPCommand"]) -> Dict[str, Any]:
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
                "The delete_unwatched_projects command deletes projects that are not in the list of "
                "watched directories. It discovers all projects in watched directories and compares "
                "them with database projects to find unwatched ones, then deletes those projects.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Gets watched directories from config.json (code_analysis.worker.watch_dirs) or from parameter\n"
                "3. Also checks dynamic_watch_file if configured\n"
                "4. Discovers all projects in watched directories using project discovery\n"
                "5. Gets all projects from database\n"
                "6. Compares database projects with discovered projects:\n"
                "   - Projects in discovered list: Kept\n"
                "   - Projects not in discovered list: Marked for deletion\n"
                "   - Server root directory: Always protected from deletion\n"
                "7. If dry_run=True:\n"
                "   - Lists projects that would be deleted\n"
                "   - Lists projects that would be kept\n"
                "   - Does not perform actual deletion\n"
                "8. If dry_run=False:\n"
                "   - Deletes unwatched projects using clear_project_data\n"
                "   - Removes all project data (files, chunks, datasets, etc.)\n"
                "9. Returns deletion summary\n\n"
                "Project Discovery:\n"
                "- Scans watched directories for projects (looks for projectid files)\n"
                "- Uses project discovery to find all projects\n"
                "- Handles nested project errors and duplicate project_id errors\n"
                "- Collects discovery errors for reporting\n\n"
                "Protection:\n"
                "- Server root directory is always protected from deletion\n"
                "- Projects in watched directories are kept\n"
                "- Only unwatched projects are deleted\n\n"
                "Use cases:\n"
                "- Clean up projects that are no longer in watched directories\n"
                "- Remove orphaned projects from database\n"
                "- Maintain database cleanliness\n"
                "- Free up database space\n\n"
                "Important notes:\n"
                "- This operation is PERMANENT and cannot be undone\n"
                "- Always use dry_run=True first to preview what will be deleted\n"
                "- Watched directories are read from config.json if not provided\n"
                "- Server root directory is automatically protected\n"
                "- Discovery errors are reported but don't stop the process\n"
                "- Use with extreme caution"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Server root directory path. Can be absolute or relative. "
                        "Must contain config.json and data/code_analysis.db file. "
                        "This is the server root, not individual project directories."
                    ),
                    "type": "string",
                    "required": True,
                },
                "watched_dirs": {
                    "description": (
                        "Optional list of watched directory paths. If not provided, will be read from "
                        "config.json (code_analysis.worker.watch_dirs). Also checks dynamic_watch_file "
                        "if configured. These are the directories where projects should be kept."
                    ),
                    "type": "array",
                    "required": False,
                    "items": {"type": "string"},
                    "examples": [
                        ["/home/user/projects", "/var/lib/projects"],
                        ["/opt/projects"],
                    ],
                },
                "dry_run": {
                    "description": (
                        "If True, only shows what would be deleted without actually deleting. "
                        "Default is False. ALWAYS use dry_run=True first to preview deletion."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Preview deletion (dry run)",
                    "command": {
                        "root_dir": "/home/user/projects/code_analysis",
                        "dry_run": True,
                    },
                    "explanation": (
                        "Shows which projects would be deleted and which would be kept. "
                        "Safe to run to preview deletion."
                    ),
                },
                {
                    "description": "Delete unwatched projects using config",
                    "command": {
                        "root_dir": "/home/user/projects/code_analysis",
                    },
                    "explanation": (
                        "Deletes projects not in watched directories from config.json. "
                        "WARNING: This is permanent and cannot be undone."
                    ),
                },
                {
                    "description": "Delete unwatched projects with explicit watched_dirs",
                    "command": {
                        "root_dir": "/home/user/projects/code_analysis",
                        "watched_dirs": ["/home/user/projects", "/var/lib/projects"],
                    },
                    "explanation": (
                        "Deletes projects not in the specified watched directories. "
                        "Overrides config.json watched_dirs."
                    ),
                },
            ],
            "error_cases": {
                "NO_WATCHED_DIRS": {
                    "description": "No watched directories found",
                    "example": "watched_dirs not provided and not in config.json",
                    "solution": (
                        "Provide watched_dirs parameter or configure code_analysis.worker.watch_dirs "
                        "in config.json."
                    ),
                },
                "DELETE_UNWATCHED_PROJECTS_ERROR": {
                    "description": "General error during deletion",
                    "example": "Database error, project discovery error, or deletion failure",
                    "solution": (
                        "Check database integrity, verify watched directories exist, "
                        "ensure project discovery works. Use dry_run=True first."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Whether operation was successful (True if no errors)",
                        "dry_run": "Whether this was a dry run",
                        "deleted_count": "Number of projects deleted (or would be deleted)",
                        "kept_count": "Number of projects kept",
                        "projects_deleted": (
                            "List of projects that were deleted. Each contains:\n"
                            "- project_id: Project UUID\n"
                            "- root_path: Project root path\n"
                            "- name: Project name\n"
                            "- reason: Reason for deletion (not_discovered_in_watch_dirs, invalid_path)"
                        ),
                        "projects_kept": (
                            "List of projects that were kept. Each contains:\n"
                            "- project_id: Project UUID\n"
                            "- root_path: Project root path\n"
                            "- name: Project name\n"
                            "- reason: Reason for keeping (discovered_in_watch_dirs, server_root_protected)"
                        ),
                        "discovery_errors": "List of errors during project discovery (if any)",
                        "errors": "List of errors during deletion (if any)",
                        "message": "Status message",
                    },
                    "example": {
                        "success": True,
                        "dry_run": False,
                        "deleted_count": 2,
                        "kept_count": 3,
                        "projects_deleted": [
                            {
                                "project_id": "abc123...",
                                "root_path": "/old/project1",
                                "name": "old_project1",
                                "reason": "not_discovered_in_watch_dirs",
                            },
                        ],
                        "projects_kept": [
                            {
                                "project_id": "def456...",
                                "root_path": "/home/user/projects/active_project",
                                "name": "active_project",
                                "reason": "discovered_in_watch_dirs",
                            },
                        ],
                        "discovery_errors": None,
                        "errors": None,
                        "message": "Deleted 2 unwatched project(s), kept 3 watched project(s)",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., NO_WATCHED_DIRS, DELETE_UNWATCHED_PROJECTS_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "ALWAYS use dry_run=True first to preview what will be deleted",
                "Verify watched_dirs are correct before deletion",
                "Backup database before deleting projects",
                "This operation is permanent - double-check before proceeding",
                "Server root directory is automatically protected",
                "Review projects_kept and projects_deleted lists carefully",
                "Check discovery_errors to identify project discovery issues",
            ],
        }


class ListProjectsMCPCommand(BaseMCPCommand):
    """
    List all projects in the database.

    This command retrieves all projects from the database and returns
    their UUID, root path, name, comment, and last update time.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "list_projects"
    version = "1.0.0"
    descr = "List all projects in the database with their UUID and metadata"
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["ListProjectsMCPCommand"],
    ) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": "List all projects in the database with their UUID and metadata",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": (
                        "Server root directory (contains data/code_analysis.db). "
                        "Must be an absolute path or relative to current working directory."
                    ),
                    "examples": [
                        "/home/user/projects/code_analysis",
                        "/var/lib/code_analysis",
                        "./code_analysis",
                    ],
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
            "examples": [
                {
                    "root_dir": "/home/user/projects/code_analysis",
                },
            ],
        }

    @classmethod
    def metadata(cls: type["ListProjectsMCPCommand"]) -> Dict[str, Any]:
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
                "The list_projects command retrieves all projects from the database "
                "and returns their complete metadata including UUID, root path, name, "
                "comment, and last update timestamp.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection at root_dir/data/code_analysis.db\n"
                "3. Queries all projects from the projects table\n"
                "4. Returns list of projects sorted by name and root_path\n\n"
                "Use cases:\n"
                "- Discover all projects in the database\n"
                "- Get project UUIDs for use in other commands\n"
                "- Verify project registration\n"
                "- Audit project metadata\n\n"
                "Important notes:\n"
                "- Returns all projects regardless of their status\n"
                "- Projects are sorted alphabetically by name, then by root_path\n"
                "- Empty database returns empty list (count: 0)\n"
                "- Each project entry includes: id (UUID), root_path, name, comment, updated_at"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Server root directory path. Can be absolute or relative to current working directory. "
                        "Must contain data/code_analysis.db file. The directory must exist and be accessible. "
                        "This is the root directory of the code-analysis-server, not individual project directories."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/code_analysis",
                        "/var/lib/code_analysis",
                        "./code_analysis",
                        "/opt/code-analysis-server",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Basic usage: list all projects",
                    "command": {
                        "root_dir": "/home/user/projects/code_analysis",
                    },
                    "explanation": (
                        "Retrieves all projects from the database and returns their UUID, "
                        "root path, name, comment, and last update time."
                    ),
                },
                {
                    "description": "List projects from server root",
                    "command": {
                        "root_dir": "/var/lib/code_analysis",
                    },
                    "explanation": (
                        "Lists all projects stored in the server's database. "
                        "Useful for discovering what projects are registered."
                    ),
                },
            ],
            "error_cases": {
                "ROOT_DIR_NOT_FOUND": {
                    "description": "root_dir path doesn't exist or is not a directory",
                    "example": "root_dir='/nonexistent/path'",
                    "solution": "Provide a valid existing directory path",
                },
                "DATABASE_NOT_FOUND": {
                    "description": "Database file not found at root_dir/data/code_analysis.db",
                    "example": "root_dir='/path' but data/code_analysis.db missing",
                    "solution": (
                        "Ensure the database file exists. You may need to run update_indexes "
                        "or restore_database first to create the database."
                    ),
                },
                "DATABASE_ERROR": {
                    "description": "Failed to open or query the database",
                    "example": "Database locked, corrupted, or permission denied",
                    "solution": (
                        "Check database integrity, ensure it's not locked by another process, "
                        "verify file permissions, or run repair_sqlite_database if corrupted"
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "projects": (
                            "List of project dictionaries, each containing:\n"
                            "- id: Project UUID (string)\n"
                            "- root_path: Project root directory path (string)\n"
                            "- name: Project name (string, may be None)\n"
                            "- comment: Optional comment/description (string, may be None)\n"
                            "- updated_at: Last update timestamp (float, Julian day)"
                        ),
                        "count": "Number of projects found (integer)",
                    },
                    "example": {
                        "projects": [
                            {
                                "id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                                "root_path": "/home/user/projects/vast_srv",
                                "name": "vast_srv",
                                "comment": None,
                                "updated_at": 2460300.123456,
                            },
                            {
                                "id": "36ebabd4-a480-4175-8129-2789f89beb40",
                                "root_path": "/home/user/projects/code_analysis",
                                "name": "code_analysis",
                                "comment": "Main code analysis tool",
                                "updated_at": 2460301.789012,
                            },
                        ],
                        "count": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., VALIDATION_ERROR, DATABASE_ERROR, LIST_PROJECTS_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error details",
                },
            },
        }

    async def execute(
        self: "ListProjectsMCPCommand",
        root_dir: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute list projects command.

        Args:
            self: Command instance.
            root_dir: Server root directory.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with list of projects or ErrorResult on failure.
        """
        try:
            # Validate and normalize root_dir
            root_path = self._validate_root_dir(root_dir)

            # Open database
            database = self._open_database(str(root_path), auto_analyze=False)
            try:
                # Get all projects
                projects = database.get_all_projects()

                return SuccessResult(
                    data={
                        "projects": projects,
                        "count": len(projects),
                    },
                    message=f"Found {len(projects)} project(s)",
                )
            finally:
                database.close()
        except Exception as e:
            return self._handle_error(e, "LIST_PROJECTS_ERROR", "list_projects")

