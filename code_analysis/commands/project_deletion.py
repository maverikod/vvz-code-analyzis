"""
Internal commands for project deletion.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


async def _clear_project_data_impl(database: DatabaseClient, project_id: str) -> None:
    """Clear all data for a project using DatabaseClient atomically.

    This is a helper function that implements clear_project_data for DatabaseClient.
    All operations are performed within a single transaction for atomicity and performance.
    """
    clear_start = time.time()
    logger.info(f"[CLEAR_PROJECT_DATA] Starting clear for project {project_id}")
    
    transaction_id = None
    try:
        # Begin transaction
        tx_start = time.time()
        transaction_id = database.begin_transaction()
        logger.info(f"[CLEAR_PROJECT_DATA] Started transaction {transaction_id} in {time.time() - tx_start:.3f}s")
        
        # Get all file IDs for this project
        step_start = time.time()
        files = database.select("files", where={"project_id": project_id}, columns=["id"])
        file_ids = [f["id"] for f in files]
        logger.info(f"[CLEAR_PROJECT_DATA] Got {len(file_ids)} file IDs in {time.time() - step_start:.3f}s")

        # Delete duplicates first (before files)
        try:
            step_start = time.time()
            # Delete duplicate occurrences first (foreign key constraint)
            database.execute(
                """
                DELETE FROM duplicate_occurrences
                WHERE duplicate_id IN (
                    SELECT id FROM code_duplicates WHERE project_id = ?
                )
                """,
                (project_id,),
                transaction_id=transaction_id,
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted duplicate_occurrences in {time.time() - step_start:.3f}s")
            
            step_start = time.time()
            # Delete duplicate groups
            database.execute(
                "DELETE FROM code_duplicates WHERE project_id = ?", (project_id,), transaction_id=transaction_id
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted code_duplicates in {time.time() - step_start:.3f}s")
        except Exception as e:
            logger.warning(f"Failed to delete duplicates for project {project_id}: {e}")

        if not file_ids:
            # Delete datasets and vector_index even if no files
            step_start = time.time()
            database.execute("DELETE FROM datasets WHERE project_id = ?", (project_id,), transaction_id=transaction_id)
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted datasets in {time.time() - step_start:.3f}s")
            
            step_start = time.time()
            database.execute("DELETE FROM vector_index WHERE project_id = ?", (project_id,), transaction_id=transaction_id)
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted vector_index in {time.time() - step_start:.3f}s")
            
            step_start = time.time()
            database.execute("DELETE FROM projects WHERE id = ?", (project_id,), transaction_id=transaction_id)
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted project record in {time.time() - step_start:.3f}s")
            
            # Commit transaction
            commit_start = time.time()
            database.commit_transaction(transaction_id)
            logger.info(f"[CLEAR_PROJECT_DATA] Committed transaction {transaction_id} in {time.time() - commit_start:.3f}s")
            logger.info(f"[CLEAR_PROJECT_DATA] Completed clear for project {project_id} (no files) in {time.time() - clear_start:.3f}s")
            return

        # Delete data for all files
        if file_ids:
            step_start = time.time()
            placeholders = ",".join("?" * len(file_ids))
            # Get class IDs
            classes = database.execute(
                f"SELECT id FROM classes WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Got class IDs in {time.time() - step_start:.3f}s")
            # Handle different result formats
            if isinstance(classes, list):
                classes_data = classes
            elif isinstance(classes, dict):
                classes_data = classes.get("data", [])
            else:
                classes_data = []
            class_ids = [c["id"] for c in classes_data]

            # Get content IDs for FTS
            step_start = time.time()
            content_rows = database.execute(
                f"SELECT id FROM code_content WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Got content IDs in {time.time() - step_start:.3f}s")
            # Handle different result formats
            if isinstance(content_rows, list):
                content_data = content_rows
            elif isinstance(content_rows, dict):
                content_data = content_rows.get("data", [])
            else:
                content_data = []
            content_ids = [c["id"] for c in content_data]

            # Delete FTS entries in batches
            if content_ids:
                batch_size = 1000
                batch_count = 0
                for i in range(0, len(content_ids), batch_size):
                    batch = content_ids[i : i + batch_size]
                    batch_placeholders = ",".join("?" * len(batch))
                    try:
                        batch_start = time.time()
                        database.execute(
                            f"DELETE FROM code_content_fts WHERE rowid IN ({batch_placeholders})",
                            tuple(batch),
                            transaction_id=transaction_id,
                        )
                        batch_count += 1
                        logger.debug(f"[CLEAR_PROJECT_DATA] Deleted FTS batch {batch_count} ({len(batch)} rows) in {time.time() - batch_start:.3f}s")
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete FTS batch {i//batch_size + 1} for project {project_id}: {e}"
                        )
                        break
                logger.info(f"[CLEAR_PROJECT_DATA] Deleted {batch_count} FTS batches ({len(content_ids)} total rows)")

            # Delete methods
            if class_ids:
                step_start = time.time()
                method_placeholders = ",".join("?" * len(class_ids))
                database.execute(
                    f"DELETE FROM methods WHERE class_id IN ({method_placeholders})",
                    tuple(class_ids),
                    transaction_id=transaction_id,
                )
                logger.info(f"[CLEAR_PROJECT_DATA] Deleted methods in {time.time() - step_start:.3f}s")

            # Delete other file-related data
            step_start = time.time()
            database.execute(
                f"DELETE FROM classes WHERE file_id IN ({placeholders})", tuple(file_ids), transaction_id=transaction_id
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted classes in {time.time() - step_start:.3f}s")
            
            step_start = time.time()
            database.execute(
                f"DELETE FROM functions WHERE file_id IN ({placeholders})", tuple(file_ids), transaction_id=transaction_id
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted functions in {time.time() - step_start:.3f}s")
            
            step_start = time.time()
            database.execute(
                f"DELETE FROM imports WHERE file_id IN ({placeholders})", tuple(file_ids), transaction_id=transaction_id
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted imports in {time.time() - step_start:.3f}s")
            
            step_start = time.time()
            database.execute(
                f"DELETE FROM issues WHERE file_id IN ({placeholders})", tuple(file_ids), transaction_id=transaction_id
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted issues in {time.time() - step_start:.3f}s")
            
            step_start = time.time()
            database.execute(
                f"DELETE FROM code_content WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted code_content in {time.time() - step_start:.3f}s")
            
            step_start = time.time()
            database.execute(
                f"DELETE FROM ast_trees WHERE file_id IN ({placeholders})", tuple(file_ids), transaction_id=transaction_id
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted ast_trees in {time.time() - step_start:.3f}s")
            
            step_start = time.time()
            database.execute(
                f"DELETE FROM cst_trees WHERE file_id IN ({placeholders})", tuple(file_ids), transaction_id=transaction_id
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted cst_trees in {time.time() - step_start:.3f}s")
            
            step_start = time.time()
            database.execute(
                f"DELETE FROM code_chunks WHERE file_id IN ({placeholders})",
                tuple(file_ids),
                transaction_id=transaction_id,
            )
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted code_chunks in {time.time() - step_start:.3f}s")
            
            step_start = time.time()
            database.execute("DELETE FROM files WHERE id IN ({})".format(placeholders), tuple(file_ids), transaction_id=transaction_id)
            logger.info(f"[CLEAR_PROJECT_DATA] Deleted files in {time.time() - step_start:.3f}s")

        # Delete project-level data
        step_start = time.time()
        database.execute("DELETE FROM datasets WHERE project_id = ?", (project_id,), transaction_id=transaction_id)
        logger.info(f"[CLEAR_PROJECT_DATA] Deleted datasets in {time.time() - step_start:.3f}s")
        
        step_start = time.time()
        database.execute("DELETE FROM vector_index WHERE project_id = ?", (project_id,), transaction_id=transaction_id)
        logger.info(f"[CLEAR_PROJECT_DATA] Deleted vector_index in {time.time() - step_start:.3f}s")
        
        step_start = time.time()
        database.execute("DELETE FROM projects WHERE id = ?", (project_id,), transaction_id=transaction_id)
        logger.info(f"[CLEAR_PROJECT_DATA] Deleted project record in {time.time() - step_start:.3f}s")
        
        # Commit transaction
        commit_start = time.time()
        database.commit_transaction(transaction_id)
        logger.info(f"[CLEAR_PROJECT_DATA] Committed transaction {transaction_id} in {time.time() - commit_start:.3f}s")
        logger.info(f"[CLEAR_PROJECT_DATA] Completed clear for project {project_id} in {time.time() - clear_start:.3f}s")
    
    except Exception as e:
        # Rollback transaction on error
        if transaction_id:
            try:
                rollback_start = time.time()
                database.rollback_transaction(transaction_id)
                logger.error(f"[CLEAR_PROJECT_DATA] Rolled back transaction {transaction_id} in {time.time() - rollback_start:.3f}s due to error: {e}")
            except Exception as rollback_error:
                logger.error(f"[CLEAR_PROJECT_DATA] Error during rollback: {rollback_error}")
        raise


class DeleteProjectCommand:
    """
    Command to delete a project and all its data.

    This command completely removes a project from the database:
    - All files and their associated data (classes, functions, methods, etc.)
    - All chunks and vector indexes
    - All duplicates
    - All datasets
    - The project record itself

    Optionally can also delete from disk:
    - Project root directory (if delete_from_disk=True)
    - All files from version directory for this project (if delete_from_disk=True)

    Use with caution - this operation cannot be undone.
    """

    def __init__(
        self,
        database: DatabaseClient,
        project_id: str,
        dry_run: bool = False,
        delete_from_disk: bool = False,
        version_dir: Optional[str] = None,
    ):
        """
        Initialize delete project command.

        Args:
            database: DatabaseClient instance
            project_id: Project ID to delete
            dry_run: If True, only show what would be deleted
            delete_from_disk: If True, also delete project directory and version files from disk
            version_dir: Version directory path (if None, will try to get from config)
        """
        self.database = database
        self.project_id = project_id
        self.dry_run = dry_run
        self.delete_from_disk = delete_from_disk
        self.version_dir = version_dir

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
                root_path_obj = Path(root_path)
                result["would_delete_root_dir"] = root_path_obj.exists()
                if version_dir_path:
                    project_version_dir = version_dir_path / self.project_id
                    result["would_delete_version_dir"] = project_version_dir.exists()
            return result

        # Perform deletion
        deletion_start_time = time.time()
        logger.info(f"[DELETE_PROJECT] Starting deletion of project {self.project_id}")
        
        try:
            disk_deletion_errors = []

            # Delete from disk if requested
            if self.delete_from_disk:
                disk_start = time.time()
                logger.info(f"[DELETE_PROJECT] Starting disk deletion for {self.project_id}")
                # Delete version directory for this project
                if version_dir_path:
                    project_version_dir = version_dir_path / self.project_id
                    if project_version_dir.exists():
                        try:
                            import shutil

                            shutil.rmtree(project_version_dir)
                            logger.info(
                                f"Deleted version directory for project {self.project_id}: {project_version_dir}"
                            )
                        except Exception as e:
                            error_msg = f"Failed to delete version directory {project_version_dir}: {e}"
                            logger.error(error_msg, exc_info=True)
                            disk_deletion_errors.append(error_msg)

                # Delete project root directory
                root_path_obj = Path(root_path)
                if root_path_obj.exists():
                    try:
                        import shutil

                        shutil.rmtree(root_path_obj)
                        logger.info(f"Deleted project root directory: {root_path_obj}")
                    except Exception as e:
                        error_msg = f"Failed to delete project root directory {root_path_obj}: {e}"
                        logger.error(error_msg, exc_info=True)
                        disk_deletion_errors.append(error_msg)

            # Delete from database
            # clear_project_data is not in DatabaseClient API, so we implement it via execute()
            # This is a complex operation that deletes all project data
            db_start = time.time()
            logger.info(f"[DELETE_PROJECT] Starting database deletion for {self.project_id}")
            await _clear_project_data_impl(self.database, self.project_id)
            logger.info(
                f"[DELETE_PROJECT] Completed database deletion in {time.time() - db_start:.3f}s. "
                f"Deleted project {self.project_id} ({project_name}) from database: "
                f"{file_count} files, {chunk_count} chunks, {dataset_count} datasets"
            )

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
            logger.info(f"[DELETE_PROJECT] Total deletion time for {self.project_id}: {total_time:.3f}s")
            result["deletion_time_seconds"] = total_time

            if self.delete_from_disk:
                result["version_dir"] = (
                    str(version_dir_path) if version_dir_path else None
                )
                if disk_deletion_errors:
                    result["disk_deletion_errors"] = disk_deletion_errors
                    result[
                        "message"
                    ] += f" (with {len(disk_deletion_errors)} disk deletion error(s))"

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


class DeleteUnwatchedProjectsCommand:
    """
    Command to delete projects that are not in the list of watched directories.

    This command:
    1. Discovers all projects in watched directories using project discovery
    2. Finds all projects in the database
    3. Identifies projects that are not in the discovered list
    4. Deletes those projects

    Use with caution - this operation cannot be undone.
    """

    def __init__(
        self,
        database: DatabaseClient,
        watched_dirs: List[str],
        dry_run: bool = False,
        server_root_dir: Optional[str] = None,
    ):
        """
        Initialize delete unwatched projects command.

        Args:
            database: DatabaseClient instance
            watched_dirs: List of watched directory paths (absolute)
            dry_run: If True, only show what would be deleted
            server_root_dir: Server root directory (will be protected from deletion)
        """
        self.database = database
        self.watched_dirs = {Path(d).resolve() for d in watched_dirs}
        self.dry_run = dry_run
        self.server_root_dir = (
            Path(server_root_dir).resolve() if server_root_dir else None
        )

    async def execute(self) -> Dict[str, Any]:
        """
        Execute deletion of unwatched projects.

        Uses project discovery to find all projects in watched directories,
        then compares with database projects to find unwatched ones.

        Returns:
            Dictionary with deletion results
        """
        from ..core.project_discovery import (
            discover_projects_in_directory,
            NestedProjectError,
            DuplicateProjectIdError,
        )

        # Step 1: Discover all projects in watched directories
        discovered_project_ids: Set[str] = set()
        discovery_errors = []

        for watched_dir in self.watched_dirs:
            try:
                discovered_projects = discover_projects_in_directory(watched_dir)
                discovered_project_ids.update(p.project_id for p in discovered_projects)
                logger.debug(
                    f"Discovered {len(discovered_projects)} project(s) in {watched_dir}"
                )
            except NestedProjectError as e:
                logger.error(f"Nested project error in {watched_dir}: {e}")
                discovery_errors.append(f"Nested project in {watched_dir}: {e}")
            except DuplicateProjectIdError as e:
                logger.error(f"Duplicate project_id error in {watched_dir}: {e}")
                discovery_errors.append(f"Duplicate project_id in {watched_dir}: {e}")
            except Exception as e:
                logger.error(f"Error discovering projects in {watched_dir}: {e}")
                discovery_errors.append(f"Error in {watched_dir}: {e}")

        # Step 2: Get all projects from database
        result = self.database.execute("SELECT id, root_path, name FROM projects")
        # Handle different result formats
        if isinstance(result, list):
            all_projects = result
        elif isinstance(result, dict):
            all_projects = result.get("data", [])
        else:
            all_projects = []

        projects_to_delete = []
        projects_to_keep = []

        # Step 3: Compare database projects with discovered projects
        for project in all_projects:
            project_id = project["id"]
            root_path = project["root_path"]
            project_name = project.get("name", "Unknown")

            # Normalize project root path
            try:
                project_path = Path(root_path).resolve()
            except Exception as e:
                logger.warning(f"Invalid project path {root_path}: {e}")
                # If path is invalid, consider it unwatched
                projects_to_delete.append(
                    {
                        "project_id": project_id,
                        "root_path": root_path,
                        "name": project_name,
                        "reason": "invalid_path",
                    }
                )
                continue

            # Protect server root directory from deletion
            if self.server_root_dir and project_path == self.server_root_dir:
                projects_to_keep.append(
                    {
                        "project_id": project_id,
                        "root_path": root_path,
                        "name": project_name,
                        "reason": "server_root_protected",
                    }
                )
                continue

            # Check if project root path exists on disk
            if not project_path.exists():
                # Project root doesn't exist on disk - mark for deletion
                projects_to_delete.append(
                    {
                        "project_id": project_id,
                        "root_path": root_path,
                        "name": project_name,
                        "reason": "root_path_not_exists_on_disk",
                    }
                )
                continue

            # Check if project is in discovered projects
            if project_id in discovered_project_ids:
                projects_to_keep.append(
                    {
                        "project_id": project_id,
                        "root_path": root_path,
                        "name": project_name,
                        "reason": "discovered_in_watch_dirs",
                    }
                )
            else:
                # Project exists on disk but not in watched directories
                # Keep it (it's a valid project, just not in current watch_dirs config)
                projects_to_keep.append(
                    {
                        "project_id": project_id,
                        "root_path": root_path,
                        "name": project_name,
                        "reason": "exists_on_disk_but_not_in_watch_dirs",
                    }
                )

        if not projects_to_delete:
            return {
                "success": True,
                "dry_run": self.dry_run,
                "deleted_count": 0,
                "kept_count": len(projects_to_keep),
                "projects_deleted": [],
                "projects_kept": projects_to_keep,
                "message": "No unwatched projects found",
            }

        # Delete projects
        deleted_projects = []
        errors = []

        for project_info in projects_to_delete:
            project_id = project_info["project_id"]

            if self.dry_run:
                deleted_projects.append(project_info)
            else:
                try:
                    await _clear_project_data_impl(self.database, project_id)
                    deleted_projects.append(project_info)
                    logger.info(
                        f"Deleted unwatched project {project_info['name']} "
                        f"({project_id}): {project_info['root_path']}"
                    )
                except Exception as e:
                    error_info = {
                        "project_id": project_id,
                        "root_path": project_info["root_path"],
                        "name": project_info["name"],
                        "error": str(e),
                    }
                    errors.append(error_info)
                    logger.error(
                        f"Failed to delete project {project_id}: {e}",
                        exc_info=True,
                    )

        return {
            "success": len(errors) == 0 and len(discovery_errors) == 0,
            "dry_run": self.dry_run,
            "deleted_count": len(deleted_projects),
            "kept_count": len(projects_to_keep),
            "projects_deleted": deleted_projects,
            "projects_kept": projects_to_keep,
            "discovery_errors": discovery_errors if discovery_errors else None,
            "errors": errors if errors else None,
            "message": (
                f"Deleted {len(deleted_projects)} unwatched project(s), "
                f"kept {len(projects_to_keep)} watched project(s)"
            ),
        }
