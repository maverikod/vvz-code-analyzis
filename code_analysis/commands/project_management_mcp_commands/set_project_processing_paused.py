"""
MCP command: set_project_processing_paused.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ._shared import (
    Any,
    BaseMCPCommand,
    Dict,
    ErrorResult,
    SuccessResult,
    ValidationError,
)


class SetProjectProcessingPausedMCPCommand(BaseMCPCommand):
    """
    Set whether indexing and vectorization workers skip this project.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: False — fast UPDATE; runs in HTTP handler.
    """

    name = "set_project_processing_paused"
    version = "1.0.0"
    descr = (
        "Pause or resume background indexing and vectorization for a project. "
        "When paused, workers skip the project until cleared."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["SetProjectProcessingPausedMCPCommand"],
    ) -> Dict[str, Any]:
        """JSON schema for MCP Proxy validation."""
        return {
            "type": "object",
            "description": (
                "Set processing_paused on a project. When true, the indexing worker "
                "and vectorization worker skip this project until set back to false."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from list_projects or projectid file).",
                },
                "processing_paused": {
                    "type": "boolean",
                    "description": "True to pause background processing; false to resume.",
                },
            },
            "required": ["project_id", "processing_paused"],
            "additionalProperties": False,
        }

    def validate_params(
        self: "SetProjectProcessingPausedMCPCommand", params: Dict[str, Any]
    ) -> Dict[str, Any]:
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    async def execute(
        self: "SetProjectProcessingPausedMCPCommand",
        project_id: str,
        processing_paused: bool,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Write ``processing_paused`` to projectid, sync DB, return the new value."""
        try:
            database = self._open_database_from_config(auto_analyze=False)
            try:
                project = database.get_project(project_id)
                if not project:
                    return self._handle_error(
                        ValidationError(
                            "Project not found",
                            field="project_id",
                            details={"project_id": project_id},
                        ),
                        "PROJECT_NOT_FOUND",
                        self.name,
                    )
                from ...core.project_root_path import resolve_project_root_absolute_str
                from ...core.project_resolution import update_projectid_fields

                stored_root = (
                    project.get("root_path")
                    if isinstance(project, dict)
                    else getattr(project, "root_path", None)
                )
                watch_dir_id = (
                    project.get("watch_dir_id")
                    if isinstance(project, dict)
                    else getattr(project, "watch_dir_id", None)
                )
                project_name = (
                    project.get("name")
                    if isinstance(project, dict)
                    else getattr(project, "name", None)
                )
                resolved_root = resolve_project_root_absolute_str(
                    project_id=project_id,
                    root_path_stored=str(stored_root or ""),
                    watch_dir_id=(
                        str(watch_dir_id) if watch_dir_id is not None else None
                    ),
                    project_name=str(project_name or "").strip() or None,
                    database=database,
                    require_exists=True,
                )
                if not resolved_root:
                    return self._handle_error(
                        ValidationError(
                            "Cannot resolve project root for projectid update",
                            field="project_id",
                            details={"project_id": project_id},
                        ),
                        "PROJECT_ROOT_NOT_FOUND",
                        self.name,
                    )
                update_projectid_fields(
                    resolved_root, processing_paused=bool(processing_paused)
                )
                if hasattr(database, "sync_project_metadata_from_projectid"):
                    database.sync_project_metadata_from_projectid(resolved_root)
                else:
                    database.execute(
                        """
                        UPDATE projects
                        SET processing_paused = ?
                        WHERE id = ?
                        """,
                        (bool(processing_paused), project_id),
                    )
                rows = database.select("projects", where={"id": project_id}, limit=1)
                if not rows:
                    return self._handle_error(
                        ValidationError(
                            "Project not found after update",
                            field="project_id",
                            details={"project_id": project_id},
                        ),
                        "PROJECT_NOT_FOUND",
                        self.name,
                    )
                row = rows[0]
                stored = row.get("processing_paused")
                paused_bool = bool(stored) if stored is not None else False
                return SuccessResult(
                    data={
                        "project_id": project_id,
                        "processing_paused": paused_bool,
                    },
                    message=(
                        "Background processing paused for project"
                        if paused_bool
                        else "Background processing resumed for project"
                    ),
                )
            finally:
                database.disconnect()
        except Exception as e:
            return self._handle_error(e, "SET_PROCESSING_PAUSED_ERROR", self.name)

    @classmethod
    def metadata(cls: type["SetProjectProcessingPausedMCPCommand"]) -> Dict[str, Any]:
        """Metadata for AI / help."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "Writes ``processing_paused`` to the project's ``projectid`` file "
                "(source of truth), then syncs the ``projects`` row. "
                "When true, the indexing worker does not pick up files for that project "
                "and the vectorization worker excludes it from pending work and FAISS rebuild. "
                "Does not stop the file watcher or other commands."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID.",
                    "type": "string",
                    "required": True,
                },
                "processing_paused": {
                    "description": "True to pause, false to resume.",
                    "type": "boolean",
                    "required": True,
                },
            },
            "usage_examples": [
                {
                    "description": "Pause background processing",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "processing_paused": True,
                    },
                },
                {
                    "description": "Resume",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "processing_paused": False,
                    },
                },
            ],
        }
