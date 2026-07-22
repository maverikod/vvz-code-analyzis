"""
Internal commands for project deletion.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..core.database_driver_pkg.domain.projects import get_project
from ..core.trash_utils import (
    build_trash_folder_name,
    ensure_unique_trash_path,
)

from .clear_project_data_impl import (
    _clear_project_data_impl,
    mark_project_deleted_impl,
)

if TYPE_CHECKING:
    from ..core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


class DeleteProjectCommand:
    """
    Delete or soft-delete a project.

    **Soft delete** (``delete_from_disk=True``): marks the project and files in the
    database (including empty projects via ``projects.deleted``), moves the project
    root into ``trash_dir``, and removes the per-project version directory. Database
    rows remain until ``permanently_delete_from_trash`` / ``clear_trash``.

    **Full / permanent delete** (``delete_from_disk=False``): runs the same soft-delete
    stage first (DB markers + move to trash + version dir removal), then clears all
    project data from the database and removes the FAISS index file.

    File-level trash uses ``trash_dir/{project_id}/...`` for individual deleted files.
    """

    def __init__(
        self,
        database: DatabaseClient,
        project_id: str,
        dry_run: bool = False,
        delete_from_disk: bool = False,
        version_dir: Optional[str] = None,
        trash_dir: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        """
        Initialize delete project command.

        Args:
            database: DatabaseClient instance
            project_id: Project ID to delete
            dry_run: If True, only show what would be deleted
            delete_from_disk: If True, soft-delete only (DB rows kept). If False, soft-delete
                then full clear from DB and FAISS index file.
            version_dir: Version directory path (if None, inferred from DB path or defaults)
            trash_dir: Trash directory path (if None, will try to get from config when config_path set)
            config_path: Optional path to config.json to resolve trash_dir when trash_dir is None
        """
        self.database = database
        self.project_id = project_id
        self.dry_run = dry_run
        self.delete_from_disk = delete_from_disk
        self.version_dir = version_dir
        self.trash_dir = trash_dir
        self.config_path = config_path

    async def _soft_delete_project_stage(
        self,
        project_name: str,
        root_path: str,
        trash_dir_path: Optional[Path],
        version_dir_path: Optional[Path],
    ) -> list[str]:
        """
        Mark project/files soft-deleted in DB, move project root to trash, delete
        version directory. Returns disk error messages (non-fatal).
        """
        await mark_project_deleted_impl(self.database, self.project_id)
        disk_deletion_errors: list[str] = []

        if trash_dir_path:
            root_path_obj = Path(root_path)
            if root_path_obj.exists():
                try:
                    trash_dir_path.mkdir(parents=True, exist_ok=True)
                    deleted_at_utc = datetime.now(timezone.utc)
                    trash_folder_name = build_trash_folder_name(
                        project_name, self.project_id, deleted_at_utc
                    )
                    dest = ensure_unique_trash_path(trash_dir_path, trash_folder_name)
                    shutil.move(str(root_path_obj), str(dest))
                    logger.info(
                        "Moved project root to trash: %s -> %s",
                        root_path_obj,
                        dest,
                    )
                except Exception as e:
                    error_msg = (
                        f"Failed to move project root to trash {root_path_obj}: {e}"
                    )
                    logger.error(error_msg, exc_info=True)
                    disk_deletion_errors.append(error_msg)

        if version_dir_path:
            project_version_dir = version_dir_path / self.project_id
            if project_version_dir.exists():
                try:
                    shutil.rmtree(project_version_dir)
                    logger.info(
                        "Deleted version directory for project %s: %s",
                        self.project_id,
                        project_version_dir,
                    )
                except Exception as e:
                    error_msg = (
                        f"Failed to delete version directory {project_version_dir}: {e}"
                    )
                    logger.error(error_msg, exc_info=True)
                    disk_deletion_errors.append(error_msg)

        return disk_deletion_errors

    async def execute(self) -> Dict[str, Any]:
        """
        Execute project deletion.

        Returns:
            Dictionary with deletion results
        """
        # Get project info before deletion
        project = get_project(self.database, self.project_id)
        if not project:
            return {
                "success": False,
                "error": "PROJECT_NOT_FOUND",
                "message": f"Project {self.project_id} not found",
            }

        project_name = project.name or "Unknown"
        root_path = project.root_path or "Unknown"

        # Get statistics before deletion
        files = self.database.get_project_files(self.project_id, include_deleted=True)
        file_count = len(files)

        # Count chunks
        result = self.database.execute(
            """
            SELECT COUNT(*) as count 
            FROM code_chunks cc
            JOIN files f ON cc.file_id = f.id
            WHERE f.project_id = ?
            """,
            (self.project_id,),
        )
        # Handle different result formats
        if isinstance(result, list):
            data = result
        elif isinstance(result, dict):
            data = result.get("data", [])
        else:
            data = []
        chunk_count = data[0]["count"] if data and len(data) > 0 else 0

        # Version / trash paths (soft-delete stage uses these for both modes).
        version_dir_path: Optional[Path] = None
        if self.version_dir:
            version_dir_path = Path(self.version_dir).resolve()
        else:
            db_path = getattr(self.database, "_db_path", None)
            if db_path:
                db_path_obj = Path(db_path)
                if db_path_obj.parent.name == "data":
                    version_dir_path = db_path_obj.parent / "versions"
                else:
                    version_dir_path = db_path_obj.parent / "data" / "versions"
            else:
                version_dir_path = Path("data/versions").resolve()

        trash_dir_path: Optional[Path] = None
        if self.trash_dir:
            trash_dir_path = Path(self.trash_dir).resolve()
        elif self.config_path and Path(self.config_path).exists():
            try:
                from ..core.storage_paths import load_raw_config, resolve_storage_paths

                config_data = load_raw_config(Path(self.config_path))
                storage = resolve_storage_paths(
                    config_data=config_data,
                    config_path=Path(self.config_path),
                )
                trash_dir_path = storage.trash_dir
            except Exception as e:
                logger.warning("Could not resolve trash_dir from config: %s", e)

        if self.dry_run:
            # ``delete_from_disk`` naming follows MCP: True = trash-only (keep DB rows);
            # False (default) = trash then full DB + FAISS clear. Legacy keys would_soft_delete /
            # would_permanent_db_clear refer to *phases*, not plain English "soft vs hard".
            keep_db = bool(self.delete_from_disk)
            clear_db_after = not keep_db
            result = {
                "success": True,
                "dry_run": True,
                "project_id": self.project_id,
                "project_name": project_name,
                "root_path": root_path,
                "files_count": file_count,
                "chunks_count": chunk_count,
                "delete_from_disk": self.delete_from_disk,
                "keep_database_rows_after_operation": keep_db,
                "would_clear_database_and_faiss_after_trash": clear_db_after,
                "would_run_soft_delete_to_trash_phase": True,
                "planned_steps": [
                    "Mark project and files soft-deleted in DB; move project root under "
                    "trash_dir (if configured); remove per-project folder under version_dir",
                ]
                + (
                    [
                        "Then: delete all project rows from the database and remove this "
                        "project's FAISS index file (sources remain under trash until "
                        "clear_trash / permanently_delete_from_trash)",
                    ]
                    if clear_db_after
                    else [
                        "Then: keep all database rows for recovery until clear_trash / "
                        "permanently_delete_from_trash",
                    ]
                ),
                "parameter_note": (
                    "delete_from_disk=True means soft-delete to trash only (DB kept). "
                    "delete_from_disk=False (default) means the same trash step, then "
                    "permanent removal of project data from the database and FAISS file."
                ),
                # Legacy aliases (same semantics as before this clarification):
                "would_soft_delete": True,
                "would_permanent_db_clear": clear_db_after,
                "message": (
                    f"Would soft-delete project {project_name} ({self.project_id})"
                    + (
                        ", then remove all data from the database"
                        if clear_db_after
                        else " (soft-delete only; database rows kept)"
                    )
                ),
            }
            result["version_dir"] = str(version_dir_path) if version_dir_path else None
            result["trash_dir"] = str(trash_dir_path) if trash_dir_path else None
            root_path_obj = Path(root_path)
            result["would_move_to_trash"] = bool(
                trash_dir_path and root_path_obj.exists()
            )
            if version_dir_path:
                project_version_dir = version_dir_path / self.project_id
                result["would_delete_version_dir"] = project_version_dir.exists()
            return result

        deletion_start_time = time.time()
        logger.info(f"[DELETE_PROJECT] Starting deletion of project {self.project_id}")

        try:
            logger.info(
                "[DELETE_PROJECT] Soft-delete stage for %s (delete_from_disk=%s)",
                self.project_id,
                self.delete_from_disk,
            )
            disk_deletion_errors = await self._soft_delete_project_stage(
                project_name=project_name,
                root_path=root_path,
                trash_dir_path=trash_dir_path,
                version_dir_path=version_dir_path,
            )

            if not self.delete_from_disk:
                db_start = time.time()
                logger.info(
                    "[DELETE_PROJECT] Permanent DB clear for %s", self.project_id
                )
                await _clear_project_data_impl(self.database, self.project_id)
                logger.info(
                    "[DELETE_PROJECT] Completed database deletion in %.3fs for %s "
                    "(%s files, %s chunks)",
                    time.time() - db_start,
                    self.project_id,
                    file_count,
                    chunk_count,
                )

                try:
                    config_path = Path(self.config_path) if self.config_path else None
                    if not config_path or not config_path.exists():
                        from .base_mcp_command import BaseMCPCommand

                        config_path = BaseMCPCommand._resolve_config_path()
                    if config_path.exists():
                        from ..core.storage_paths import (
                            load_raw_config,
                            resolve_storage_paths,
                            get_faiss_index_path,
                        )

                        config_data = load_raw_config(config_path)
                        storage = resolve_storage_paths(
                            config_data=config_data, config_path=config_path
                        )
                        faiss_index_path = get_faiss_index_path(
                            storage.faiss_dir, self.project_id
                        )
                        if faiss_index_path.exists():
                            faiss_index_path.unlink()
                            logger.info(
                                "[DELETE_PROJECT] Deleted FAISS index %s",
                                faiss_index_path,
                            )
                except Exception as e:
                    logger.warning(
                        "[DELETE_PROJECT] Could not delete FAISS index for %s: %s",
                        self.project_id,
                        e,
                    )

            result = {
                "success": True,
                "dry_run": False,
                "project_id": self.project_id,
                "project_name": project_name,
                "root_path": root_path,
                "files_count": file_count,
                "chunks_count": chunk_count,
                "delete_from_disk": self.delete_from_disk,
                "message": (
                    f"Soft-deleted project {project_name} ({self.project_id})"
                    if self.delete_from_disk
                    else (
                        f"Permanently removed project {project_name} "
                        f"({self.project_id}) from the database"
                    )
                ),
            }

            total_time = time.time() - deletion_start_time
            logger.info(
                "[DELETE_PROJECT] Total deletion time for %s: %.3fs",
                self.project_id,
                total_time,
            )
            result["deletion_time_seconds"] = total_time
            result["version_dir"] = str(version_dir_path) if version_dir_path else None
            result["trash_dir"] = str(trash_dir_path) if trash_dir_path else None
            if disk_deletion_errors:
                result["disk_deletion_errors"] = disk_deletion_errors
                result[
                    "message"
                ] += f" (with {len(disk_deletion_errors)} disk error(s))"

            return result
        except Exception as e:
            logger.error(
                f"Failed to delete project {self.project_id}: {e}", exc_info=True
            )
            return {
                "success": False,
                "error": "DELETION_ERROR",
                "message": f"Failed to delete project: {str(e)}",
                "project_id": self.project_id,
            }
