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
    List,
    Optional,
    Path,
    SuccessResult,
    logger,
)


def _soft_deleted_project_ids(database: Any) -> List[str]:
    """Return project ids with projects.deleted = 1 (soft-deleted / trashed in DB)."""
    result = database.execute("SELECT id FROM projects WHERE deleted = 1", ())
    rows = result.get("data") or []
    out: List[str] = []
    for row in rows:
        rid = row.get("id")
        if rid is not None:
            out.append(str(rid))
    return out


class ClearTrashMCPCommand(BaseMCPCommand):
    """
    Permanently delete all contents of the trash directory.

    Clears database and FAISS data for projects found in trash (resolvable ids), then
    removes trash contents on disk. Also removes **DB-only orphan** soft-deleted
    projects (marked deleted in the database but with no corresponding resolvable
    trash folder), so DB and disk stay consistent.

    Optionally dry_run to only report what would be removed (no DB or disk changes).
    """

    name = "clear_trash"
    version = "1.0.0"
    descr = (
        "Empty trash on disk and clear DB/FAISS for trashed projects; also clears "
        "soft-deleted projects missing from trash (orphan DB rows). Optional dry_run."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True  # Long-running (clear many projects); run via queue

    @classmethod
    def get_schema(cls: type["ClearTrashMCPCommand"]) -> Dict[str, Any]:
        return {
            "type": "object",
            "description": (
                "Clear all contents of trash (recycle bin). Also clears database rows "
                "for soft-deleted projects that no longer have a folder in trash."
            ),
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
            from ...core.trash_utils import merge_project_ids_for_clear_trash_db_phase
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

            # Clear DB (and FAISS) for resolvable trash + DB-only soft-delete orphans,
            # then delete paths on disk (DB always before disk for any trash on disk).
            if not dry_run:
                database = self._open_database_from_config(auto_analyze=False)
                try:
                    soft_deleted = _soft_deleted_project_ids(database)
                    project_ids = merge_project_ids_for_clear_trash_db_phase(
                        trash_dir_path, soft_deleted
                    )
                    if project_ids:
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
