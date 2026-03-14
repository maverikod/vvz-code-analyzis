"""
MCP command: list_projects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio

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

# Timeout for the whole run (open_db + list_projects + watch_dir_paths).
# open_database_from_config includes: ensure_database_integrity (check_sqlite_integrity
# can block up to 2s on locked DB) and db.connect() (retries up to 5s after restart).
# So 5s was too low; use 15s so list_projects completes after server restart.
_LIST_PROJECTS_DB_TIMEOUT = 15.0


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
        use_queue: False — fast read-only DB query; runs in HTTP handler (sync).
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
            "description": (
                "List all projects in the database with their UUID and metadata. "
                "Allowed parameter: watched_dir_id (optional). Does NOT accept root_dir; "
                "database path is resolved from server configuration."
            ),
            "properties": {
                "watched_dir_id": {
                    "type": "string",
                    "description": (
                        "Optional watched directory identifier (UUID4). "
                        "If provided, only projects from this watched directory will be returned. "
                        "If not provided, all projects from all watched directories are returned."
                    ),
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                    ],
                },
            },
            "required": [],
            "additionalProperties": False,
            "examples": [
                {},
                {
                    "watched_dir_id": "550e8400-e29b-41d4-a716-446655440000",
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
                "and returns for each project: project id, watch_dir (observed directory path), "
                "and project directory name, plus root_path, comment, watch_dir_id, updated_at.\n\n"
                "Parameters: Only watched_dir_id (optional). Database path is from server config only.\n\n"
                "Operation flow:\n"
                "1. Opens database from server configuration (config.json)\n"
                "2. If watched_dir_id is provided, filters projects by watched_dir_id\n"
                "3. For each project, resolves watch_dir path from watch_dir_paths table\n"
                "4. Returns list with id, watch_dir (path), name (project dir name), and other metadata\n\n"
                "Use cases:\n"
                "- Discover all projects and get project_id for other commands\n"
                "- Get watch_dir path and project directory name per project\n"
                "- Filter projects by watched directory\n\n"
                "Important: Each project always includes id, watch_dir (path or None), and name."
            ),
            "parameters": {
                "watched_dir_id": {
                    "description": (
                        "Optional watched directory identifier (UUID4). "
                        "If provided, only projects belonging to this watched directory will be returned. "
                        "If not provided or omitted, all projects from all watched directories are returned. "
                        "The watched_dir_id can be found in the watch_dirs table or obtained from project metadata. "
                        "This command has no other parameters; root_dir is not accepted (database path from server config)."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Basic usage: list all projects",
                    "command": {},
                    "explanation": (
                        "Retrieves all projects from the database and returns their UUID, "
                        "root path, name, comment, watch_dir_id, and last update time. "
                        "Database path is automatically resolved from server configuration."
                    ),
                },
                {
                    "description": "List projects from specific watched directory",
                    "command": {
                        "watched_dir_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                    "explanation": (
                        "Lists only projects that belong to the specified watched directory. "
                        "Useful for filtering projects by their watch directory location."
                    ),
                },
            ],
            "error_cases": {
                "CONFIG_NOT_FOUND": {
                    "description": "Server configuration file (config.json) not found or cannot be loaded",
                    "example": "config.json missing or invalid",
                    "solution": (
                        "Ensure config.json exists and is valid JSON. "
                        "The configuration file is required to resolve database path."
                    ),
                },
                "DATABASE_NOT_FOUND": {
                    "description": "Database file not found at the path resolved from configuration",
                    "example": "Database path from config.json points to non-existent file",
                    "solution": (
                        "Ensure the database file exists at the configured path. "
                        "You may need to run update_indexes or restore_database first to create the database."
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
                "INVALID_WATCHED_DIR_ID": {
                    "description": "watched_dir_id provided but not found in database",
                    "example": "watched_dir_id='invalid-uuid' or watched_dir_id not in watch_dirs table",
                    "solution": (
                        "Verify the watched_dir_id is a valid UUID4 and exists in the watch_dirs table. "
                        "Use list_projects without filter first to see available projects and their watch_dir_id values."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "projects": (
                            "List of project dictionaries. Each project always includes:\n"
                            "- id: Project UUID (string)\n"
                            "- watch_dir: Watched directory absolute path (string, or None if not linked)\n"
                            "- name: Project directory name (string, may be None)\n"
                            "Additional fields: root_path, comment, watch_dir_id, updated_at."
                        ),
                        "count": "Number of projects found (integer)",
                    },
                    "example": {
                        "projects": [
                            {
                                "id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                                "watch_dir": "/home/user/watch_dirs/main",
                                "name": "vast_srv",
                                "root_path": "/home/user/watch_dirs/main/vast_srv",
                                "comment": None,
                                "watch_dir_id": "550e8400-e29b-41d4-a716-446655440000",
                                "updated_at": "2026-01-15T10:30:00.123456",
                            },
                            {
                                "id": "36ebabd4-a480-4175-8129-2789f89beb40",
                                "watch_dir": "/home/user/watch_dirs/main",
                                "name": "code_analysis",
                                "root_path": "/home/user/watch_dirs/main/code_analysis",
                                "comment": "Main code analysis tool",
                                "watch_dir_id": "550e8400-e29b-41d4-a716-446655440000",
                                "updated_at": "2026-01-15T11:45:00.789012",
                            },
                        ],
                        "count": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., CONFIG_NOT_FOUND, DATABASE_ERROR, LIST_PROJECTS_ERROR, INVALID_WATCHED_DIR_ID)",
                    "message": "Human-readable error message",
                    "details": "Additional error details",
                },
            },
        }

    def _run_list_projects_sync(
        self: "ListProjectsMCPCommand",
        watched_dir_id: Optional[str] = None,
    ) -> SuccessResult | ErrorResult:
        """Run blocking DB work for list_projects (called from executor).

        Uses one list_projects query and one batch query for watch_dir_paths
        (WHERE watch_dir_id IN (...)) instead of N+1 per-project selects.
        """
        try:
            database = self._open_database_from_config(auto_analyze=False)
            try:
                project_objects = database.list_projects()

                if watched_dir_id:
                    watch_dir = database.select(
                        "watch_dirs", where={"id": watched_dir_id}, limit=1
                    )
                    if not watch_dir:
                        from ...core.exceptions import ValidationError

                        return self._handle_error(
                            ValidationError(
                                f"Watched directory not found: {watched_dir_id}",
                                field="watched_dir_id",
                                details={"watched_dir_id": watched_dir_id},
                            ),
                            "INVALID_WATCHED_DIR_ID",
                            "list_projects",
                        )

                    project_objects = [
                        p for p in project_objects if p.watch_dir_id == watched_dir_id
                    ]

                # One batch query for all watch_dir paths (no N+1).
                watch_dir_ids = list(
                    {p.watch_dir_id for p in project_objects if p.watch_dir_id}
                )
                path_by_watch_dir: Dict[str, str] = {}
                if watch_dir_ids:
                    placeholders = ",".join("?" * len(watch_dir_ids))
                    sql = (
                        "SELECT watch_dir_id, absolute_path FROM watch_dir_paths "
                        f"WHERE watch_dir_id IN ({placeholders})"
                    )
                    result = database.execute(sql, tuple(watch_dir_ids))
                    rows = result.get("data") if isinstance(result, dict) else []
                    if isinstance(rows, list):
                        for row in rows:
                            if isinstance(row, dict) and row.get("absolute_path"):
                                path_by_watch_dir[row["watch_dir_id"]] = row[
                                    "absolute_path"
                                ]

                projects = []
                for project in project_objects:
                    watch_dir_path = (
                        path_by_watch_dir.get(project.watch_dir_id)
                        if project.watch_dir_id
                        else None
                    )
                    project_dict = {
                        "id": project.id,
                        "watch_dir": watch_dir_path,
                        "name": project.name,
                        "root_path": project.root_path,
                        "comment": project.comment,
                        "watch_dir_id": project.watch_dir_id,
                        "updated_at": (
                            project.updated_at.isoformat()
                            if project.updated_at
                            else None
                        ),
                    }
                    projects.append(project_dict)

                filter_msg = (
                    f" (filtered by watched_dir_id: {watched_dir_id})"
                    if watched_dir_id
                    else ""
                )

                return SuccessResult(
                    data={
                        "projects": projects,
                        "count": len(projects),
                    },
                    message=f"Found {len(projects)} project(s){filter_msg}",
                )
            finally:
                database.disconnect()
        except Exception as e:
            return self._handle_error(e, "LIST_PROJECTS_ERROR", "list_projects")

    async def execute(
        self: "ListProjectsMCPCommand",
        watched_dir_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute list projects command.

        Args:
            self: Command instance.
            watched_dir_id: Optional watched directory identifier (UUID4) to filter projects.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with list of projects or ErrorResult on failure.
        """
        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    self._run_list_projects_sync,
                    watched_dir_id,
                ),
                timeout=_LIST_PROJECTS_DB_TIMEOUT,
            )
            return result
        except asyncio.TimeoutError:
            return self._handle_error(
                TimeoutError(
                    f"list_projects did not complete within {_LIST_PROJECTS_DB_TIMEOUT}s"
                ),
                "LIST_PROJECTS_TIMEOUT",
                "list_projects",
            )
