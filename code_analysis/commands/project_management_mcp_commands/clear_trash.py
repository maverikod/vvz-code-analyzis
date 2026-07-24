"""
MCP command: clear_trash.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ...core.sql_portable import WHERE_PROJECTS_TRASHED
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
    """Return project ids with projects soft-deleted (trashed in DB)."""
    result = database.execute(
        "SELECT id FROM projects WHERE " + WHERE_PROJECTS_TRASHED, ()
    )
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
        """Return the schema for dry-run and trash-directory overrides."""
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
        """Clear trashed project data from the database, FAISS, and disk."""
        try:
            from ...core.storage_paths import (
                load_raw_config,
                resolve_storage_paths,
                get_faiss_index_path,
            )
            from ...core.project_exclusive_lock import is_project_exclusively_locked
            from ...core.trash_utils import (
                merge_project_ids_for_clear_trash_db_phase,
                resolve_trash_entry_project_id,
            )
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

            # bug 88f06abc gap: clear_trash discovers project_ids internally
            # (trash-folder projectid markers + DB soft-delete rows) rather than
            # taking project_id as a kwarg, so run()'s literal-project_id gate
            # never sees them. Skip any exclusively-locked project on BOTH the
            # DB-clear phase and the disk-clear phase below instead of failing
            # (or worse, silently mutating) the whole batch.
            locked_project_ids: List[str] = []

            # Clear DB (and FAISS) for resolvable trash + DB-only soft-delete orphans,
            # then delete paths on disk (DB always before disk for any trash on disk).
            database = self._open_database_from_config(auto_analyze=False)
            try:
                soft_deleted = _soft_deleted_project_ids(database)
                project_ids = merge_project_ids_for_clear_trash_db_phase(
                    trash_dir_path, soft_deleted
                )
                for project_id in project_ids:
                    if is_project_exclusively_locked(database, project_id):
                        locked_project_ids.append(project_id)
                if not dry_run:
                    for project_id in project_ids:
                        if project_id in locked_project_ids:
                            continue
                        await _clear_project_data_impl(database, project_id)
                        faiss_index_path = get_faiss_index_path(
                            storage.faiss_dir, project_id
                        )
                        if faiss_index_path.exists():
                            faiss_index_path.unlink()
            finally:
                database.disconnect()

            # Resolve locked project_ids back to their on-disk trash folder names
            # so ClearTrashCommand's file-system pass below skips them too.
            excluded_folder_names: List[str] = []
            if (
                locked_project_ids
                and trash_dir_path.exists()
                and trash_dir_path.is_dir()
            ):
                locked_set = set(locked_project_ids)
                for child in trash_dir_path.iterdir():
                    if not child.is_dir():
                        continue
                    pid = resolve_trash_entry_project_id(trash_dir_path, child.name)
                    if pid in locked_set:
                        excluded_folder_names.append(child.name)

            cmd = ClearTrashCommand(
                trash_dir=trash_dir,
                dry_run=dry_run,
                exclude_names=excluded_folder_names,
            )
            result = cmd.execute()
            if not result.get("success"):
                return self._handle_error(
                    Exception(result.get("message", "Clear trash failed")),
                    result.get("error", "CLEAR_TRASH_ERROR"),
                    "clear_trash",
                )
            result["skipped_locked_project_ids"] = locked_project_ids
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
