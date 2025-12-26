"""
Internal commands for file management (cleanup, unmark, collapse versions).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase
else:
    CodeDatabase = Any

logger = logging.getLogger(__name__)


class CleanupDeletedFilesCommand:
    """
    Command to clean up deleted files from database.

    Options:
    - project_id: Specific project (optional, all projects if not specified)
    - dry_run: Show what would be deleted without actually deleting
    - older_than_days: Only delete files deleted more than N days ago
    - hard_delete: Permanently delete (removes all data, chunks, FAISS vectors)

    Hard delete removes:
    - File record
    - Physical file from version directory
    - All chunks (and removes from FAISS index)
    - All classes, functions, methods
    - All AST trees
    - All vector indexes

    Use with caution - cannot be recovered.
    """

    def __init__(
        self,
        database: CodeDatabase,
        project_id: Optional[str] = None,
        dry_run: bool = False,
        older_than_days: Optional[int] = None,
        hard_delete: bool = False,
    ):
        """
        Initialize cleanup command.

        Args:
            database: CodeDatabase instance
            project_id: Optional project ID (all projects if None)
            dry_run: If True, only show what would be deleted
            older_than_days: Only delete files deleted more than N days ago
            hard_delete: If True, permanently delete (default: False, just list)
        """
        self.database = database
        self.project_id = project_id
        self.dry_run = dry_run
        self.older_than_days = older_than_days
        self.hard_delete = hard_delete

    async def execute(self) -> Dict[str, Any]:
        """
        Execute cleanup command.

        Returns:
            Dictionary with cleanup statistics
        """
        import time

        result = {
            "deleted_files": [],
            "total_files": 0,
            "total_size": 0,
            "dry_run": self.dry_run,
            "hard_delete": self.hard_delete,
        }

        try:
            # Get deleted files
            if self.project_id:
                deleted_files = self.database.get_deleted_files(self.project_id)
            else:
                # Get all projects and their deleted files
                cursor = self.database.conn.cursor()
                cursor.execute("SELECT id FROM projects")
                projects = cursor.fetchall()
                deleted_files = []
                for project_row in projects:
                    project_id = project_row[0]
                    deleted_files.extend(self.database.get_deleted_files(project_id))

            # Filter by age if specified
            if self.older_than_days:
                cutoff_time = time.time() - (self.older_than_days * 24 * 3600)
                deleted_files = [
                    f for f in deleted_files if f.get("updated_at", 0) < cutoff_time
                ]

            result["total_files"] = len(deleted_files)

            if self.dry_run:
                # Just collect information
                for file_info in deleted_files:
                    file_id = file_info["id"]
                    file_path = file_info.get("path", "unknown")
                    version_dir = file_info.get("version_dir")
                    deleted_at = file_info.get("updated_at", 0)

                    file_size = 0
                    if version_dir and file_path:
                        try:
                            file_path_obj = Path(file_path)
                            if file_path_obj.exists():
                                file_size = file_path_obj.stat().st_size
                        except Exception:
                            pass

                    result["deleted_files"].append(
                        {
                            "id": file_id,
                            "path": file_path,
                            "version_dir": version_dir,
                            "deleted_at": deleted_at,
                            "size": file_size,
                        }
                    )
                    result["total_size"] += file_size

                result["message"] = (
                    f"Would delete {result['total_files']} files "
                    f"({result['total_size']} bytes)"
                )
            elif self.hard_delete:
                # Actually delete files
                for file_info in deleted_files:
                    file_id = file_info["id"]
                    file_path = file_info.get("path", "unknown")
                    version_dir = file_info.get("version_dir")

                    try:
                        # Hard delete removes physical file and all DB data
                        self.database.hard_delete_file(file_id)
                        result["deleted_files"].append(
                            {"id": file_id, "path": file_path, "deleted": True}
                        )
                        logger.info(f"Hard deleted file ID {file_id}: {file_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete file ID {file_id}: {e}")
                        result["deleted_files"].append(
                            {
                                "id": file_id,
                                "path": file_path,
                                "deleted": False,
                                "error": str(e),
                            }
                        )

                result["message"] = f"Deleted {result['total_files']} files"
            else:
                # Just list files
                for file_info in deleted_files:
                    result["deleted_files"].append(
                        {
                            "id": file_info["id"],
                            "path": file_info.get("path", "unknown"),
                            "version_dir": file_info.get("version_dir"),
                            "deleted_at": file_info.get("updated_at", 0),
                        }
                    )

                result["message"] = f"Found {result['total_files']} deleted files"

        except Exception as e:
            logger.error(f"Error in cleanup command: {e}", exc_info=True)
            result["error"] = str(e)

        return result


class UnmarkDeletedFileCommand:
    """
    Command to unmark file as deleted (recovery).

    Process:
    1. Finds file in version directory (by path or original_path)
    2. Moves file back to original_path
    3. Clears deleted flag, original_path, version_dir
    4. File will be processed again

    Options:
    - file_path: File path (current path in version_dir or original_path)
    - project_id: Project ID
    - dry_run: Show what would be restored without actually restoring
    """

    def __init__(
        self,
        database: "CodeDatabase",
        file_path: str,
        project_id: str,
        dry_run: bool = False,
    ):
        """
        Initialize unmark command.

        Args:
            database: CodeDatabase instance
            file_path: File path (current in version_dir or original_path)
            project_id: Project ID
            dry_run: If True, only show what would be restored
        """
        self.database = database
        self.file_path = file_path
        self.project_id = project_id
        self.dry_run = dry_run

    async def execute(self) -> Dict[str, Any]:
        """
        Execute unmark command.

        Returns:
            Dictionary with restoration information
        """
        result = {
            "restored": False,
            "file_path": self.file_path,
            "original_path": None,
            "version_dir": None,
            "dry_run": self.dry_run,
        }

        try:
            # Get file info
            cursor = self.database.conn.cursor()
            cursor.execute(
                """
                SELECT id, path, original_path, version_dir 
                FROM files 
                WHERE project_id = ? AND (path = ? OR original_path = ?)
                ORDER BY last_modified DESC
                LIMIT 1
                """,
                (self.project_id, self.file_path, self.file_path),
            )
            row = cursor.fetchone()

            if not row:
                result["error"] = f"File not found: {self.file_path}"
                return result

            file_id, current_path, original_path, version_dir = (
                row[0],
                row[1],
                row[2],
                row[3],
            )

            result["original_path"] = original_path
            result["version_dir"] = version_dir

            if not original_path:
                result["error"] = "File has no original_path, cannot restore"
                return result

            if self.dry_run:
                result["message"] = (
                    f"Would restore file from {current_path} to {original_path}"
                )
                result["restored"] = True  # Would be restored
            else:
                # Actually restore
                success = self.database.unmark_file_deleted(
                    self.file_path, self.project_id
                )
                result["restored"] = success
                if success:
                    result["message"] = f"Restored file to {original_path}"
                else:
                    result["error"] = "Failed to restore file"

        except Exception as e:
            logger.error(f"Error in unmark command: {e}", exc_info=True)
            result["error"] = str(e)

        return result


class CollapseVersionsCommand:
    """
    Command to collapse file versions, keeping only latest by last_modified.

    Finds all records with same path but different last_modified.
    Keeps the one with latest last_modified, deletes others (hard delete).

    Options:
    - project_id: Project ID
    - keep_latest: If True, keep latest version (default: True)
    - dry_run: Show what would be collapsed without actually collapsing
    """

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        keep_latest: bool = True,
        dry_run: bool = False,
    ):
        """
        Initialize collapse command.

        Args:
            database: CodeDatabase instance
            project_id: Project ID
            keep_latest: If True, keep latest version (default: True)
            dry_run: If True, only show what would be collapsed
        """
        self.database = database
        self.project_id = project_id
        self.keep_latest = keep_latest
        self.dry_run = dry_run

    async def execute(self) -> Dict[str, Any]:
        """
        Execute collapse command.

        Returns:
            Dictionary with collapse statistics
        """
        result = {
            "kept_count": 0,
            "deleted_count": 0,
            "collapsed_files": [],
            "dry_run": self.dry_run,
        }

        try:
            if self.dry_run:
                # Just analyze, don't delete
                cursor = self.database.conn.cursor()
                cursor.execute(
                    """
                    SELECT path, COUNT(*) as version_count
                    FROM files
                    WHERE project_id = ?
                    GROUP BY path
                    HAVING COUNT(*) > 1
                    """,
                    (self.project_id,),
                )
                files_with_versions = cursor.fetchall()

                for path_row in files_with_versions:
                    file_path = path_row[0]
                    version_count = path_row[1]

                    # Get all versions
                    versions = self.database.get_file_versions(
                        file_path, self.project_id
                    )

                    if self.keep_latest:
                        keep_version = versions[0]  # Latest
                        delete_versions = versions[1:]
                    else:
                        keep_version = versions[-1]  # Oldest
                        delete_versions = versions[:-1]

                    result["collapsed_files"].append(
                        {
                            "path": file_path,
                            "version_count": version_count,
                            "keep": {
                                "id": keep_version["id"],
                                "last_modified": keep_version.get("last_modified"),
                            },
                            "delete": [
                                {"id": v["id"], "last_modified": v.get("last_modified")}
                                for v in delete_versions
                            ],
                        }
                    )
                    result["kept_count"] += 1
                    result["deleted_count"] += len(delete_versions)

                result["message"] = (
                    f"Would collapse {len(result['collapsed_files'])} files: "
                    f"keep {result['kept_count']}, delete {result['deleted_count']}"
                )
            else:
                # Actually collapse
                collapse_result = self.database.collapse_file_versions(
                    self.project_id, self.keep_latest
                )
                result.update(collapse_result)
                result["message"] = (
                    f"Collapsed {len(result['collapsed_files'])} files: "
                    f"kept {result['kept_count']}, deleted {result['deleted_count']}"
                )

        except Exception as e:
            logger.error(f"Error in collapse command: {e}", exc_info=True)
            result["error"] = str(e)

        return result


class RepairDatabaseCommand:
    """
    Command to repair database integrity - restore correct file status based on actual file presence.

    Process:
    1. If file exists in project directory - remove deleted flag
    2. If file exists in versions but not in project - set deleted flag
    3. If file doesn't exist anywhere - restore from CST nodes:
       - Place in versions directory
       - Add to project files if not marked for deletion

    This restores correct database structure based on actual file system state.

    Options:
    - project_id: Project ID
    - root_dir: Project root directory
    - version_dir: Version directory for deleted files
    - dry_run: If True, only show what would be repaired
    """

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        root_dir: Path,
        version_dir: str,
        dry_run: bool = False,
    ):
        """
        Initialize repair database command.

        Args:
            database: CodeDatabase instance
            project_id: Project ID
            root_dir: Project root directory
            version_dir: Version directory for deleted files
            dry_run: If True, only show what would be repaired
        """
        self.database = database
        self.project_id = project_id
        self.root_dir = root_dir
        self.version_dir = version_dir
        self.dry_run = dry_run

    async def execute(self) -> Dict[str, Any]:
        """
        Execute repair database command.

        Returns:
            Dictionary with repair statistics
        """
        result = {
            "files_in_project_restored": [],
            "files_in_versions_marked_deleted": [],
            "files_restored_from_cst": [],
            "errors": [],
            "workers_stopped": {},
            "dry_run": self.dry_run,
        }

        try:
            # Stop all workers before repair
            if not self.dry_run:
                logger.info("Stopping all workers before database repair...")
                workers_stopped = await self._stop_all_workers()
                result["workers_stopped"] = workers_stopped
                logger.info(
                    f"Stopped workers: {workers_stopped.get('stopped_count', 0)} "
                    f"workers, {len(workers_stopped.get('errors', []))} errors"
                )
            # Get all files from database
            all_files = self.database.get_project_files(self.project_id)
            logger.info(f"Found {len(all_files)} files in database")

            # Get all files in project directory
            project_files = set()
            for py_file in self.root_dir.rglob("*.py"):
                if py_file.is_file():
                    project_files.add(str(py_file))

            # Get all files in versions directory
            version_dir_path = Path(self.version_dir) / self.project_id
            version_files = set()
            if version_dir_path.exists():
                for py_file in version_dir_path.rglob("*.py"):
                    if py_file.is_file():
                        version_files.add(str(py_file))

            logger.info(
                f"Found {len(project_files)} files in project, {len(version_files)} in versions"
            )

            # Process each file in database
            for file_record in all_files:
                file_id = file_record["id"]
                db_path = file_record["path"]
                is_deleted = file_record.get("deleted", 0) == 1
                original_path = file_record.get("original_path")

                # Determine actual file path to check
                check_path = original_path if original_path else db_path

                # Case 1: File exists in project directory
                if check_path in project_files or db_path in project_files:
                    if is_deleted:
                        # File exists but marked as deleted - restore it
                        try:
                            if not self.dry_run:
                                with self.database._lock:
                                    cursor = self.database.conn.cursor()
                                    cursor.execute(
                                        """
                                        UPDATE files 
                                        SET deleted = 0, 
                                            original_path = NULL, 
                                            version_dir = NULL, 
                                            path = ?,
                                            updated_at = julianday('now')
                                        WHERE id = ?
                                        """,
                                        (check_path, file_id),
                                    )
                                    self.database.conn.commit()
                            result["files_in_project_restored"].append(
                                {"id": file_id, "path": check_path}
                            )
                            logger.info(f"Restored file in project: {check_path}")
                        except Exception as e:
                            error_msg = f"Error restoring {check_path}: {e}"
                            logger.error(error_msg)
                            result["errors"].append(error_msg)

                # Case 2: File exists in versions but not in project
                elif check_path in version_files or db_path in version_files:
                    if not is_deleted:
                        # File in versions but not marked as deleted - mark it
                        try:
                            if not self.dry_run:
                                # Find version file path
                                version_file_path = None
                                if check_path in version_files:
                                    version_file_path = check_path
                                elif db_path in version_files:
                                    version_file_path = db_path
                                else:
                                    # Try to find in versions
                                    for vf in version_files:
                                        if Path(vf).name == Path(check_path).name:
                                            version_file_path = vf
                                            break

                                if version_file_path:
                                    self.database.mark_file_deleted(
                                        file_path=check_path,
                                        project_id=self.project_id,
                                        version_dir=self.version_dir,
                                    )
                            result["files_in_versions_marked_deleted"].append(
                                {"id": file_id, "path": check_path}
                            )
                            logger.info(f"Marked file in versions as deleted: {check_path}")
                        except Exception as e:
                            error_msg = f"Error marking {check_path} as deleted: {e}"
                            logger.error(error_msg)
                            result["errors"].append(error_msg)

                # Case 3: File doesn't exist anywhere - restore from CST
                else:
                    if not is_deleted:
                        # File not found but not marked as deleted - try to restore from CST
                        try:
                            restored = await self._restore_file_from_cst(
                                file_id, check_path, file_record
                            )
                            if restored:
                                result["files_restored_from_cst"].append(
                                    {"id": file_id, "path": check_path}
                                )
                                logger.info(f"Restored file from CST: {check_path}")
                            else:
                                result["errors"].append(
                                    f"Could not restore {check_path} from CST"
                                )
                        except Exception as e:
                            error_msg = f"Error restoring {check_path} from CST: {e}"
                            logger.error(error_msg)
                            result["errors"].append(error_msg)

            # Build summary message
            result["message"] = (
                f"Repaired database: "
                f"{len(result['files_in_project_restored'])} files restored in project, "
                f"{len(result['files_in_versions_marked_deleted'])} files marked as deleted, "
                f"{len(result['files_restored_from_cst'])} files restored from CST, "
                f"{len(result['errors'])} errors"
            )
            logger.info(result["message"])

        except Exception as e:
            logger.error(f"Error in repair database command: {e}", exc_info=True)
            result["error"] = str(e)

        return result

    async def _restore_file_from_cst(
        self, file_id: int, file_path: str, file_record: Dict[str, Any]
    ) -> bool:
        """
        Restore file from CST nodes.

        Args:
            file_id: File ID
            file_path: File path
            file_record: File record from database

        Returns:
            True if file was restored, False otherwise
        """
        try:
            # Get AST tree from database
            with self.database._lock:
                cursor = self.database.conn.cursor()
                cursor.execute(
                    "SELECT tree_json FROM ast_trees WHERE file_id = ?", (file_id,)
                )
                row = cursor.fetchone()
                if not row:
                    logger.warning(f"No AST tree found for file {file_id}")
                    return False

                # TODO: Restore file content from AST tree
                # This requires converting AST back to source code
                # For now, we'll mark the file as needing analysis
                # The file will be re-analyzed and restored during next analysis cycle

                logger.info(
                    f"AST tree found for {file_path}, but full restoration from AST not yet implemented"
                )
                return False

        except Exception as e:
            logger.error(f"Error restoring file from CST: {e}")
            return False

    async def _stop_all_workers(self) -> Dict[str, Any]:
        """
        Stop all workers (file_watcher, vectorization, repair) before repair.

        Returns:
            Dictionary with stop results
        """
        result = {
            "stopped_count": 0,
            "stopped_workers": [],
            "errors": [],
        }

        try:
            import psutil
            import signal

            # Find all worker processes
            worker_patterns = [
                ("file_watcher", ["file_watcher", "run_file_watcher_worker"]),
                ("vectorization", ["vectorization", "run_vectorization_worker"]),
                ("repair", ["repair_worker", "run_repair_worker"]),
            ]

            all_worker_processes = []
            for worker_type, patterns in worker_patterns:
                for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                    try:
                        cmdline = " ".join(proc.info["cmdline"] or [])
                        if any(pattern in cmdline.lower() for pattern in patterns):
                            all_worker_processes.append(
                                {
                                    "pid": proc.info["pid"],
                                    "type": worker_type,
                                    "cmdline": cmdline,
                                }
                            )
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

            logger.info(f"Found {len(all_worker_processes)} worker processes to stop")

            # Stop each worker gracefully
            for worker_info in all_worker_processes:
                pid = worker_info["pid"]
                worker_type = worker_info["type"]
                try:
                    proc = psutil.Process(pid)
                    if not proc.is_running():
                        continue

                    # Send SIGTERM for graceful shutdown
                    proc.terminate()
                    logger.info(
                        f"Sent SIGTERM to {worker_type} worker (PID: {pid})"
                    )

                    # Wait up to 10 seconds for graceful shutdown
                    try:
                        proc.wait(timeout=10)
                        logger.info(f"{worker_type} worker stopped gracefully (PID: {pid})")
                        result["stopped_count"] += 1
                        result["stopped_workers"].append(
                            {"pid": pid, "type": worker_type, "graceful": True}
                        )
                    except psutil.TimeoutExpired:
                        # Force kill if still running
                        proc.kill()
                        logger.warning(
                            f"Force killed {worker_type} worker (PID: {pid}) after timeout"
                        )
                        result["stopped_count"] += 1
                        result["stopped_workers"].append(
                            {"pid": pid, "type": worker_type, "graceful": False}
                        )

                except psutil.NoSuchProcess:
                    # Process already gone
                    result["stopped_count"] += 1
                    result["stopped_workers"].append(
                        {"pid": pid, "type": worker_type, "already_stopped": True}
                    )
                except Exception as e:
                    error_msg = f"Error stopping {worker_type} worker (PID: {pid}): {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)

            # Wait a bit for processes to fully terminate
            if all_worker_processes:
                import asyncio
                await asyncio.sleep(1)

        except ImportError:
            logger.warning("psutil not available, cannot stop workers")
            result["errors"].append("psutil not available")
        except Exception as e:
            logger.error(f"Error stopping workers: {e}", exc_info=True)
            result["errors"].append(str(e))

        return result
