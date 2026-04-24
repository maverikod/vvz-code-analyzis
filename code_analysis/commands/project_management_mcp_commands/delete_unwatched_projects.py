"""
MCP command: delete_unwatched_projects.

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
        "Delete only orphaned project records from DB (root_path not on disk or invalid). "
        "Keeps projects that exist on disk but are outside watch_dirs. Cannot be undone."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True  # Deletion of multiple projects; run via queue

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
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self: "DeleteUnwatchedProjectsMCPCommand",
        watched_dirs: Optional[List[str]] = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute delete unwatched projects command.

        Args:
            self: Command instance.
            watched_dirs: Optional list of watched directories.
            dry_run: If True, only show what would be deleted.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with deletion summary or ErrorResult on failure.
        """
        try:
            config_path = self._resolve_config_path()
            config_dir = config_path.parent.resolve()
            if watched_dirs is None:
                from ...core.storage_paths import load_raw_config

                config_data = load_raw_config(config_path)
                worker_config = config_data.get("code_analysis", {}).get("worker", {})
                config_watch_dirs = worker_config.get("watch_dirs", [])
                watched_dirs = []
                for item in config_watch_dirs:
                    if isinstance(item, dict) and "path" in item:
                        watched_dirs.append(item["path"])
                    elif isinstance(item, str):
                        watched_dirs.append(item)

            if not watched_dirs:
                return self._handle_error(
                    ValidationError(
                        "No watched directories found in config and none provided",
                        field="watched_dirs",
                        details={},
                    ),
                    "NO_WATCHED_DIRS",
                    "delete_unwatched_projects",
                )

            database = self._open_database_from_config(auto_analyze=False)
            try:
                from ..delete_unwatched_projects_command import (
                    DeleteUnwatchedProjectsCommand,
                )

                cmd = DeleteUnwatchedProjectsCommand(
                    database=database,
                    watched_dirs=watched_dirs,
                    dry_run=dry_run,
                    server_root_dir=str(config_dir),
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
                "The delete_unwatched_projects command deletes only ORPHANED project records from "
                "the database: projects whose root_path does not exist on disk or is invalid. It does "
                "NOT delete projects that exist on disk but are outside the current watched directories "
                "(those are kept; reason exists_on_disk_but_not_in_watch_dirs). File-operating commands "
                "work only within watched directories; this command only cleans DB records for projects "
                "that no longer have a valid root on disk.\n\n"
                "Operation flow:\n"
                "1. Gets watched directories from config or parameter\n"
                "2. Discovers all projects in watched directories using project discovery\n"
                "3. Gets all projects from database\n"
                "4. For each DB project: invalid path or server root protected; root_path not exists -> "
                "marked for deletion (orphaned); root exists and in discovered list -> kept; root exists "
                "but not in discovered list -> KEPT (exists_on_disk_but_not_in_watch_dirs).\n"
                "5. If dry_run=True: reports what would be deleted/kept; no actual deletion\n"
                "6. If dry_run=False: deletes only marked (orphaned) project data via clear_project_data\n"
                "7. Returns deletion summary\n\n"
                "Protection:\n"
                "- Server root directory is always protected from deletion\n"
                "- Projects that exist on disk but are not in watch_dirs are KEPT (no file operations "
                "outside watched dirs)\n"
                "- Only orphaned DB records (root_path missing/invalid) are deleted\n\n"
                "Use cases: Remove orphaned project records from database (root moved or deleted on disk); "
                "maintain database cleanliness.\n\n"
                "Important notes:\n"
                "- This operation is PERMANENT and cannot be undone\n"
                "- Always use dry_run=True first to preview what will be deleted\n"
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
                        "config.json (code_analysis.worker.watch_dirs) only. These are the directories "
                        "where projects should be kept."
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
                        "Deletes only orphaned project records (root_path missing on disk) using config. "
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
                        "Deletes only orphaned project records (root_path missing on disk); watched_dirs override config. "
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
                        "success": (
                            "True if no per-project deletion failures; discovery issues "
                            "use discovery_warnings / discovery_errors and do not flip success alone"
                        ),
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
                            "- reason: Reason for keeping (discovered_in_watch_dirs, "
                            "under_watch_dir_project_root, exists_on_disk_but_not_in_watch_dirs, "
                            "server_root_protected)"
                        ),
                        "discovery_warnings": (
                            "Non-fatal discovery issues (e.g. duplicate project_id in a watch_dir)"
                        ),
                        "discovery_errors": "Unexpected failures while scanning a watch_dir (if any)",
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
                        "discovery_warnings": None,
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
                "Check discovery_warnings and discovery_errors for discovery issues",
            ],
        }
