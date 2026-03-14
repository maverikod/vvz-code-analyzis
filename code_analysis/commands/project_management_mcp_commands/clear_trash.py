"""
MCP command: clear_trash.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ._shared import (
    Any,
    BaseMCPCommand,
    Dict,
    ErrorResult,
    Optional,
    Path,
    SuccessResult,
    logger,
)


class ClearTrashMCPCommand(BaseMCPCommand):
    """
    Permanently delete all contents of the trash directory.

    Optionally dry_run to only report what would be removed.
    """

    name = "clear_trash"
    version = "1.0.0"
    descr = "Permanently delete all projects from trash (recycle bin); optional dry_run"
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True  # Long-running (clear many projects); run via queue

    @classmethod
    def get_schema(cls: type["ClearTrashMCPCommand"]) -> Dict[str, Any]:
        return {
            "type": "object",
            "description": "Clear all contents of trash (recycle bin)",
            "properties": {
                "dry_run": {
                    "type": "boolean",
                    "description": (
                        "If True, only list what would be removed without deleting. "
                        "Default: False."
                    ),
                    "default": False,
                },
                "trash_dir": {
                    "type": "string",
                    "description": (
                        "Optional path to trash directory. "
                        "If omitted, uses trash_dir from server config."
                    ),
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self: "ClearTrashMCPCommand",
        dry_run: bool = False,
        trash_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        try:
            from ...core.storage_paths import (
                load_raw_config,
                resolve_storage_paths,
                get_faiss_index_path,
            )
            from ...core.trash_utils import get_project_id_from_trash_folder
            from ..clear_project_data_impl import _clear_project_data_impl
            from ..trash_commands import ClearTrashCommand

            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            if not trash_dir:
                trash_dir = str(storage.trash_dir)
            trash_dir_path = Path(trash_dir)

            # Clear DB (and FAISS) for each trashed project before deleting folders
            if not dry_run and trash_dir_path.exists():
                project_ids = []
                for child in trash_dir_path.iterdir():
                    if child.is_dir():
                        pid = get_project_id_from_trash_folder(
                            trash_dir_path, child.name
                        )
                        if pid:
                            project_ids.append(pid)
                if project_ids:
                    database = self._open_database_from_config(auto_analyze=False)
                    try:
                        for project_id in project_ids:
                            await _clear_project_data_impl(database, project_id)
                            faiss_index_path = get_faiss_index_path(
                                storage.faiss_dir, project_id
                            )
                            if faiss_index_path.exists():
                                faiss_index_path.unlink()
                    finally:
                        database.disconnect()

            cmd = ClearTrashCommand(trash_dir=trash_dir, dry_run=dry_run)
            result = cmd.execute()
            if not result.get("success"):
                return self._handle_error(
                    Exception(result.get("message", "Clear trash failed")),
                    result.get("error", "CLEAR_TRASH_ERROR"),
                    "clear_trash",
                )
            return SuccessResult(
                data=result,
                message=(
                    f"Would remove {result.get('removed_count', 0)} item(s)"
                    if dry_run
                    else f"Removed {result.get('removed_count', 0)} item(s) from trash"
                ),
            )
        except Exception as e:
            return self._handle_error(e, "CLEAR_TRASH_ERROR", "clear_trash")
