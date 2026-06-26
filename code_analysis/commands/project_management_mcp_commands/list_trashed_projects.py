"""
MCP command: list_trashed_projects.

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
    logger,
)


class ListTrashedProjectsMCPCommand(BaseMCPCommand):
    """
    List projects that have been moved to trash (recycle bin).

    Returns folders in trash_dir with parsed original_name and deleted_at.
    """

    name = "list_trashed_projects"
    version = "1.0.0"
    descr = "List projects in trash (recycle bin) with folder name, original name, and deletion time"
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["ListTrashedProjectsMCPCommand"]) -> Dict[str, Any]:
        """Return the schema for an optional trash-directory override."""
        return {
            "type": "object",
            "description": "List projects in trash (recycle bin)",
            "properties": {
                "trash_dir": {
                    "type": "string",
                    "description": (
                        "Optional path to trash directory. "
                        "If omitted, uses trash_dir from server config (StoragePaths)."
                    ),
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def validate_params(
        self: "ListTrashedProjectsMCPCommand", params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate params against schema."""
        return super().validate_params(params)

    async def execute(
        self: "ListTrashedProjectsMCPCommand",
        trash_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """List and parse project entries in the configured trash directory."""
        params: Dict[str, Any] = {"trash_dir": trash_dir}
        params.update(kwargs)
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            return self._handle_error(e, "VALIDATION_ERROR", "list_trashed_projects")
        try:
            from ...core.storage_paths import load_raw_config, resolve_storage_paths

            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            trash_dir_effective = params.get("trash_dir")
            if not trash_dir_effective:
                trash_dir_effective = str(storage.trash_dir)
            from ..trash_commands import ListTrashedProjectsCommand

            cmd = ListTrashedProjectsCommand(trash_dir=trash_dir_effective)
            result = cmd.execute()
            if not result.get("success"):
                return self._handle_error(
                    Exception(result.get("message", "List trash failed")),
                    result.get("error", "LIST_TRASH_ERROR"),
                    "list_trashed_projects",
                )
            return SuccessResult(
                data=result,
                message=f"Found {result.get('count', 0)} item(s) in trash",
            )
        except Exception as e:
            return self._handle_error(
                e, "LIST_TRASHED_PROJECTS_ERROR", "list_trashed_projects"
            )
