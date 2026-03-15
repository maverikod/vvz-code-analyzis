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
                "Optional filters: watched_dir_id, name_contains, comment_contains. "
                "Database path is resolved from server configuration."
            ),
            "properties": {
                "watched_dir_id": {
                    "type": "string",
                    "description": (
                        "Optional watched directory identifier (UUID4). "
                        "If provided, only projects from this watched directory will be returned."
                    ),
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                    ],
                },
                "name_contains": {
                    "type": "string",
                    "description": (
                        "Optional substring to filter projects by name (case-insensitive). "
                        "Only projects whose name contains this string are returned."
                    ),
                    "examples": ["vast_srv", "code_analysis"],
                },
                "comment_contains": {
                    "type": "string",
                    "description": (
                        "Optional substring to filter projects by comment/description (case-insensitive). "
                        "Only projects whose comment contains this string are returned."
                    ),
                    "examples": ["AI Admin", "pipeline"],
                },
            },
            "required": [],
            "additionalProperties": False,
            "examples": [
                {},
                {"watched_dir_id": "550e8400-e29b-41d4-a716-446655440000"},
                {"name_contains": "vast_srv"},
                {"comment_contains": "pipeline"},
            ],
        }

    def validate_params(
        self: "ListProjectsMCPCommand", params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate params; if watched_dir_id is provided, ensure it exists."""
        params = super().validate_params(params)
        watched_dir_id = params.get("watched_dir_id")
        if watched_dir_id:
            BaseMCPCommand._validate_watch_dir_id_exists(watched_dir_id)
        return params

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
                "name, comment (description), root_path, watch_dir_id, updated_at.\n\n"
                "Optional filters: watched_dir_id (UUID), name_contains (substring in name), "
                "comment_contains (substring in comment/description). All filters are case-insensitive.\n\n"
                "Operation flow:\n"
                "1. Validates all present parameters against schema (strict type check)\n"
                "2. Opens database from server configuration (config.json)\n"
                "3. Applies watched_dir_id filter if provided\n"
                "4. Applies name_contains and comment_contains substring filters if provided\n"
                "5. Resolves watch_dir path from watch_dir_paths table\n"
                "6. Returns list with id, watch_dir, name, comment, root_path, watch_dir_id, updated_at\n\n"
                "Use cases:\n"
                "- Discover all projects and get project_id (UUID) for other commands\n"
                "- Find projects by name or description: use name_contains or comment_contains\n"
                "- Filter by watched directory with watched_dir_id\n\n"
                "Important: project_id in other commands must be the UUID (id), not the name."
            ),
            "parameters": {
                "watched_dir_id": {
                    "description": "Optional watched directory identifier (UUID4). Filter by watch_dir.",
                    "type": "string",
                    "required": False,
                    "examples": [
                        "550e8400-e29b-41d4-a716-446655440000",
                        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    ],
                },
                "name_contains": {
                    "description": (
                        "Optional substring to filter by project name (case-insensitive). "
                        "Use to find project by name and then use returned id as project_id."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["vast_srv", "code_analysis"],
                },
                "comment_contains": {
                    "description": (
                        "Optional substring to filter by project comment/description (case-insensitive)."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["AI Admin", "pipeline"],
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
                        "Lists only projects that belong to the specified watched directory."
                    ),
                },
                {
                    "description": "Find projects by name (e.g. get project_id for vast_srv)",
                    "command": {"name_contains": "vast_srv"},
                    "explanation": (
                        "Returns projects whose name contains 'vast_srv'. Use the returned id as project_id in other commands."
                    ),
                },
                {
                    "description": "Find projects by description/comment",
                    "command": {"comment_contains": "pipeline"},
                    "explanation": "Returns projects whose comment contains 'pipeline'.",
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
        name_contains: Optional[str] = None,
        comment_contains: Optional[str] = None,
    ) -> SuccessResult | ErrorResult:
        """Run blocking DB work for list_projects (called from executor).

        Uses one list_projects query and one batch query for watch_dir_paths
        (WHERE watch_dir_id IN (...)) instead of N+1 per-project selects.
        """
        # #region agent log
        _t2 = __import__("time").time()
        try:
            _log2 = (
                __import__("json").dumps(
                    {
                        "sessionId": "880dc2",
                        "hypothesisId": "H3",
                        "location": "list_projects._run_sync.entry",
                        "message": "sync_entry",
                        "data": {"t2": _t2},
                        "timestamp": int(_t2 * 1000),
                    }
                )
                + "\n"
            )
            open(
                "/home/vasilyvz/projects/tools/code_analysis/.cursor/debug-880dc2.log",
                "a",
            ).write(_log2)
        except Exception:  # noqa: S110
            pass
        # #endregion
        try:
            database = self._open_database_from_config(auto_analyze=False)
            # #region agent log
            _t3 = __import__("time").time()
            try:
                _log3 = (
                    __import__("json").dumps(
                        {
                            "sessionId": "880dc2",
                            "hypothesisId": "H1",
                            "location": "list_projects._run_sync.after_open_db",
                            "message": "after_open_db",
                            "data": {
                                "t3": _t3,
                                "elapsed_ms": round((_t3 - _t2) * 1000),
                            },
                            "timestamp": int(_t3 * 1000),
                        }
                    )
                    + "\n"
                )
                open(
                    "/home/vasilyvz/projects/tools/code_analysis/.cursor/debug-880dc2.log",
                    "a",
                ).write(_log3)
            except Exception:  # noqa: S110
                pass
            # #endregion
            try:
                project_objects = database.list_projects()
                # #region agent log
                _t4 = __import__("time").time()
                try:
                    _log4 = (
                        __import__("json").dumps(
                            {
                                "sessionId": "880dc2",
                                "hypothesisId": "H2",
                                "location": "list_projects._run_sync.after_list_projects",
                                "message": "after_list_projects",
                                "data": {
                                    "t4": _t4,
                                    "elapsed_ms": round((_t4 - _t3) * 1000),
                                    "n": len(project_objects),
                                },
                                "timestamp": int(_t4 * 1000),
                            }
                        )
                        + "\n"
                    )
                    open(
                        "/home/vasilyvz/projects/tools/code_analysis/.cursor/debug-880dc2.log",
                        "a",
                    ).write(_log4)
                except Exception:  # noqa: S110
                    pass
                # #endregion

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

                if name_contains is not None:
                    needle = name_contains.lower()
                    project_objects = [
                        p
                        for p in project_objects
                        if (p.name or "").lower().find(needle) >= 0
                    ]
                if comment_contains is not None:
                    needle = comment_contains.lower()
                    project_objects = [
                        p
                        for p in project_objects
                        if (p.comment or "").lower().find(needle) >= 0
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

                parts = []
                if watched_dir_id:
                    parts.append(f"watched_dir_id: {watched_dir_id}")
                if name_contains is not None:
                    parts.append(f"name_contains: {name_contains!r}")
                if comment_contains is not None:
                    parts.append(f"comment_contains: {comment_contains!r}")
                filter_msg = (
                    (" (filtered by " + ", ".join(parts) + ")") if parts else ""
                )
                # #region agent log
                _t6 = __import__("time").time()
                try:
                    _log6 = (
                        __import__("json").dumps(
                            {
                                "sessionId": "880dc2",
                                "hypothesisId": "H5",
                                "location": "list_projects._run_sync.before_return",
                                "message": "before_return",
                                "data": {
                                    "t6": _t6,
                                    "elapsed_since_t4_ms": round((_t6 - _t4) * 1000),
                                },
                                "timestamp": int(_t6 * 1000),
                            }
                        )
                        + "\n"
                    )
                    open(
                        "/home/vasilyvz/projects/tools/code_analysis/.cursor/debug-880dc2.log",
                        "a",
                    ).write(_log6)
                except Exception:  # noqa: S110
                    pass
                # #endregion

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
        name_contains: Optional[str] = None,
        comment_contains: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute list projects command.

        Args:
            self: Command instance.
            watched_dir_id: Optional watched directory identifier (UUID4) to filter projects.
            name_contains: Optional substring to filter by project name (case-insensitive).
            comment_contains: Optional substring to filter by project comment (case-insensitive).
            **kwargs: Extra args; validated and rejected if not in schema.

        Returns:
            SuccessResult with list of projects or ErrorResult on failure.
        """
        # #region agent log
        _t0 = __import__("time").time()
        try:
            _log = (
                __import__("json").dumps(
                    {
                        "sessionId": "880dc2",
                        "hypothesisId": "H4",
                        "location": "list_projects.execute.entry",
                        "message": "entry",
                        "data": {"t0": _t0},
                        "timestamp": int(_t0 * 1000),
                    }
                )
                + "\n"
            )
            open(
                "/home/vasilyvz/projects/tools/code_analysis/.cursor/debug-880dc2.log",
                "a",
            ).write(_log)
        except Exception:  # noqa: S110
            pass
        # #endregion
        params: Dict[str, Any] = {
            "watched_dir_id": watched_dir_id,
            "name_contains": name_contains,
            "comment_contains": comment_contains,
        }
        params.update(kwargs)
        schema_props = set((self.get_schema().get("properties") or {}).keys())
        params_present = {
            k: v for k, v in params.items() if v is not None and k in schema_props
        }
        BaseMCPCommand.validate_params_against_schema(
            params_present,
            self.get_schema(),
            command_name=self.name,
        )
        # #region agent log
        _t1 = __import__("time").time()
        try:
            _log1 = (
                __import__("json").dumps(
                    {
                        "sessionId": "880dc2",
                        "hypothesisId": "H4",
                        "location": "list_projects.execute.after_validate",
                        "message": "after_validate",
                        "data": {"t1": _t1, "elapsed_ms": round((_t1 - _t0) * 1000)},
                        "timestamp": int(_t1 * 1000),
                    }
                )
                + "\n"
            )
            open(
                "/home/vasilyvz/projects/tools/code_analysis/.cursor/debug-880dc2.log",
                "a",
            ).write(_log1)
        except Exception:  # noqa: S110
            pass
        # #endregion
        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    self._run_list_projects_sync,
                    watched_dir_id,
                    name_contains,
                    comment_contains,
                ),
                timeout=_LIST_PROJECTS_DB_TIMEOUT,
            )
            # #region agent log
            _t_end = __import__("time").time()
            try:
                _log_end = (
                    __import__("json").dumps(
                        {
                            "sessionId": "880dc2",
                            "hypothesisId": "H4",
                            "location": "list_projects.execute.exit",
                            "message": "exit",
                            "data": {
                                "t_end": _t_end,
                                "elapsed_total_ms": round((_t_end - _t0) * 1000),
                                "elapsed_after_validate_ms": round(
                                    (_t_end - _t1) * 1000
                                ),
                            },
                            "timestamp": int(_t_end * 1000),
                        }
                    )
                    + "\n"
                )
                open(
                    "/home/vasilyvz/projects/tools/code_analysis/.cursor/debug-880dc2.log",
                    "a",
                ).write(_log_end)
            except Exception:  # noqa: S110
                pass
            # #endregion
            return result
        except asyncio.TimeoutError:
            # #region agent log
            _t_to = __import__("time").time()
            try:
                _log_to = (
                    __import__("json").dumps(
                        {
                            "sessionId": "880dc2",
                            "hypothesisId": "timeout",
                            "location": "list_projects.execute.timeout",
                            "message": "TimeoutError",
                            "data": {
                                "t_timeout": _t_to,
                                "elapsed_since_t0_ms": round((_t_to - _t0) * 1000),
                            },
                            "timestamp": int(_t_to * 1000),
                        }
                    )
                    + "\n"
                )
                open(
                    "/home/vasilyvz/projects/tools/code_analysis/.cursor/debug-880dc2.log",
                    "a",
                ).write(_log_to)
            except Exception:  # noqa: S110
                pass
            # #endregion
            return self._handle_error(
                TimeoutError(
                    f"list_projects did not complete within {_LIST_PROJECTS_DB_TIMEOUT}s"
                ),
                "LIST_PROJECTS_TIMEOUT",
                "list_projects",
            )
