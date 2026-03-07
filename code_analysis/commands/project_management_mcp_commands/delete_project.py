"""
MCP command: delete_project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ._shared import (
    Any,
    BaseMCPCommand,
    Dict,
    ErrorResult,
    List,
    Optional,
    SuccessResult,
    logger,
)


class DeleteProjectMCPCommand(BaseMCPCommand):
    """
    Delete a project and all its data.

    This command completely removes a project from the database:
    - All files and their associated data
    - All chunks and vector indexes
    - All duplicates
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
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project ID (UUID v4). Required. "
                        "The project identifier to delete. "
                        "Can be obtained from list_projects command."
                    ),
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                    ],
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
                        "If True, move project root directory to trash (recycle bin) and delete version directory. "
                        "If False, only delete from database. Default: False."
                    ),
                    "default": False,
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
            "examples": [
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "dry_run": True,
                },
            ],
        }

    async def execute(
        self: "DeleteProjectMCPCommand",
        project_id: str,
        dry_run: bool = False,
        delete_from_disk: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute delete project command.

        Args:
            self: Command instance.
            project_id: Project ID (UUID v4) to delete.
            dry_run: If True, only show what would be deleted.
            delete_from_disk: If True, also delete from disk and version directory.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with deletion summary or ErrorResult on failure.
        """
        try:
            from ..core.exceptions import ValidationError, DatabaseError
            from pathlib import Path

            # Resolve database path from config
            from ..core.storage_paths import load_raw_config, resolve_storage_paths

            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            db_path = storage.db_path

            # Get socket path and create DatabaseClient
            from ..core.database_client.client import DatabaseClient
            from .base_mcp_command import _get_socket_path_from_db_path

            socket_path = _get_socket_path_from_db_path(db_path)
            database = DatabaseClient(socket_path=socket_path)
            database.connect()

            try:
                # Get project from database to verify it exists and get root_path
                project = database.get_project(project_id)
                if not project:
                    return self._handle_error(
                        ValidationError(
                            f"Project not found: {project_id}",
                            field="project_id",
                            details={"project_id": project_id},
                        ),
                        "PROJECT_NOT_FOUND",
                        "delete_project",
                    )

                # Get version_dir and trash_dir from config if delete_from_disk is True
                version_dir = None
                trash_dir = None
                if delete_from_disk:
                    file_watcher_config = config_data.get("code_analysis", {}).get(
                        "file_watcher", {}
                    )
                    version_dir = file_watcher_config.get("version_dir")
                    if not version_dir:
                        config_dir_path = Path(config_path).parent
                        version_dir = str(config_dir_path / "data" / "versions")
                    trash_dir = str(storage.trash_dir)

                # Import and execute command
                from .project_deletion import DeleteProjectCommand

                cmd = DeleteProjectCommand(
                    database=database,
                    project_id=project_id,
                    dry_run=dry_run,
                    delete_from_disk=delete_from_disk,
                    version_dir=version_dir,
                    trash_dir=trash_dir,
                    config_path=str(config_path),
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
                "1. Resolves database path from server configuration (config.json)\n"
                "2. Opens database connection\n"
                "3. Validates project_id exists in database and retrieves project information\n"
                "4. Retrieves project information and statistics\n"
                "5. If dry_run=True:\n"
                "   - Returns statistics about what would be deleted\n"
                "   - Shows what would be deleted from disk (if delete_from_disk=True)\n"
                "   - Does not perform actual deletion\n"
                "6. If dry_run=False:\n"
                "   a. Deletes all project data from database first (while project dir still exists)\n"
                "   b. If delete_from_disk=True:\n"
                "      * Moves project root directory to trash (recycle bin); does NOT permanently delete\n"
                "      * Permanently deletes version directory for this project ({version_dir}/{project_id}/)\n"
                "      * Continues even if move/delete fails (errors are logged)\n"
                "   c. Database deletion:\n"
                "      * All files and their associated data (classes, functions, methods, imports, usages)\n"
                "      * All chunks and removes from FAISS vector index\n"
                "      * All duplicates\n"
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
                "- AST/CST: All AST and CST trees\n"
                "- Project record: The project itself\n\n"
                "Disk (if delete_from_disk=True):\n"
                "- Project root directory: Moved to trash (recycle bin), not permanently deleted. Use list_trashed_projects / permanently_delete_from_trash / clear_trash to manage.\n"
                "- Version directory: Permanently removed ({version_dir}/{project_id}/)\n"
                "  Trash directory is typically 'data/trash' (config: code_analysis.storage.trash_dir)\n\n"
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
                "project_id": {
                    "description": (
                        "Project UUID (UUID4). Required. "
                        "The project identifier to delete. "
                        "Can be obtained from list_projects command. "
                        "The project must exist in the database."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                        "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    ],
                },
                "dry_run": {
                    "description": (
                        "If True, only shows what would be deleted without actually deleting. "
                        "Default is False. ALWAYS use dry_run=True first to preview deletion. "
                        "This is a safety feature to prevent accidental deletions."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "delete_from_disk": {
                    "description": (
                        "If True, moves project root directory to trash (recycle bin) and deletes version directory. "
                        "If False (default), only deletes from database. "
                        "Trashed projects can be listed with list_trashed_projects and permanently removed with permanently_delete_from_trash or clear_trash."
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
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "dry_run": True,
                    },
                    "explanation": (
                        "Shows statistics about what would be deleted without actually deleting. "
                        "Safe to run to preview deletion. Always use this first before actual deletion."
                    ),
                },
                {
                    "description": "Delete project from database only",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    },
                    "explanation": (
                        "Permanently deletes project and all its data from database. "
                        "Project files on disk are NOT deleted. "
                        "WARNING: This is permanent and cannot be undone."
                    ),
                },
                {
                    "description": "Delete project from database and move to trash",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "delete_from_disk": True,
                    },
                    "explanation": (
                        "Deletes project from database and moves project directory to trash (recycle bin). "
                        "Version directory is permanently deleted. Use list_trashed_projects to see trashed items; "
                        "permanently_delete_from_trash or clear_trash to remove from disk permanently."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project with specified project_id not found in database",
                    "example": "project_id='550e8400-e29b-41d4-a716-446655440000' but project not in database",
                    "solution": (
                        "Verify project exists. Run list_projects to see all projects and their IDs. "
                        "Ensure the project_id is correct and the project is registered in the database."
                    ),
                },
                "CONFIG_NOT_FOUND": {
                    "description": "Server configuration file (config.json) not found or cannot be loaded",
                    "example": "config.json missing or invalid",
                    "solution": (
                        "Ensure config.json exists and is valid JSON. "
                        "The configuration file is required to resolve database path."
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
                        "message": "Deleted project my_project (928bcf10-db1c-47a3-8341-f60a6d997fe7)",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, DATABASE_ERROR, DELETE_PROJECT_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error details",
                },
            },
            "best_practices": [
                "ALWAYS use dry_run=True first to preview what will be deleted",
                "Verify project_id is correct before deletion - use list_projects to get project IDs",
                "Backup database before deleting important projects",
                "This operation is permanent - double-check before proceeding",
                "By default, project files on disk are NOT deleted, only database records",
                "Use list_projects to verify project exists and get correct project_id before deletion",
                "Database path is automatically resolved from server configuration, no root_dir needed",
            ],
        }
