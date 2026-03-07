"""
MCP command: permanently_delete_from_trash.

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
    _get_socket_path_from_db_path,
    logger,
)


class PermanentlyDeleteFromTrashMCPCommand(BaseMCPCommand):
    """
    Permanently delete one project folder from trash.

    Removes the folder from trash_dir; cannot be undone.
    """

    name = "permanently_delete_from_trash"
    version = "1.0.0"
    descr = "Permanently delete one project folder from trash (recycle bin)"
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["PermanentlyDeleteFromTrashMCPCommand"]) -> Dict[str, Any]:
        return {
            "type": "object",
            "description": "Permanently delete one folder from trash",
            "properties": {
                "trash_folder_name": {
                    "type": "string",
                    "description": (
                        "Name of the trashed folder to delete (e.g. MyProject_2025-01-29T14-30-00Z). "
                        "Must be a direct child of trash_dir; no path separators or '..' allowed."
                    ),
                },
                "trash_dir": {
                    "type": "string",
                    "description": (
                        "Optional path to trash directory. "
                        "If omitted, uses trash_dir from server config."
                    ),
                },
            },
            "required": ["trash_folder_name"],
            "additionalProperties": False,
        }

    async def execute(
        self: "PermanentlyDeleteFromTrashMCPCommand",
        trash_folder_name: str,
        trash_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        try:
            from ..core.storage_paths import (
                load_raw_config,
                resolve_storage_paths,
                get_faiss_index_path,
            )
            from ..core.trash_utils import get_project_id_from_trash_folder
            from .clear_project_data_impl import _clear_project_data_impl
            from .trash_commands import PermanentlyDeleteFromTrashCommand

            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            if not trash_dir:
                trash_dir = str(storage.trash_dir)
            trash_dir_path = Path(trash_dir)

            # 1. Clear project from DB in one batch (then delete folder)
            project_id = get_project_id_from_trash_folder(
                trash_dir_path, trash_folder_name
            )
            if project_id:
                socket_path = _get_socket_path_from_db_path(Path(storage.db_path))
                from ..core.database_client.client import DatabaseClient

                database = DatabaseClient(socket_path=socket_path)
                database.connect()
                try:
                    await _clear_project_data_impl(database, project_id)
                    faiss_index_path = get_faiss_index_path(
                        storage.faiss_dir, project_id
                    )
                    if faiss_index_path.exists():
                        faiss_index_path.unlink()
                        logger.info(
                            "Deleted FAISS index for project %s from trash",
                            project_id,
                        )
                finally:
                    database.disconnect()

            # 2. Permanently delete folder from trash
            cmd = PermanentlyDeleteFromTrashCommand(
                trash_dir=trash_dir,
                trash_folder_name=trash_folder_name,
            )
            result = cmd.execute()
            if not result.get("success"):
                return self._handle_error(
                    Exception(result.get("message", "Permanent delete failed")),
                    result.get("error", "PERMANENT_DELETE_ERROR"),
                    "permanently_delete_from_trash",
                )
            return SuccessResult(
                data=result,
                message=result.get("message", "Permanently deleted from trash"),
            )
        except Exception as e:
            return self._handle_error(
                e,
                "PERMANENTLY_DELETE_FROM_TRASH_ERROR",
                "permanently_delete_from_trash",
            )
