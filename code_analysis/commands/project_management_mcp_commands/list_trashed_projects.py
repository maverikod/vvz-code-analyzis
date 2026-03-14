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

    async def execute(
        self: "ListTrashedProjectsMCPCommand",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        try:
            from ...core.storage_paths import load_raw_config, resolve_storage_paths

            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            trash_dir = kwargs.get("trash_dir")
            if not trash_dir:
                trash_dir = str(storage.trash_dir)
            from ..trash_commands import ListTrashedProjectsCommand

            cmd = ListTrashedProjectsCommand(trash_dir=trash_dir)
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
