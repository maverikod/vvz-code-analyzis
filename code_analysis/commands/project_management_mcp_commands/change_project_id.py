"""
MCP command: change_project_id.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ._shared import (
    Any,
    BaseMCPCommand,
    Dict,
    ErrorResult,
    Optional,
    SuccessResult,
    ValidationError,
    ProjectIdError,
    load_project_id,
    _get_socket_path_from_db_path,
    logger,
    uuid,
)


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
                "project_id": {
                    "type": "string",
                    "description": (
                        "Current project identifier (UUID4). Project root path is resolved from database."
                    ),
                    "examples": ["61d708de-e9fe-11f0-b3c3-2ba372fd1d94"],
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
            "required": ["project_id", "new_project_id"],
            "additionalProperties": False,
            "examples": [
                {
                    "project_id": "61d708de-e9fe-11f0-b3c3-2ba372fd1d94",
                    "new_project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                },
                {
                    "project_id": "61d708de-e9fe-11f0-b3c3-2ba372fd1d94",
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
        project_id: str,
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
            project_id: Current project identifier (root path resolved from database).
            new_project_id: New project identifier (UUID v4).
            old_project_id: Optional current project_id for validation.
            description: Optional new project description.
            update_database: Whether to update database (default: True).
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with change summary or ErrorResult on failure.
        """
        try:
            root_path = self._resolve_project_root(project_id)
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
                                field="project_id",
                                details={"project_id": project_id, "error": str(e)},
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
                        field="project_id",
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

                    database = self._open_database_from_config(auto_analyze=False)
                    try:
                        existing_project_id = (
                            BaseMCPCommand._get_project_id_by_root_path(
                                database, str(root_path)
                            )
                        )
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
                            database.execute(
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
