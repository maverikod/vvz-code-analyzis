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

from ..core.trash_utils import (
    build_trash_folder_name,
    ensure_unique_trash_path,
)

from .clear_project_data_impl import _clear_project_data_impl

if TYPE_CHECKING:
    from ..core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


class DeleteProjectCommand:
    """
    Command to delete a project and all its data.

    This command completely removes a project from the database:
    - All files and their associated data (classes, functions, methods, etc.)
    - All chunks and vector indexes
    - All duplicates
    - All datasets
    - The project record itself

    Optionally can also "delete from disk": when delete_from_disk=True, the project
    root directory is moved to trash (recycle bin) instead of being permanently
    removed. Version directory for this project is permanently deleted.

    Use with caution - database removal cannot be undone.
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
            delete_from_disk: If True, move project root to trash and delete version dir
            version_dir: Version directory path (if None, will try to get from config)
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

    async def execute(self) -> Dict[str, Any]:
        """
        Execute project deletion.

        Returns:
            Dictionary with deletion results
        """
        # Get project info before deletion
        project = self.database.get_project(self.project_id)
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

        # Count datasets - use select to get datasets
        datasets = self.database.select(
            "datasets", where={"project_id": self.project_id}
        )
        dataset_count = len(datasets)

        # Get version directory if needed
        version_dir_path = None
        if self.delete_from_disk:
            if self.version_dir:
                version_dir_path = Path(self.version_dir).resolve()
            else:
                # Try to get from database config or use default
                # Default: data/versions relative to database location
                db_path = getattr(self.database, "_db_path", None)
                if db_path:
                    db_path_obj = Path(db_path)
                    if db_path_obj.parent.name == "data":
                        version_dir_path = db_path_obj.parent / "versions"
                    else:
                        version_dir_path = db_path_obj.parent / "data" / "versions"
                else:
                    # Fallback to default
                    version_dir_path = Path("data/versions").resolve()

        # Resolve trash_dir if delete_from_disk (from param or config per plan)
        trash_dir_path = None
        if self.delete_from_disk:
            if self.trash_dir:
                trash_dir_path = Path(self.trash_dir).resolve()
            elif self.config_path and Path(self.config_path).exists():
                try:
                    from ..core.storage_paths import (
                        load_raw_config,
                        resolve_storage_paths,
                    )

                    config_data = load_raw_config(Path(self.config_path))
                    storage = resolve_storage_paths(
                        config_data=config_data,
                        config_path=Path(self.config_path),
                    )
                    trash_dir_path = storage.trash_dir
                except Exception as e:
                    logger.warning("Could not resolve trash_dir from config: %s", e)

        if self.dry_run:
            result = {
                "success": True,
                "dry_run": True,
                "project_id": self.project_id,
                "project_name": project_name,
                "root_path": root_path,
                "files_count": file_count,
                "chunks_count": chunk_count,
                "datasets_count": dataset_count,
                "delete_from_disk": self.delete_from_disk,
                "message": f"Would delete project {project_name} ({self.project_id})",
            }
            if self.delete_from_disk:
                result["version_dir"] = (
                    str(version_dir_path) if version_dir_path else None
                )
                result["trash_dir"] = str(trash_dir_path) if trash_dir_path else None
                root_path_obj = Path(root_path)
                result["would_move_to_trash"] = root_path_obj.exists()
                if version_dir_path:
                    project_version_dir = version_dir_path / self.project_id
                    result["would_delete_version_dir"] = project_version_dir.exists()
            return result

        # Perform deletion: first DB, then move to trash (if delete_from_disk)
        deletion_start_time = time.time()
        logger.info(f"[DELETE_PROJECT] Starting deletion of project {self.project_id}")

        try:
            disk_deletion_errors = []

            # 1. Delete from database first (while project dir still exists)
            db_start = time.time()
            logger.info(
                f"[DELETE_PROJECT] Starting database deletion for {self.project_id}"
            )
            await _clear_project_data_impl(self.database, self.project_id)
            logger.info(
                f"[DELETE_PROJECT] Completed database deletion in {time.time() - db_start:.3f}s. "
                f"Deleted project {self.project_id} ({project_name}) from database: "
                f"{file_count} files, {chunk_count} chunks, {dataset_count} datasets"
            )

            # 2. If delete_from_disk: move project root to trash, then delete version dir
            if self.delete_from_disk and trash_dir_path:
                root_path_obj = Path(root_path)
                if root_path_obj.exists():
                    try:
                        trash_dir_path.mkdir(parents=True, exist_ok=True)
                        deleted_at_utc = datetime.now(timezone.utc)
                        trash_folder_name = build_trash_folder_name(
                            project_name, self.project_id, deleted_at_utc
                        )
                        dest = ensure_unique_trash_path(
                            trash_dir_path, trash_folder_name
                        )
                        shutil.move(str(root_path_obj), str(dest))
                        logger.info(
                            f"Moved project root to trash: {root_path_obj} -> {dest}"
                        )
                    except Exception as e:
                        error_msg = (
                            f"Failed to move project root to trash {root_path_obj}: {e}"
                        )
                        logger.error(error_msg, exc_info=True)
                        disk_deletion_errors.append(error_msg)

                # Delete version directory for this project (permanent)
                if version_dir_path:
                    project_version_dir = version_dir_path / self.project_id
                    if project_version_dir.exists():
                        try:
                            shutil.rmtree(project_version_dir)
                            logger.info(
                                f"Deleted version directory for project {self.project_id}: {project_version_dir}"
                            )
                        except Exception as e:
                            error_msg = f"Failed to delete version directory {project_version_dir}: {e}"
                            logger.error(error_msg, exc_info=True)
                            disk_deletion_errors.append(error_msg)

            result = {
                "success": True,
                "dry_run": False,
                "project_id": self.project_id,
                "project_name": project_name,
                "root_path": root_path,
                "files_count": file_count,
                "chunks_count": chunk_count,
                "datasets_count": dataset_count,
                "delete_from_disk": self.delete_from_disk,
                "message": f"Deleted project {project_name} ({self.project_id})",
            }

            total_time = time.time() - deletion_start_time
            logger.info(
                f"[DELETE_PROJECT] Total deletion time for {self.project_id}: {total_time:.3f}s"
            )
            result["deletion_time_seconds"] = total_time

            if self.delete_from_disk:
                result["version_dir"] = (
                    str(version_dir_path) if version_dir_path else None
                )
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
