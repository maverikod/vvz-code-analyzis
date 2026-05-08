"""
Command to repair database integrity based on actual file presence.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union, cast

if TYPE_CHECKING:
    from ...core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

from ...core.sql_portable import sql_julian_timestamp_now_expr

logger = logging.getLogger(__name__)

_FileRowId = Union[str, int]


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
    - version_dir: Version directory for deleted files (used when trash_dir is None)
    - trash_dir: Preferred root for file trash; files under trash_dir/project_id (FILE_TRASH_SPEC)
    - dry_run: If True, only show what would be repaired
    - force: If True, allow overwriting existing file when restoring from DB (backup first)
    """

    def __init__(
        self,
        database: "DatabaseClient",
        project_id: str,
        root_dir: Path,
        version_dir: str,
        dry_run: bool = False,
        trash_dir: Optional[str] = None,
        force: bool = False,
    ):
        """
        Initialize repair database command.

        Args:
            database: DatabaseClient instance
            project_id: Project ID
            root_dir: Project root directory
            version_dir: Version directory for deleted files (used when trash_dir is None)
            dry_run: If True, only show what would be repaired
            trash_dir: Optional; when set, file trash is under trash_dir/project_id
            force: If True, overwrite existing file when restoring from DB (after backup)
        """
        self.database = database
        self.project_id = project_id
        self.root_dir = root_dir
        self.version_dir = version_dir
        self.dry_run = dry_run
        self.trash_dir = trash_dir
        self.force = force
        self._repair_git_paths: List[Path] = []

    async def execute(self) -> Dict[str, Any]:
        """
        Execute repair database command.

        Returns:
            Dictionary with repair statistics
        """
        result: Dict[str, Any] = {
            "files_in_project_restored": [],
            "files_in_versions_marked_deleted": [],
            "files_restored_from_cst": [],
            "errors": [],
            "workers_stopped": {},
            "dry_run": self.dry_run,
        }
        self._repair_git_paths.clear()

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

            # Get all files in versions/file-trash directory (FILE_TRASH_SPEC step 13)
            if self.trash_dir:
                from ...core.storage_paths import get_file_trash_dir

                version_dir_path = get_file_trash_dir(
                    Path(self.trash_dir), self.project_id
                )
            else:
                version_dir_path = Path(self.version_dir) / self.project_id
            version_files = set()
            if version_dir_path.exists():
                for py_file in version_dir_path.rglob("*.py"):
                    if py_file.is_file():
                        version_files.add(str(py_file))

            logger.info(
                f"Found {len(project_files)} files in project, {len(version_files)} in versions"
            )

            # Process each file in database (convert File to dict if needed)
            for file_obj in all_files:
                file_record = (
                    file_obj.to_db_row()
                    if hasattr(file_obj, "to_db_row")
                    else cast(Dict[str, Any], file_obj)
                )
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
                                _now = sql_julian_timestamp_now_expr(self.database)
                                self.database.execute(
                                    f"""
                                    UPDATE files 
                                    SET deleted = 0, 
                                        original_path = NULL, 
                                        version_dir = NULL, 
                                        path = ?,
                                        updated_at = {_now}
                                    WHERE id = ?
                                    """,
                                    (check_path, file_id),
                                )
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
                                    if self.trash_dir:
                                        self.database.mark_file_deleted(
                                            file_path=check_path,
                                            project_id=self.project_id,
                                            trash_dir=self.trash_dir,
                                        )
                                    else:
                                        self.database.mark_file_deleted(
                                            file_path=check_path,
                                            project_id=self.project_id,
                                            version_dir=self.version_dir,
                                        )
                                    self._append_repair_git_path(check_path)
                            result["files_in_versions_marked_deleted"].append(
                                {"id": file_id, "path": check_path}
                            )
                            logger.info(
                                f"Marked file in versions as deleted: {check_path}"
                            )
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
                                file_id, check_path, file_record, force=self.force
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

        uniq: Dict[str, Path] = {}
        for p in self._repair_git_paths:
            rp = p.resolve()
            uniq[str(rp)] = rp
        result["repair_git_paths"] = sorted(uniq.keys())

        return result

    def _append_repair_git_path(self, path_str: str) -> None:
        """Record a project-tree path for git staging (under root_dir only)."""
        raw = Path(path_str)
        candidate = (
            raw.resolve() if raw.is_absolute() else (self.root_dir / path_str).resolve()
        )
        try:
            candidate.relative_to(self.root_dir.resolve())
        except ValueError:
            return
        self._repair_git_paths.append(candidate)

    async def _restore_file_from_cst(
        self,
        file_id: _FileRowId,
        file_path: str,
        file_record: Dict[str, Any],
        force: bool = False,
    ) -> bool:
        """
        Restore file from DB using full stored payload (snapshot or CST).

        Safe mode: when target file exists, refuse overwrite (return False).
        Force mode: when target exists and force=True, create backup first, then overwrite.
        After writing file, sync DB from file via unified pipeline (sync_file_to_db_atomic).

        Args:
            file_id: File primary key (UUID or legacy int)
            file_path: File path
            file_record: File record from database
            force: If True, allow overwrite after mandatory backup

        Returns:
            True if file was restored, False otherwise
        """
        try:
            source_code = await self._get_restore_payload(file_id)
            if not source_code:
                logger.warning(
                    "No full source payload found for file_id=%s (snapshot or cst_trees)",
                    file_id,
                )
                return False

            # Determine target path (FILE_TRASH_SPEC step 13: use path from DB for trash)
            if file_record.get("deleted"):
                target_path = Path(file_record["path"])
                target_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                target_path = (self.root_dir / file_path).resolve()

            # Safe mode: refuse overwrite when file exists and force is False
            if target_path.exists() and not force:
                logger.warning(
                    "Restore-from-DB skipped: target already exists at %s (use force=True to overwrite with backup)",
                    target_path,
                )
                return False

            # Force mode: mandatory backup before overwrite
            if target_path.exists() and force:
                from ...core.backup_manager import BackupManager

                backup_manager = BackupManager(self.root_dir)
                backup_uuid = backup_manager.create_backup(
                    target_path,
                    command="restore_from_db_force",
                    comment="before overwrite from DB",
                )
                if not backup_uuid:
                    logger.error(
                        "Restore-from-DB aborted: backup failed for %s; cannot overwrite without backup",
                        target_path,
                    )
                    return False
                logger.info("Backup created for force restore: %s", backup_uuid)

            # Restore file content (full payload)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(source_code, encoding="utf-8")

            # Sync DB from file via unified pipeline (file -> db)
            project_id = file_record.get("project_id")
            if project_id:
                from ...core.database.file_tree_sync import sync_file_to_db_atomic

                abs_path = str(target_path)
                file_mtime = target_path.stat().st_mtime
                sync_result = sync_file_to_db_atomic(
                    self.database,
                    project_id=str(project_id),
                    absolute_path=abs_path,
                    source_code=source_code,
                    file_mtime=file_mtime,
                    file_id=file_id,
                )
                if not sync_result.get("success"):
                    logger.warning(
                        "Failed to sync DB after restoration: %s",
                        sync_result.get("error"),
                    )
                else:
                    logger.info(
                        "DB synced after restoration: snapshot=%s, nodes=%s",
                        sync_result.get("snapshot", 0),
                        sync_result.get("nodes", 0),
                    )

            logger.info("Restored file %s from DB to %s", file_path, target_path)
            tp = target_path.resolve()
            try:
                tp.relative_to(self.root_dir.resolve())
                self._repair_git_paths.append(tp)
            except ValueError:
                pass
            return True

        except Exception as e:
            logger.error("Error restoring file from DB: %s", e, exc_info=True)
            return False

    async def _get_restore_payload(self, file_id: _FileRowId) -> Optional[str]:
        """
        Get full source payload for restore (snapshot source_payload or cst_trees.cst_code).

        Prefers file_tree_snapshots.source_payload when available; falls back to
        cst_trees.cst_code for backward compatibility.
        """
        try:
            row_result = cast(
                Dict[str, Any],
                self.database.execute(
                    "SELECT source_payload FROM file_tree_snapshots WHERE file_id = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (file_id,),
                ),
            )
            data: List[Any] = row_result.get("data", [])
            if data and data[0].get("source_payload"):
                return str(data[0]["source_payload"])
        except Exception as e:
            logger.debug(
                "No snapshot payload for file_id=%s (%s), trying cst_trees",
                file_id,
                e,
            )
        db = cast(Any, self.database)
        cst_data = await db.get_cst_tree(file_id)
        if cst_data and cst_data.get("cst_code"):
            return str(cst_data["cst_code"])
        return None

    async def _stop_all_workers(self) -> Dict[str, Any]:
        """
        Stop all workers (file_watcher, vectorization, repair) before repair.

        Returns:
            Dictionary with stop results
        """
        result: Dict[str, Any] = {
            "stopped_count": 0,
            "stopped_workers": [],
            "errors": [],
        }

        try:
            import psutil

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
                    logger.info(f"Sent SIGTERM to {worker_type} worker (PID: {pid})")

                    # Wait up to 10 seconds for graceful shutdown
                    try:
                        proc.wait(timeout=10)
                        logger.info(
                            f"{worker_type} worker stopped gracefully (PID: {pid})"
                        )
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
