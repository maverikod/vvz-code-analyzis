"""
MCP command: list_projects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
from pathlib import Path

from ...core.sql_portable import WHERE_FILES_ACTIVE, WHERE_PROJECTS_ACTIVE_P
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
    descr = (
        "List active (non–soft-deleted) projects with UUID and metadata; "
        "set include_deleted to include trashed project rows."
    )
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
                "List projects with UUID and metadata. By default excludes rows "
                "soft-deleted to trash (projects.deleted). Optional filters: "
                "watched_dir_id, name_contains, comment_contains, include_deleted. "
                "Database path is resolved from server configuration."
            ),
            "properties": {
                "include_deleted": {
                    "type": "boolean",
                    "description": (
                        "If true, return all rows from ``projects`` (active and soft-deleted), "
                        "including projects that only have trashed file rows. "
                        "Default false — only operational projects (active files or empty)."
                    ),
                    "default": False,
                },
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
                {"include_deleted": True},
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
                "The list_projects command returns projects from the database with: "
                "project id, watch_dir (observed directory path), name, comment (description), "
                "root_path, watch_dir_id, updated_at.\n\n"
                "**By default** rows with ``projects.deleted`` set (soft-deleted / in trash) "
                "are **excluded**, so the list matches operational “active” projects. "
                "Pass ``include_deleted: true`` to list **every** ``projects`` row (active "
                "and soft-deleted), including projects whose files are all in trash — same "
                "lifecycle as ``list_trashed_projects`` / ``project_set_mark_del``. Each item "
                "includes a boolean ``deleted`` field.\n\n"
                "Optional filters: watched_dir_id (UUID), name_contains (substring in name), "
                "comment_contains (substring in comment/description). All filters are case-insensitive.\n\n"
                "Operation flow:\n"
                "1. Validates all present parameters against schema (strict type check)\n"
                "2. Opens database from server configuration (config.json)\n"
                "3. Applies watched_dir_id filter if provided\n"
                "4. Applies name_contains and comment_contains substring filters if provided\n"
                "5. Resolves watch_dir path from watch_dir_paths table\n"
                "6. Returns list with id, watch_dir, name, comment, root_path, watch_dir_id, "
                "processing_paused, deleted, updated_at\n\n"
                "Use cases:\n"
                "- Discover all projects and get project_id (UUID) for other commands\n"
                "- Find projects by name or description: use name_contains or comment_contains\n"
                "- Filter by watched directory with watched_dir_id\n\n"
                "Important: project_id in other commands must be the UUID (id), not the name."
            ),
            "parameters": {
                "include_deleted": {
                    "description": (
                        "When false (default), omit soft-deleted projects (``projects.deleted``). "
                        "When true, include them alongside active projects."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
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
        include_deleted: bool = False,
    ) -> SuccessResult | ErrorResult:
        """Run blocking DB work for list_projects (called from executor).

        Uses a single SQL query that fetches active projects and watch_dir_paths
        (LEFT JOIN) in one round-trip to minimize DB lock time.
        """
        try:
            from code_analysis.core.database.watch_dirs_partition import (
                current_server_instance_id,
                sql_watch_dir_paths_join,
            )

            database = self._open_database_from_config(auto_analyze=False)
            try:
                sid = current_server_instance_id()
                wdp_join = sql_watch_dir_paths_join("p", "w")
                # When include_deleted: all rows from ``projects`` (soft-deleted projects
                # often have only trashed file rows — they must not be dropped by the
                # active-files INNER JOIN used for the default list).
                if include_deleted:
                    _list_sql = (
                        "SELECT p.id, p.root_path, p.name, p.comment, p.watch_dir_id, "
                        "p.processing_paused, p.created_at, p.updated_at, p.deleted, "
                        "w.absolute_path AS watch_dir_path "
                        "FROM projects p "
                        f"{wdp_join} "
                        "WHERE p.server_instance_id = ? "
                        "ORDER BY p.created_at"
                    )
                else:
                    _proj_del = f" AND {WHERE_PROJECTS_ACTIVE_P}"
                    _list_sql = (
                        "SELECT p.id, p.root_path, p.name, p.comment, p.watch_dir_id, "
                        "p.processing_paused, p.created_at, p.updated_at, p.deleted, "
                        "w.absolute_path AS watch_dir_path "
                        "FROM ("
                        "  SELECT p.* FROM projects p "
                        "  WHERE p.server_instance_id = ? "
                        "  AND p.id IN ("
                        "    SELECT project_id FROM files "
                        "    WHERE " + WHERE_FILES_ACTIVE + " GROUP BY project_id"
                        "  )" + _proj_del + "  UNION "
                        "  SELECT p.* FROM projects p "
                        "  WHERE p.server_instance_id = ? "
                        "  AND p.id NOT IN (SELECT project_id FROM files)"
                        + _proj_del
                        + ") p "
                        f"{wdp_join} "
                        "ORDER BY p.created_at"
                    )
                list_params = (sid,) if include_deleted else (sid, sid)
                result = database.execute(_list_sql, list_params)
                raw_rows = (
                    result.get("data", [])
                    if isinstance(result, dict)
                    else (result if isinstance(result, list) else [])
                )

                projects = []
                for row in raw_rows if isinstance(raw_rows, list) else []:
                    if not isinstance(row, dict):
                        continue
                    updated_at = row.get("updated_at")
                    if updated_at is not None and hasattr(updated_at, "isoformat"):
                        updated_at = updated_at.isoformat()
                    processing_paused = row.get("processing_paused")
                    deleted_raw = row.get("deleted")
                    deleted_flag = (
                        bool(deleted_raw) if deleted_raw is not None else False
                    )
                    from ...core.project_root_path import (
                        is_legacy_projects_root_path_absolute_storage,
                        resolve_project_root_absolute_str,
                        resolve_watch_dir_absolute_for_project_row,
                    )

                    stored_root = str(row.get("root_path") or "")
                    watch_dir_id_val = row.get("watch_dir_id")
                    project_name = str(row.get("name") or "").strip() or None
                    project_id_val = str(row.get("id") or "").strip() or None
                    resolved_root = resolve_project_root_absolute_str(
                        project_id=project_id_val,
                        root_path_stored=stored_root,
                        watch_dir_id=(
                            str(watch_dir_id_val)
                            if watch_dir_id_val is not None
                            else None
                        ),
                        project_name=project_name,
                        database=database,
                        require_exists=True,
                    )
                    resolved_watch = resolve_watch_dir_absolute_for_project_row(
                        project_id=project_id_val,
                        root_path_stored=stored_root,
                        watch_dir_id=(
                            str(watch_dir_id_val)
                            if watch_dir_id_val is not None
                            else None
                        ),
                        project_name=project_name,
                        database=database,
                    )
                    display_root = stored_root
                    if resolved_root:
                        try:
                            watch_for_segment = resolved_watch or row.get(
                                "watch_dir_path"
                            )
                            if watch_for_segment and not (
                                is_legacy_projects_root_path_absolute_storage(
                                    stored_root
                                )
                            ):
                                rel = (
                                    Path(resolved_root)
                                    .resolve()
                                    .relative_to(Path(str(watch_for_segment)).resolve())
                                )
                                if len(rel.parts) == 1:
                                    display_root = rel.parts[0]
                        except (OSError, ValueError):
                            pass
                    projects.append(
                        {
                            "id": row.get("id"),
                            "watch_dir": resolved_watch or row.get("watch_dir_path"),
                            "name": row.get("name"),
                            "root_path": display_root,
                            "comment": row.get("comment"),
                            "watch_dir_id": row.get("watch_dir_id"),
                            "processing_paused": (
                                bool(processing_paused)
                                if processing_paused is not None
                                else False
                            ),
                            "deleted": deleted_flag,
                            "updated_at": updated_at,
                        }
                    )

                if watched_dir_id:
                    watch_dir = database.select(
                        "watch_dirs",
                        where={
                            "server_instance_id": sid,
                            "id": watched_dir_id,
                        },
                        limit=1,
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
                    projects = [
                        p for p in projects if p.get("watch_dir_id") == watched_dir_id
                    ]

                if name_contains is not None:
                    needle = name_contains.lower()
                    projects = [
                        p
                        for p in projects
                        if str(p.get("name") or "").lower().find(needle) >= 0
                    ]
                if comment_contains is not None:
                    needle = comment_contains.lower()
                    projects = [
                        p
                        for p in projects
                        if str(p.get("comment") or "").lower().find(needle) >= 0
                    ]

                parts = []
                if watched_dir_id:
                    parts.append(f"watched_dir_id: {watched_dir_id}")
                if name_contains is not None:
                    parts.append(f"name_contains: {name_contains!r}")
                if comment_contains is not None:
                    parts.append(f"comment_contains: {comment_contains!r}")
                if include_deleted:
                    parts.append("include_deleted: true")
                filter_msg = (
                    (" (filtered by " + ", ".join(parts) + ")") if parts else ""
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
        name_contains: Optional[str] = None,
        comment_contains: Optional[str] = None,
        include_deleted: Optional[bool] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute list projects command.

        Args:
            self: Command instance.
            watched_dir_id: Optional watched directory identifier (UUID4) to filter projects.
            name_contains: Optional substring to filter by project name (case-insensitive).
            comment_contains: Optional substring to filter by project comment (case-insensitive).
            include_deleted: If true, include soft-deleted (trashed) project rows.
            **kwargs: Extra args; validated and rejected if not in schema.

        Returns:
            SuccessResult with list of projects or ErrorResult on failure.
        """
        params: Dict[str, Any] = {
            "watched_dir_id": watched_dir_id,
            "name_contains": name_contains,
            "comment_contains": comment_contains,
            "include_deleted": include_deleted,
        }
        params.update(kwargs)
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            return self._handle_error(e, "VALIDATION_ERROR", "list_projects")
        watched_dir_id = params.get("watched_dir_id")
        name_contains = params.get("name_contains")
        comment_contains = params.get("comment_contains")
        if params.get("include_deleted") is None:
            include_deleted_effective = False
        else:
            include_deleted_effective = bool(params["include_deleted"])
        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._run_list_projects_sync(
                        watched_dir_id,
                        name_contains,
                        comment_contains,
                        include_deleted_effective,
                    ),
                ),
                timeout=_LIST_PROJECTS_DB_TIMEOUT,
            )
            return result
        except asyncio.TimeoutError:
            logger.debug(
                "[CHAIN] list_projects asyncio.TimeoutError timeout_s=%s",
                _LIST_PROJECTS_DB_TIMEOUT,
            )
            return self._handle_error(
                TimeoutError(
                    f"list_projects did not complete within {_LIST_PROJECTS_DB_TIMEOUT}s"
                ),
                "LIST_PROJECTS_TIMEOUT",
                "list_projects",
            )
