"""
MCP command: project_set_mark_del (project removal / soft-delete).

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
    ValidationError,
    logger,
)


class DeleteProjectMCPCommand(BaseMCPCommand):
    """
    Delete or soft-delete a project (always through trash first).

    **Soft-delete stage (always):** marks project/files in the DB, moves the project
    root into ``trash_dir`` (recycle bin), and removes the per-project version folder.

    **Then:** ``delete_from_disk=False`` (default) additionally clears all project rows
    from the database and removes the FAISS index file; sources remain under trash until
    ``clear_trash`` / ``permanently_delete_from_trash``. ``delete_from_disk=True`` keeps DB
    rows for recovery and skips that permanent DB clear (trash cleanup later).

    Attributes:
        name: MCP command name (``project_set_mark_del``).
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "project_set_mark_del"
    version = "1.0.0"
    descr = (
        "Trash-first project removal: always moves project root into the trash "
        "(recycle bin) and marks it in the DB; then optionally clears DB/FAISS. "
        "Default: trash + full DB clear (sources stay under trash until purged)."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True  # Long-running (DB clear + disk); run via queue

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
                "Soft-delete to trash first: the project directory is moved under the "
                "configured trash_dir (recycle bin) and the project is marked deleted in the "
                "database. Depending on delete_from_disk, database rows may then be cleared "
                "or kept until trash cleanup. This is destructive for DB data when the "
                "permanent-clear path runs; on-disk sources under trash can be restored until "
                "permanently_delete_from_trash / clear_trash."
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
                        "If True: soft-delete to trash only — move project root to trash, remove version "
                        "dir; **database rows stay** until clear_trash / permanently_delete_from_trash. "
                        "If False (default): same trash step, then **permanently remove** all project data "
                        "from the database and delete the FAISS index file (sources still under trash until purged)."
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

    def validate_params(
        self: "DeleteProjectMCPCommand", params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate params and reject unknown project_id before queuing."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

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
            delete_from_disk: If True, soft-delete to trash only (keep DB rows). If False
                (default), trash step then full DB clear + remove FAISS index file.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with deletion summary or ErrorResult on failure.
        """
        extra = dict(kwargs)
        extra.pop("context", None)
        params: Dict[str, Any] = {
            "project_id": project_id,
            "dry_run": dry_run,
            "delete_from_disk": delete_from_disk,
        }
        params.update(extra)
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        project_id = params["project_id"]
        dry_run = bool(params.get("dry_run", False))
        delete_from_disk = bool(params.get("delete_from_disk", False))

        try:
            from ...core.exceptions import DatabaseError
            from pathlib import Path

            # Config and storage for version_dir/trash_dir (DeleteProjectCommand)
            from ...core.storage_paths import load_raw_config, resolve_storage_paths

            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )

            database = self._open_database_from_config(auto_analyze=False)

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
                        "project_set_mark_del",
                    )

                # Version / trash dirs: required for soft-delete stage (all modes).
                file_watcher_config = config_data.get("code_analysis", {}).get(
                    "file_watcher", {}
                )
                version_dir = file_watcher_config.get("version_dir")
                if not version_dir:
                    config_dir_path = Path(config_path).parent
                    version_dir = str(config_dir_path / "data" / "versions")
                trash_dir = str(storage.trash_dir)

                from ..project_deletion import DeleteProjectCommand

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
                        "project_set_mark_del",
                    )

                return SuccessResult(
                    data=result,
                    message=result.get("message", "Project deleted successfully"),
                )
            finally:
                database.disconnect()
        except Exception as e:
            return self._handle_error(e, "DELETE_PROJECT_ERROR", "project_set_mark_del")

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
                "**Trash / recycle bin (primary):** every run starts by moving the project "
                "root into `trash_dir` (timestamped folder) and marking the project/files in "
                "the database — i.e. removal goes **through the trash**, not by silently "
                "unlinking the tree in place.\n\n"
                "**After the trash step:** with `delete_from_disk=False` (default), the "
                "command then clears project rows from the database and removes the FAISS "
                "slice for the project; the tree remains on disk under trash until you use "
                "`permanently_delete_from_trash` / `clear_trash` or delete that folder. "
                "With `delete_from_disk=True`, DB rows stay for recovery until trash cleanup; "
                "the version directory under `version_dir` is still removed during soft-delete.\n\n"
                "Operation flow:\n"
                "1. Resolves database path from server configuration (config.json)\n"
                "2. Opens database connection\n"
                "3. Validates project_id exists in database and retrieves project information\n"
                "4. Retrieves project information and statistics\n"
                "5. If dry_run=True:\n"
                "   - Returns statistics and whether a soft-delete / permanent DB clear would run\n"
                "   - Does not perform actual deletion\n"
                "6. If dry_run=False:\n"
                "   a. Soft-delete stage (always): marks project and files in the database (including "
                "empty projects via projects.deleted), moves project root to trash, removes per-project "
                "version directory under version_dir.\n"
                "   b. If delete_from_disk=True: stops after soft-delete (DB rows kept for recovery "
                "until permanently_delete_from_trash / clear_trash).\n"
                "   c. If delete_from_disk=False: after soft-delete, permanently removes all project data "
                "from the database and deletes the on-disk FAISS index file for this project.\n"
                "   Disk errors during move/delete are logged; soft-delete DB markers still apply.\n"
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
                "Disk (soft-delete stage; runs for both modes):\n"
                "- Project root directory: moved under trash_dir with a timestamped folder name.\n"
                "- Version directory: per-project folder under version_dir removed.\n"
                "- With delete_from_disk=True only, trashed tree stays on disk until "
                "list_trashed_projects / permanently_delete_from_trash / clear_trash.\n"
                "- With delete_from_disk=False, trash folder remains after DB clear unless removed separately.\n\n"
                "Use cases:\n"
                "- Move a project out of the active tree into trash, then drop DB/index data\n"
                "- Keep DB rows but park sources in trash (delete_from_disk=True path)\n"
                "- Clean up test projects\n"
                "- Free up database and disk space after trash purge\n"
                "- Remove orphaned projects\n\n"
                "Important notes:\n"
                "- On disk, the project root always lands in trash first (recycle bin), not an instant shred\n"
                "- Database + FAISS clear (default path) cannot be undone; trashed files persist until purge\n"
                "- Always use dry_run=True first to preview what will be deleted\n"
                "- delete_from_disk=False (default): soft-delete to trash, then full database clear + FAISS file\n"
                "- delete_from_disk=True: soft-delete to trash only; database rows remain until trash cleanup commands\n"
                "- Disk deletion errors are logged but do not stop database deletion\n"
                "- All related data is cascaded and removed from database when the permanent-clear path runs\n"
                "- Use with extreme caution on the default path (DB + index cleared); True is softer on DB only"
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
                        "If True, soft-delete only (DB rows kept; use trash cleanup to purge). "
                        "If False (default), soft-delete then permanent database removal and FAISS file deletion."
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
                    "description": (
                        "Default: move project to trash, then clear DB and FAISS (sources stay in trash)"
                    ),
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    },
                    "explanation": (
                        "``delete_from_disk`` omitted (False): soft-delete moves the project tree into "
                        "``trash_dir``, then **all project rows are removed from the database** and the "
                        "FAISS slice is deleted. On-disk sources remain under trash until "
                        "``clear_trash`` / ``permanently_delete_from_trash``."
                    ),
                },
                {
                    "description": (
                        "Trash-only: move project to trash and **keep database rows** until trash cleanup"
                    ),
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "delete_from_disk": True,
                    },
                    "explanation": (
                        "``delete_from_disk=True``: same soft-delete (move root to trash, remove version dir), "
                        "but **no** permanent DB/FAISS clear — rows stay for recovery. Use "
                        "``list_trashed_projects``, then ``permanently_delete_from_trash`` or ``clear_trash`` "
                        "to purge disk and DB later."
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
                "Remember the project tree always goes to trash first (recycle bin), not silent unlink",
                "ALWAYS use dry_run=True first to preview what will be deleted",
                "Verify project_id is correct before deletion - use list_projects to get project IDs",
                "Backup database before deleting important projects",
                "DB-clear path is irreversible for rows; trashed folders remain until trash purge",
                "Default delete_from_disk=False moves the project root to trash then clears DB data",
                "Use list_projects to verify project exists and get correct project_id before deletion",
                "Database path is automatically resolved from server configuration, no root_dir needed",
            ],
        }
