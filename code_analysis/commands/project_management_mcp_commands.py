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
from ..core.exceptions import DatabaseError, ValidationError
from ..core.project_resolution import (
    ProjectIdError,
    load_project_id,
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
    version = "1.1.0"
    descr = (
        "Change project identifier and/or description: update projectid file and database record. "
        "New project_id must be a valid UUID v4. Description is optional."
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
                "Change project identifier and/or description. Updates the projectid file in the project root "
                "and the project record in the database (if exists). "
                "The new project_id must be a valid UUID v4 format. "
                "Description is optional and can be updated independently or together with project_id."
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
                "description": {
                    "type": "string",
                    "description": (
                        "Optional new project description. If provided, updates the description "
                        "in both projectid file and database. If not provided, existing description is preserved. "
                        "Can be updated independently of project_id."
                    ),
                    "default": None,
                    "examples": ["My project description", "Production codebase"],
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
                "The change_project_id command updates the project identifier and/or description for a project. "
                "This is a critical operation that affects both the projectid file and the database. "
                "You can change project_id, description, or both in a single operation.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Validates new_project_id is a valid UUID v4 format\n"
                "3. If old_project_id is provided, validates it matches current projectid file\n"
                "4. Loads current project information from projectid file (if exists)\n"
                "5. Updates projectid file in JSON format with:\n"
                "   - new_project_id (always updated)\n"
                "   - description (updated if provided, otherwise preserved from existing file)\n"
                "6. If update_database is True, updates project record in database (if exists):\n"
                "   - Updates project id (if changed)\n"
                "   - Updates comment field (description) if provided\n"
                "\n"
                "Project ID File Format:\n"
                "The projectid file is stored in JSON format:\n"
                "{\n"
                '  "id": "550e8400-e29b-41d4-a716-446655440000",\n'
                '  "description": "Human readable description"\n'
                "}\n\n"
                "Description Handling:\n"
                "- If description parameter is provided: Updates description in both file and database\n"
                "- If description parameter is not provided: Preserves existing description from projectid file\n"
                "- If projectid file doesn't exist: Uses empty string as default description\n"
                "- Description can be updated independently of project_id\n\n"
                "Safety features:\n"
                "- Validates new_project_id format (must be UUID v4)\n"
                "- Optional old_project_id validation prevents accidental changes\n"
                "- Database update is optional (can update only file)\n"
                "- Preserves existing description if not explicitly provided\n\n"
                "Important notes:\n"
                "- This command modifies project identity - use with caution\n"
                "- If database has existing project with old_project_id, it will be updated\n"
                "- If database has no project record, only file is updated\n"
                "- All future commands will use the new project_id\n"
                "- Description update is optional and can be done separately from project_id change\n"
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
                "description": {
                    "description": (
                        "Optional new project description. Human-readable text describing the project. "
                        "If provided, this description will replace the existing description in both "
                        "the projectid file and the database (comment field). "
                        "If not provided, the existing description from the projectid file is preserved. "
                        "You can update description independently of project_id by providing the same "
                        "new_project_id as the current one and a new description."
                    ),
                    "type": "string",
                    "required": False,
                    "default": None,
                    "examples": [
                        "My production codebase",
                        "Test project for development",
                        "Legacy system maintenance",
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
                {
                    "description": "Change both project_id and description",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "description": "Updated project description",
                    },
                    "explanation": (
                        "Updates both project_id and description in projectid file and database. "
                        "Both fields are updated in a single operation."
                    ),
                },
                {
                    "description": "Update only description (keep same project_id)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "description": "New description for existing project",
                    },
                    "explanation": (
                        "Updates only the description while keeping the same project_id. "
                        "Provide the current project_id as new_project_id and the new description."
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
                        "old_description": "Previous description from projectid file (if existed)",
                        "new_description": "New description that was set (if provided)",
                        "projectid_file_path": "Path to updated projectid file",
                        "database_updated": "Whether database was updated (True/False)",
                        "database_project_id": "New project_id in database (if updated)",
                    },
                    "example": {
                        "old_project_id": "61d708de-e9fe-11f0-b3c3-2ba372fd1d94",
                        "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "old_description": "Old project description",
                        "new_description": "New project description",
                        "projectid_file_path": "/home/user/projects/my_project/projectid",
                        "database_updated": True,
                        "database_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
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
        description: Optional[str] = None,
        update_database: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute change project ID and/or description command.

        Args:
            self: Command instance.
            root_dir: Project root directory.
            new_project_id: New project identifier (UUID v4).
            old_project_id: Optional current project_id for validation.
            description: Optional new project description.
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

            # Step 3: Load current project information from file
            current_description = ""
            if not projectid_path.exists():
                # If file doesn't exist, we'll create it
                current_project_id = None
            else:
                try:
                    from ..core.project_resolution import load_project_info

                    project_info = load_project_info(root_path)
                    current_project_id = project_info.project_id
                    current_description = project_info.description
                except ProjectIdError as e:
                    # File exists but is invalid - we'll recreate it
                    logger.warning(
                        f"Invalid projectid file at {projectid_path}, will recreate: {e}"
                    )
                    current_project_id = None
                    current_description = ""
                except Exception as e:
                    # Try to load just the ID if description loading fails
                    try:
                        current_project_id = load_project_id(root_path)
                        current_description = ""
                    except Exception:
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
                if current_project_id is None:
                    return self._handle_error(
                        ValidationError(
                            "old_project_id provided but projectid file doesn't exist",
                            field="old_project_id",
                            details={
                                "old_project_id": old_project_id,
                                "projectid_path": str(projectid_path),
                            },
                        ),
                        "PROJECTID_FILE_NOT_FOUND",
                        "change_project_id",
                    )
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

            # Step 5: Determine new description
            new_description = (
                description if description is not None else current_description
            )

            # Step 6: Update projectid file in JSON format
            try:
                import json

                project_data = {
                    "id": new_project_id,
                    "description": new_description,
                }
                projectid_path.write_text(
                    json.dumps(project_data, indent=4, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                logger.info(
                    f"Updated projectid file: {projectid_path} "
                    f"(old_id: {current_project_id}, new_id: {new_project_id}, "
                    f"old_desc: {current_description}, new_desc: {new_description})"
                )
            except Exception as e:
                return self._handle_error(
                    ValidationError(
                        f"Failed to write projectid file: {str(e)}",
                        field="root_dir",
                        details={
                            "projectid_path": str(projectid_path),
                            "error": str(e),
                        },
                    ),
                    "PROJECTID_WRITE_ERROR",
                    "change_project_id",
                )

            # Step 7: Update database if requested
            database_updated = False
            database_project_id = None
            if update_database:
                try:
                    # Resolve database path from config
                    config_path = self._resolve_config_path()
                    from ..core.storage_paths import (
                        load_raw_config,
                        resolve_storage_paths,
                    )

                    config_data = load_raw_config(config_path)
                    resolve_storage_paths(
                        config_data=config_data, config_path=config_path
                    )

                    # Open database
                    database = self._open_database(str(root_path), auto_analyze=False)
                    try:
                        # Check if project exists with old ID or by root_path
                        existing_project_id = database.get_project_id(str(root_path))
                        if existing_project_id:
                            if (
                                current_project_id
                                and existing_project_id == current_project_id
                            ):
                                # Update project record (both ID and description if changed)
                                if description is not None:
                                    # Update both ID and description
                                    database.execute(
                                        """
                                        UPDATE projects 
                                        SET id = ?, comment = ?, updated_at = julianday('now')
                                        WHERE id = ?
                                        """,
                                        (
                                            new_project_id,
                                            new_description,
                                            current_project_id,
                                        ),
                                    )
                                else:
                                    # Update only ID
                                    database.execute(
                                        """
                                        UPDATE projects 
                                        SET id = ?, updated_at = julianday('now')
                                        WHERE id = ?
                                        """,
                                        (new_project_id, current_project_id),
                                    )
                                database_updated = True
                                database_project_id = new_project_id
                                logger.info(
                                    f"Updated project record in database: "
                                    f"{current_project_id} -> {new_project_id}"
                                    + (
                                        f", description: {new_description}"
                                        if description
                                        else ""
                                    )
                                )
                            elif existing_project_id != new_project_id:
                                # Update existing project with different ID
                                if description is not None:
                                    database.execute(
                                        """
                                        UPDATE projects 
                                        SET id = ?, comment = ?, updated_at = julianday('now')
                                        WHERE id = ?
                                        """,
                                        (
                                            new_project_id,
                                            new_description,
                                            existing_project_id,
                                        ),
                                    )
                                else:
                                    database.execute(
                                        """
                                        UPDATE projects 
                                        SET id = ?, updated_at = julianday('now')
                                        WHERE id = ?
                                        """,
                                        (new_project_id, existing_project_id),
                                    )
                                database_updated = True
                                database_project_id = new_project_id
                                logger.info(
                                    f"Updated project record in database: "
                                    f"{existing_project_id} -> {new_project_id}"
                                    + (
                                        f", description: {new_description}"
                                        if description
                                        else ""
                                    )
                                )
                            else:
                                # Same ID, only update description if provided
                                if description is not None:
                                    database.execute(
                                        """
                                        UPDATE projects 
                                        SET comment = ?, updated_at = julianday('now')
                                        WHERE id = ?
                                        """,
                                        (new_description, existing_project_id),
                                    )
                                    database_updated = True
                                    logger.info(
                                        f"Updated project description in database: {new_description}"
                                    )
                        else:
                            # Project doesn't exist in database, create it with new ID and description
                            database._execute(
                                """
                                INSERT INTO projects (id, root_path, name, comment, updated_at)
                                VALUES (?, ?, ?, ?, julianday('now'))
                                """,
                                (
                                    new_project_id,
                                    str(root_path),
                                    root_path.name,
                                    new_description,
                                ),
                            )
                            database._commit()
                            database_updated = True
                            database_project_id = new_project_id
                            logger.info(
                                f"Created new project record in database with ID: {new_project_id}, "
                                f"description: {new_description}"
                            )
                    finally:
                        database.disconnect()
                except Exception as e:
                    logger.warning(
                        f"Failed to update database (file was updated): {str(e)}",
                        exc_info=True,
                    )
                    # Don't fail the command if database update fails - file was already updated

            # Build result message
            message_parts = []
            if current_project_id != new_project_id:
                message_parts.append(
                    f"Project ID: {current_project_id or 'none'} -> {new_project_id}"
                )
            if description is not None and current_description != new_description:
                message_parts.append(
                    f"Description: '{current_description}' -> '{new_description}'"
                )
            if not message_parts:
                message_parts.append("Project updated (no changes detected)")

            return SuccessResult(
                data={
                    "old_project_id": current_project_id,
                    "new_project_id": new_project_id,
                    "old_description": current_description,
                    "new_description": new_description,
                    "projectid_file_path": str(projectid_path),
                    "database_updated": database_updated,
                    "database_project_id": database_project_id,
                },
                message="; ".join(message_parts),
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
                "delete_from_disk": {
                    "type": "boolean",
                    "description": (
                        "If True, also delete project root directory and all files from version directory. "
                        "If False, only delete from database. Default: False."
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
        delete_from_disk: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute delete project command.

        Args:
            self: Command instance.
            root_dir: Project root directory.
            project_id: Optional project ID.
            dry_run: If True, only show what would be deleted.
            delete_from_disk: If True, also delete from disk and version directory.
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

                # Get version_dir from config if delete_from_disk is True
                version_dir = None
                if delete_from_disk:
                    config_path = self._resolve_config_path()
                    from ..core.storage_paths import load_raw_config

                    config_data = load_raw_config(config_path)
                    file_watcher_config = config_data.get("code_analysis", {}).get(
                        "file_watcher", {}
                    )
                    version_dir = file_watcher_config.get("version_dir")
                    if not version_dir:
                        # Default: data/versions relative to config_dir
                        config_dir = Path(config_path).parent
                        version_dir = str(config_dir / "data" / "versions")

                # Import and execute command
                from .project_deletion import DeleteProjectCommand

                cmd = DeleteProjectCommand(
                    database=database,
                    project_id=project_id,
                    dry_run=dry_run,
                    delete_from_disk=delete_from_disk,
                    version_dir=version_dir,
                )
                result = await cmd.execute()

                if not result.get("success"):
                    return self._handle_error(
                        DatabaseError(
                            result.get("message", "Failed to delete project")
                        ),
                        result.get("error", "DELETION_ERROR"),
                        "delete_project",
                    )

                return SuccessResult(
                    data=result,
                    message=result.get("message", "Project deleted successfully"),
                )
            finally:
                database.disconnect()
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
                "Optionally, it can also delete the project directory and version files from disk. "
                "This is a destructive operation that cannot be undone.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or from root_dir/projectid file)\n"
                "4. Retrieves project information and statistics\n"
                "5. If dry_run=True:\n"
                "   - Returns statistics about what would be deleted\n"
                "   - Shows what would be deleted from disk (if delete_from_disk=True)\n"
                "   - Does not perform actual deletion\n"
                "6. If dry_run=False:\n"
                "   a. If delete_from_disk=True:\n"
                "      * Deletes project root directory from disk (recursively)\n"
                "      * Deletes all files from version directory for this project ({version_dir}/{project_id}/)\n"
                "      * Continues even if disk deletion fails (errors are logged)\n"
                "   b. Deletes all project data from database:\n"
                "      * All files and their associated data (classes, functions, methods, imports, usages)\n"
                "      * All chunks and removes from FAISS vector index\n"
                "      * All duplicates\n"
                "      * All datasets\n"
                "      * All AST trees\n"
                "      * All CST trees\n"
                "      * The project record itself\n"
                "7. Returns deletion summary\n\n"
                "Deleted Data (Database):\n"
                "- Files: All file records and metadata\n"
                "- Code entities: All classes, functions, methods\n"
                "- Imports: All import records\n"
                "- Usages: All usage records\n"
                "- Chunks: All code chunks and vector indexes\n"
                "- Duplicates: All duplicate records\n"
                "- Datasets: All dataset records\n"
                "- AST/CST: All AST and CST trees\n"
                "- Project record: The project itself\n\n"
                "Deleted Data (Disk, if delete_from_disk=True):\n"
                "- Project root directory: Entire project directory tree is removed\n"
                "- Version directory: All files in {version_dir}/{project_id}/ are removed\n"
                "  Version directory is typically 'data/versions' relative to config directory\n\n"
                "Use cases:\n"
                "- Remove projects that are no longer needed (database only)\n"
                "- Completely remove projects including files from disk\n"
                "- Clean up test projects\n"
                "- Free up database and disk space\n"
                "- Remove orphaned projects\n\n"
                "Important notes:\n"
                "- This operation is PERMANENT and cannot be undone\n"
                "- Always use dry_run=True first to preview what will be deleted\n"
                "- By default (delete_from_disk=False), only database records are deleted\n"
                "- If delete_from_disk=True, project files and version directory are also deleted\n"
                "- Disk deletion errors are logged but do not stop database deletion\n"
                "- All related data is cascaded and removed from database\n"
                "- Use with extreme caution, especially with delete_from_disk=True"
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
                {
                    "description": "Delete project from database and disk",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "delete_from_disk": True,
                    },
                    "explanation": (
                        "Permanently deletes project from database AND removes project directory and "
                        "version files from disk. WARNING: This is irreversible."
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
                        "delete_from_disk": "Whether disk deletion was requested",
                        "version_dir": "Version directory path (if delete_from_disk=True)",
                        "disk_deletion_errors": "List of disk deletion errors (if any)",
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
                config_watch_dirs = worker_config.get("watch_dirs", [])

                # Extract paths from watch_dirs config (can be list of dicts or list of strings)
                watched_dirs = []
                for item in config_watch_dirs:
                    if isinstance(item, dict):
                        # New format: {"id": "uuid", "path": "/path"}
                        if "path" in item:
                            watched_dirs.append(item["path"])
                    elif isinstance(item, str):
                        # Old format: just string path
                        watched_dirs.append(item)

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
                                    # Extract paths from dynamic_dirs if they are dicts
                                    for item in dynamic_dirs:
                                        if isinstance(item, dict) and "path" in item:
                                            watched_dirs.append(item["path"])
                                        elif isinstance(item, str):
                                            watched_dirs.append(item)
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
                database.disconnect()
        except Exception as e:
            return self._handle_error(
                e, "DELETE_UNWATCHED_PROJECTS_ERROR", "delete_unwatched_projects"
            )

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
                database.disconnect()
        except Exception as e:
            return self._handle_error(e, "LIST_PROJECTS_ERROR", "list_projects")


class CreateProjectMCPCommand(BaseMCPCommand):
    """
    Create or register a new project.

    This command:
    1. Validates that watched directory exists and does not contain projectid file
    2. Validates that project directory exists
    3. Checks if project is already registered in database
    4. Creates projectid file with UUID4 and description
    5. Registers project in database

    Returns project ID, whether project already existed, and description.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "create_project"
    version = "1.0.0"
    descr = (
        "Create or register a new project. "
        "Creates projectid file and registers project in database."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["CreateProjectMCPCommand"],
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
                "Create or register a new project. "
                "Creates projectid file and registers project in database."
            ),
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": (
                        "Server root directory (contains config.json and data/code_analysis.db). "
                        "Must be an absolute path or relative to current working directory."
                    ),
                },
                "watched_dir": {
                    "type": "string",
                    "description": (
                        "Watched directory path. Must exist and must NOT contain projectid file. "
                        "Must be an absolute path or relative to current working directory."
                    ),
                },
                "project_dir": {
                    "type": "string",
                    "description": (
                        "Project directory path. Must exist. "
                        "If already registered in database, returns existing project info. "
                        "Must be an absolute path or relative to current working directory."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": (
                        "Human-readable description of the project. "
                        "If projectid file already exists, its description is used instead. "
                        "Default: empty string or project directory name."
                    ),
                    "default": "",
                },
            },
            "required": ["root_dir", "watched_dir", "project_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self: "CreateProjectMCPCommand",
        root_dir: str,
        watched_dir: str,
        project_dir: str,
        description: str = "",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute create project command.

        Args:
            self: Command instance.
            root_dir: Server root directory.
            watched_dir: Watched directory path.
            project_dir: Project directory path.
            description: Optional project description.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with project info or ErrorResult on failure.
        """
        try:
            # Validate and normalize root_dir
            root_path = self._validate_root_dir(root_dir)

            # Open database
            database = self._open_database(str(root_path), auto_analyze=False)
            try:
                # Import and execute command
                from .project_creation import CreateProjectCommand

                cmd = CreateProjectCommand(
                    database=database,
                    watched_dir=watched_dir,
                    project_dir=project_dir,
                    description=description,
                )
                result = await cmd.execute()

                if not result.get("success"):
                    error_code = result.get("error", "CREATE_PROJECT_ERROR")
                    return self._handle_error(
                        ValidationError(
                            result.get("message", "Failed to create project"),
                            field="project_dir",
                            details=result,
                        ),
                        error_code,
                        "create_project",
                    )

                return SuccessResult(
                    data=result,
                    message=result.get("message", "Project created successfully"),
                )
            finally:
                database.disconnect()
        except Exception as e:
            return self._handle_error(e, "CREATE_PROJECT_ERROR", "create_project")

    @classmethod
    def metadata(cls: type["CreateProjectMCPCommand"]) -> Dict[str, Any]:
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
                "The create_project command creates or registers a new project in the system. "
                "It validates prerequisites, creates a projectid file with UUID4 identifier, "
                "and registers the project in the database.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Validates watched_dir exists and is a directory\n"
                "4. Checks if watched_dir contains projectid file (raises error if found)\n"
                "5. Validates project_dir exists and is a directory\n"
                "6. Checks if project_dir is already registered in database:\n"
                "   - If registered: Returns existing project info (already_existed=True)\n"
                "   - If not registered: Continues to creation\n"
                "7. Checks if projectid file exists in project_dir:\n"
                "   - If exists and valid: Registers in database using existing ID\n"
                "   - If exists but invalid: Recreates projectid file\n"
                "   - If not exists: Creates new projectid file with UUID4\n"
                "8. Registers project in database\n"
                "9. Returns project information\n\n"
                "Project ID File Format:\n"
                "The projectid file is created in JSON format:\n"
                "{\n"
                '  "id": "550e8400-e29b-41d4-a716-446655440000",\n'
                '  "description": "Human readable description"\n'
                "}\n\n"
                "Validation Rules:\n"
                "- watched_dir must exist and be a directory\n"
                "- watched_dir must NOT contain projectid file\n"
                "- project_dir must exist and be a directory\n"
                "- project_dir must NOT be already registered in database (unless projectid exists)\n"
                "- description is optional (defaults to project directory name)\n\n"
                "Return Values:\n"
                "- project_id: UUID4 identifier of the project\n"
                "- already_existed: True if project was already registered, False if newly created\n"
                "- description: Project description (from file if existed, or provided)\n"
                "- old_description: Previous description if projectid file was recreated\n"
                "- message: Status message\n\n"
                "Use cases:\n"
                "- Register a new project for code analysis\n"
                "- Register an existing project that has projectid file but not in database\n"
                "- Create a new project from scratch\n"
                "- Re-register a project after database cleanup"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Server root directory path. Contains config.json and data/code_analysis.db. "
                        "Can be absolute or relative. Used to locate database."
                    ),
                    "type": "string",
                    "required": True,
                },
                "watched_dir": {
                    "description": (
                        "Watched directory path. Must exist and be a directory. "
                        "Must NOT contain projectid file. This is the parent directory "
                        "that will be monitored for projects. Can be absolute or relative."
                    ),
                    "type": "string",
                    "required": True,
                },
                "project_dir": {
                    "description": (
                        "Project directory path. Must exist and be a directory. "
                        "If already registered in database, returns existing project info. "
                        "If projectid file exists, uses its ID. Otherwise creates new project. "
                        "Can be absolute or relative."
                    ),
                    "type": "string",
                    "required": True,
                },
                "description": {
                    "description": (
                        "Human-readable description of the project. Optional. "
                        "If projectid file already exists, its description takes precedence. "
                        "If not provided and no existing description, defaults to project directory name."
                    ),
                    "type": "string",
                    "required": False,
                    "default": "",
                },
            },
            "usage_examples": [
                {
                    "description": "Create new project",
                    "command": {
                        "root_dir": "/home/user/projects/tools/code_analysis",
                        "watched_dir": "/home/user/projects/test_data",
                        "project_dir": "/home/user/projects/test_data/my_project",
                        "description": "My new project for testing",
                    },
                    "explanation": (
                        "Creates a new project in /home/user/projects/test_data/my_project. "
                        "Creates projectid file with UUID4 and registers in database."
                    ),
                },
                {
                    "description": "Register existing project with projectid file",
                    "command": {
                        "root_dir": "/home/user/projects/tools/code_analysis",
                        "watched_dir": "/home/user/projects/test_data",
                        "project_dir": "/home/user/projects/test_data/existing_project",
                    },
                    "explanation": (
                        "Registers an existing project that already has projectid file. "
                        "Uses existing project ID from file."
                    ),
                },
                {
                    "description": "Get existing project info",
                    "command": {
                        "root_dir": "/home/user/projects/tools/code_analysis",
                        "watched_dir": "/home/user/projects/test_data",
                        "project_dir": "/home/user/projects/test_data/registered_project",
                    },
                    "explanation": (
                        "If project is already registered in database, returns existing project info "
                        "without creating new projectid file."
                    ),
                },
            ],
            "error_cases": {
                "WATCHED_DIR_NOT_FOUND": {
                    "description": "Watched directory does not exist",
                    "example": "watched_dir='/path/to/missing'",
                    "solution": "Verify watched directory path exists and is accessible.",
                },
                "WATCHED_DIR_NOT_DIRECTORY": {
                    "description": "Watched path is not a directory",
                    "example": "watched_dir='/path/to/file.txt'",
                    "solution": "Ensure watched_dir points to a directory, not a file.",
                },
                "PROJECTID_EXISTS_IN_WATCHED_DIR": {
                    "description": "Watched directory already contains projectid file",
                    "example": "watched_dir='/path' contains projectid file",
                    "solution": (
                        "Watched directory should not contain projectid file. "
                        "Use a parent directory as watched_dir, or remove projectid file if not needed."
                    ),
                },
                "PROJECT_DIR_NOT_FOUND": {
                    "description": "Project directory does not exist",
                    "example": "project_dir='/path/to/missing'",
                    "solution": "Verify project directory path exists and is accessible.",
                },
                "PROJECT_DIR_NOT_DIRECTORY": {
                    "description": "Project path is not a directory",
                    "example": "project_dir='/path/to/file.txt'",
                    "solution": "Ensure project_dir points to a directory, not a file.",
                },
                "PROJECTID_WRITE_ERROR": {
                    "description": "Failed to write projectid file",
                    "example": "Permission denied or disk full",
                    "solution": (
                        "Check file permissions, ensure directory is writable, "
                        "verify disk space is available."
                    ),
                },
                "DATABASE_REGISTRATION_ERROR": {
                    "description": "Failed to register project in database",
                    "example": "Database locked, constraint violation, or connection error",
                    "solution": (
                        "Check database integrity, ensure database is not locked, "
                        "verify database connection is working."
                    ),
                },
                "CREATE_PROJECT_ERROR": {
                    "description": "General error during project creation",
                    "example": "Unexpected error in validation or creation process",
                    "solution": "Check error message for specific details and resolve accordingly.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Whether operation was successful (always True)",
                        "project_id": "UUID4 identifier of the project",
                        "already_existed": "Whether project was already registered (True) or newly created (False)",
                        "description": "Project description (from file if existed, or provided)",
                        "old_description": "Previous description if projectid file was recreated, empty otherwise",
                        "message": "Status message",
                    },
                    "example_new": {
                        "success": True,
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "already_existed": False,
                        "description": "My new project",
                        "old_description": "",
                        "message": "Created and registered new project: 550e8400-e29b-41d4-a716-446655440000",
                    },
                    "example_existing": {
                        "success": True,
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "already_existed": True,
                        "description": "Existing project description",
                        "old_description": "Previous description",
                        "message": "Project already registered: 928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., WATCHED_DIR_NOT_FOUND, PROJECTID_EXISTS_IN_WATCHED_DIR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Ensure watched_dir exists and does not contain projectid file",
                "Use descriptive project descriptions for better organization",
                "If project already has projectid file, it will be used (not recreated)",
                "If project is already registered, command returns existing info without error",
                "Always check already_existed flag to know if project was created or already existed",
            ],
        }
