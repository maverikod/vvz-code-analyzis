"""
MCP command: restore_project_from_trash.

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
    ValidationError,
    logger,
)


class RestoreProjectFromTrashMCPCommand(BaseMCPCommand):
    """
    Restore a project from trash (recycle bin).

    Moves the folder from trash back to its original root_path, then unmarks
    the project and its files in the database in one batch.
    """

    name = "restore_project_from_trash"
    version = "1.0.0"
    descr = (
        "Restore a project from trash: move folder back, then unmark in DB (one batch)"
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["RestoreProjectFromTrashMCPCommand"],
    ) -> Dict[str, Any]:
        return {
            "type": "object",
            "description": "Restore a project from trash (move files then unmark in DB)",
            "properties": {
                "trash_folder_name": {
                    "type": "string",
                    "description": (
                        "Name of the trashed folder to restore (e.g. MyProject_2025-01-29T14-30-00Z). "
                        "Must be a direct child of trash_dir."
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
        self: "RestoreProjectFromTrashMCPCommand",
        trash_folder_name: str,
        trash_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        try:
            import shutil

            from ...core.storage_paths import load_raw_config, resolve_storage_paths
            from ...core.trash_utils import get_project_id_from_trash_folder
            from ..clear_project_data_impl import unmark_project_deleted_impl

            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            if not trash_dir:
                trash_dir = str(storage.trash_dir)
            trash_dir_path = Path(trash_dir)
            source = trash_dir_path / trash_folder_name

            if not source.exists() or not source.is_dir():
                return self._handle_error(
                    ValidationError(
                        f"Trashed folder not found or not a directory: {source}",
                        field="trash_folder_name",
                        details={"trash_folder_name": trash_folder_name},
                    ),
                    "NOT_FOUND",
                    "restore_project_from_trash",
                )

            project_id = get_project_id_from_trash_folder(
                trash_dir_path, trash_folder_name
            )
            if not project_id:
                return self._handle_error(
                    ValidationError(
                        "No projectid file in trashed folder; cannot resolve project_id",
                        field="trash_folder_name",
                        details={"trash_folder_name": trash_folder_name},
                    ),
                    "NO_PROJECT_ID",
                    "restore_project_from_trash",
                )

            database = self._open_database_from_config(auto_analyze=False)
            try:
                rows = database.select(
                    "projects",
                    where={"id": project_id},
                    columns=["id", "root_path", "name"],
                )
                if not rows:
                    return self._handle_error(
                        ValidationError(
                            f"Project {project_id} not found in database",
                            field="trash_folder_name",
                            details={"project_id": project_id},
                        ),
                        "PROJECT_NOT_FOUND",
                        "restore_project_from_trash",
                    )
                row = rows[0]
                # Trashed state is determined by files table only: all files must be deleted
                active_result = database.execute(
                    "SELECT COUNT(*) as active FROM files WHERE project_id = ? "
                    "AND (deleted = 0 OR deleted IS NULL)",
                    (project_id,),
                )
                data = (
                    active_result.get("data", [])
                    if isinstance(active_result, dict)
                    else []
                )
                active = (
                    data[0].get("active", 0) or 0
                    if isinstance(data, list) and data
                    else 0
                )
                if active > 0:
                    return self._handle_error(
                        ValidationError(
                            f"Project {project_id} has non-deleted files (not in trash)",
                            field="trash_folder_name",
                            details={"project_id": project_id},
                        ),
                        "NOT_IN_TRASH",
                        "restore_project_from_trash",
                    )
                root_path = Path(row["root_path"])
                if root_path.exists():
                    return self._handle_error(
                        ValidationError(
                            f"Cannot restore: target path already exists: {root_path}",
                            field="trash_folder_name",
                            details={"root_path": str(root_path)},
                        ),
                        "TARGET_EXISTS",
                        "restore_project_from_trash",
                    )

                # 1. Move folder from trash to original root_path
                shutil.move(str(source), str(root_path))
                logger.info(
                    "Restored project from trash: %s -> %s",
                    source,
                    root_path,
                )

                # 2. Unmark project and files in one batch
                await unmark_project_deleted_impl(database, project_id)
            finally:
                database.disconnect()

            return SuccessResult(
                data={
                    "project_id": project_id,
                    "root_path": str(root_path),
                    "trash_folder_name": trash_folder_name,
                },
                message=f"Restored project {project_id} to {root_path}",
            )
        except Exception as e:
            return self._handle_error(
                e,
                "RESTORE_PROJECT_FROM_TRASH_ERROR",
                "restore_project_from_trash",
            )
