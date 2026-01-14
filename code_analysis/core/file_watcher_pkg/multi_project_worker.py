"""
Multi-project file watcher worker.

This module implements a single-process file watcher that can monitor multiple
projects/directories in one loop. It is intended to replace the previous
multi-process approach where one file watcher process was spawned per directory.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .lock_manager import LockManager
from .processor import FileChangeProcessor
from .scanner import scan_directory

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WatchDirSpec:
    """
    Watched directory specification.

    Represents a directory to scan for projects. Projects are discovered
    automatically by finding projectid files within this directory.

    Attributes:
        watch_dir: Directory to scan for projects
        watch_dir_id: UUID4 identifier for this watch directory
    """

    watch_dir: Path
    watch_dir_id: str


class MultiProjectFileWatcherWorker:
    """
    Single-process file watcher that iterates over multiple projects.

    Responsibilities:
    - Establish a DB connection via sqlite_proxy (never spawns DB worker).
    - For each scan cycle, iterate through all configured projects and scan their
      root directories, then mark changed files for chunking.
    - Use lock files per root watched directory to avoid concurrent scans.
    """

    def __init__(
        self,
        db_path: Path,
        watch_dirs: Sequence[WatchDirSpec],
        locks_dir: Path,
        scan_interval: int = 60,
        version_dir: Optional[str] = None,
        ignore_patterns: Optional[List[str]] = None,
    ) -> None:
        """
        Initialize multi-project file watcher.

        Args:
            db_path: Path to SQLite database file.
            watch_dirs: Watched directories to scan for projects (projects discovered automatically).
            locks_dir: Service state directory for lock files (from StoragePaths).
            scan_interval: Delay between cycles in seconds.
            version_dir: Version directory for deleted files (optional).
            ignore_patterns: Glob patterns to ignore (optional).
        """
        self.db_path = db_path
        self.watch_dirs = list(watch_dirs)
        self.scan_interval = int(scan_interval)
        self.locks_dir = Path(locks_dir).resolve()
        self.version_dir = version_dir
        self.ignore_patterns = ignore_patterns or []

        self._stop_event = multiprocessing.Event()
        self._pid = os.getpid()

    def stop(self) -> None:
        """Stop the worker."""
        self._stop_event.set()

    async def run(self) -> Dict[str, Any]:
        """
        Main worker loop.

        Worker policy:
            - This process must NOT start other processes.
            - If DB worker/socket is unavailable, do NOT scan/process files; only
              retry connecting with backoff until available or stopped.

        Returns:
            Dictionary with processing statistics.
        """
        total_stats: Dict[str, Any] = {
            "scanned_dirs": 0,
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
            "cycles": 0,
            "watch_dirs": len(self.watch_dirs),
        }

        logger.info(
            "Starting multi-project file watcher worker | "
            f"pid={self._pid} | watch_dirs={len(self.watch_dirs)} | "
            f"scan_interval={self.scan_interval}s"
        )

        from ..database_client.client import DatabaseClient
        from ..constants import DEFAULT_DB_DRIVER_SOCKET_DIR

        # Get socket path for database driver
        db_name = Path(self.db_path).stem
        socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
        socket_dir.mkdir(parents=True, exist_ok=True)
        socket_path = str(socket_dir / f"{db_name}_driver.sock")

        database: Any = None
        # Processors are created dynamically per discovered project

        # Track database availability status
        db_available = False
        db_status_logged = False  # Track if we've logged the current status

        backoff = 1.0
        backoff_max = 60.0

        # Initialize watch_dirs on first successful database connection
        watch_dirs_initialized = False

        try:
            while not self._stop_event.is_set():
                if database is None:
                    try:
                        database = DatabaseClient(socket_path=socket_path)
                        database.connect()
                        # Test connection with a simple query
                        try:
                            # Try to get a project to test connection
                            database.execute("SELECT 1", None)
                            # Connection successful
                            if not db_available:
                                # Status changed: unavailable -> available
                                logger.info("✅ Database is now available")
                                db_available = True
                                db_status_logged = True
                                backoff = 1.0  # Reset backoff

                                # Initialize watch_dirs on first connection
                                if not watch_dirs_initialized:
                                    try:
                                        self._initialize_watch_dirs(database)
                                        watch_dirs_initialized = True
                                    except Exception as init_e:
                                        logger.error(
                                            f"Failed to initialize watch_dirs: {init_e}",
                                            exc_info=True,
                                        )
                                        # Continue anyway - will retry on next cycle
                            else:
                                db_status_logged = False  # Already logged as available
                        except Exception as conn_e:
                            # Connection test failed
                            if db_available:
                                # Status changed: available -> unavailable
                                logger.warning(
                                    f"⚠️  Database is now unavailable: {conn_e}"
                                )
                                db_available = False
                                db_status_logged = True
                            elif not db_status_logged:
                                # First time logging unavailability
                                logger.warning(f"⚠️  Database is unavailable: {conn_e}")
                                db_status_logged = True
                            else:
                                # Already logged, don't spam
                                db_status_logged = False

                            try:
                                database.disconnect()
                            except Exception:
                                pass
                            database = None

                            # Wait with backoff before retrying
                            logger.debug(
                                f"Retrying database connection in {backoff:.1f}s..."
                            )
                            await asyncio.sleep(backoff)
                            backoff = min(backoff * 2.0, backoff_max)
                            continue
                    except Exception as e:
                        # Failed to create database connection
                        total_stats["errors"] += 1
                        if db_available:
                            # Status changed: available -> unavailable
                            logger.warning(f"⚠️  Database is now unavailable: {e}")
                            db_available = False
                            db_status_logged = True
                        elif not db_status_logged:
                            # First time logging unavailability
                            logger.warning(f"⚠️  Database is unavailable: {e}")
                            db_status_logged = True
                        else:
                            # Already logged, don't spam
                            db_status_logged = False

                        # Wait with backoff before retrying
                        logger.debug(
                            f"Retrying database connection in {backoff:.1f}s..."
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2.0, backoff_max)
                        continue

                try:
                    cycle_stats = await self._scan_cycle(database, None)
                except Exception as e:
                    total_stats["errors"] += 1
                    error_str = str(e).lower()
                    # Check if error is due to database unavailability
                    if (
                        "database" in error_str
                        or "db" in error_str
                        or "connection" in error_str
                    ):
                        if db_available:
                            # Status changed: available -> unavailable
                            logger.warning(f"⚠️  Database is now unavailable: {e}")
                            db_available = False
                            db_status_logged = True
                        else:
                            logger.debug(f"Database error during cycle: {e}")
                    else:
                        logger.error(
                            f"File watcher cycle failed (will retry after reconnect): {e}",
                            exc_info=True,
                        )
                    try:
                        database.disconnect()
                    except Exception:
                        pass
                    database = None
                    db_status_logged = False
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, backoff_max)
                    continue

                total_stats["scanned_dirs"] += cycle_stats.get("scanned_dirs", 0)
                total_stats["new_files"] += cycle_stats.get("new_files", 0)
                total_stats["changed_files"] += cycle_stats.get("changed_files", 0)
                total_stats["deleted_files"] += cycle_stats.get("deleted_files", 0)
                total_stats["errors"] += cycle_stats.get("errors", 0)
                total_stats["cycles"] += 1

                from datetime import datetime

                cycle_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(
                    f"[CYCLE #{total_stats['cycles']}] {cycle_time} | "
                    f"watch_dirs: {len(self.watch_dirs)} | "
                    f"scanned_dirs: {cycle_stats.get('scanned_dirs', 0)} | "
                    f"new_files: {cycle_stats.get('new_files', 0)} | "
                    f"changed_files: {cycle_stats.get('changed_files', 0)} | "
                    f"deleted_files: {cycle_stats.get('deleted_files', 0)} | "
                    f"errors: {cycle_stats.get('errors', 0)}"
                )

                for _ in range(int(self.scan_interval)):
                    if self._stop_event.is_set():
                        break
                    await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("File watcher worker interrupted")
        finally:
            try:
                if database is not None:
                    database.disconnect()
            except Exception:
                pass

        return total_stats

    def _count_files_on_disk(self) -> int:
        """
        Count total number of code files on disk across all watched directories.

        This method uses the same scanning logic as _scan_watch_dir to ensure
        consistent file detection. It scans each watch_dir and counts all discovered files.

        Returns:
            Total number of code files found on disk
        """
        total_files = 0

        for spec in self.watch_dirs:
            watch_dir = spec.watch_dir
            if not watch_dir.exists():
                continue

            try:
                # Use scan_directory with same parameters as _scan_watch_dir
                # This ensures we count files using the same logic
                scanned_files = scan_directory(
                    root_dir=watch_dir,
                    watch_dirs=[spec.watch_dir],
                    ignore_patterns=self.ignore_patterns,
                )
                total_files += len(scanned_files)
            except Exception as e:
                logger.debug(f"Error counting files in {watch_dir}: {e}")
                continue

        return total_files

    async def _scan_cycle(self, database: Any, processors: Any) -> Dict[str, Any]:
        """
        Perform one scan cycle for all watched directories.

        Projects are discovered automatically within each watched directory.

        Args:
            database: CodeDatabase instance.
            processors: Unused (kept for API compatibility).

        Returns:
            Dictionary with cycle statistics.
        """
        import time

        # Count total files on disk before starting cycle
        logger.info("Counting total files on disk across all projects...")
        files_total_on_disk = self._count_files_on_disk()
        logger.info(f"Total files on disk: {files_total_on_disk}")

        # Start worker statistics cycle with disk file count
        import uuid

        cycle_id = str(uuid.uuid4())
        cycle_start_time = time.time()

        # Mark any old active cycles as ended
        database.execute(
            """
            UPDATE file_watcher_stats
            SET cycle_end_time = ?, last_updated = julianday('now')
            WHERE cycle_end_time IS NULL
            """,
            (cycle_start_time,),
        )

        # Insert new cycle record
        database.execute(
            """
            INSERT INTO file_watcher_stats (
                cycle_id, cycle_start_time, files_total_at_start, last_updated
            ) VALUES (?, ?, ?, julianday('now'))
            """,
            (cycle_id, cycle_start_time, files_total_on_disk),
        )

        cycle_stats: Dict[str, Any] = {
            "scanned_dirs": 0,
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }

        # Create a single processor for multi-project mode
        processor = FileChangeProcessor(
            database=database,
            watch_dirs=[spec.watch_dir for spec in self.watch_dirs],
            version_dir=self.version_dir,
        )

        total_processing_time = 0.0

        for spec in self.watch_dirs:
            if self._stop_event.is_set():
                break

            watch_dir_start = time.time()
            watch_dir_stats = self._scan_watch_dir(spec, processor, database)
            watch_dir_duration = time.time() - watch_dir_start
            total_processing_time += watch_dir_duration

            cycle_stats["scanned_dirs"] += watch_dir_stats.get("scanned_dirs", 0)
            cycle_stats["new_files"] += watch_dir_stats.get("new_files", 0)
            cycle_stats["changed_files"] += watch_dir_stats.get("changed_files", 0)
            cycle_stats["deleted_files"] += watch_dir_stats.get("deleted_files", 0)
            cycle_stats["errors"] += watch_dir_stats.get("errors", 0)

            # Update statistics after each watch_dir
            database.execute(
                """
                UPDATE file_watcher_stats
                SET
                    files_added = files_added + ?,
                    files_processed = files_processed + ?,
                    files_skipped = files_skipped + ?,
                    files_failed = files_failed + ?,
                    files_changed = files_changed + ?,
                    files_deleted = files_deleted + ?,
                    total_processing_time_seconds = total_processing_time_seconds + ?,
                    last_updated = julianday('now')
                WHERE cycle_id = ?
                """,
                (
                    watch_dir_stats.get("new_files", 0),
                    watch_dir_stats.get("new_files", 0)
                    + watch_dir_stats.get("changed_files", 0),
                    0,  # Skipped files are tracked separately if needed
                    watch_dir_stats.get("errors", 0),
                    watch_dir_stats.get("changed_files", 0),
                    watch_dir_stats.get("deleted_files", 0),
                    watch_dir_duration,
                    cycle_id,
                ),
            )

        # End cycle
        database.execute(
            """
            UPDATE file_watcher_stats
            SET cycle_end_time = ?, last_updated = julianday('now')
            WHERE cycle_id = ?
            """,
            (time.time(), cycle_id),
        )

        return cycle_stats

    def _scan_watch_dir(
        self, spec: WatchDirSpec, processor: FileChangeProcessor, database: Any
    ) -> Dict[str, Any]:
        """
        Scan a watched directory and process all discovered projects.

        Projects are discovered automatically by finding projectid files
        within the watched directory.

        Args:
            spec: Watch directory specification.
            processor: FileChangeProcessor for multi-project mode.
            database: CodeDatabase instance.

        Returns:
            Per-watch-dir scan stats.
        """
        stats: Dict[str, Any] = {
            "scanned_dirs": 0,
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }

        watch_dir = spec.watch_dir
        if not watch_dir.exists():
            logger.warning(f"Watched directory does not exist: {watch_dir}")
            return stats

        # Create LockManager for this watch_dir (use watch_dir path as lock key)
        lock_key = str(watch_dir.resolve())
        lock_manager = LockManager(self.locks_dir, lock_key)

        if not lock_manager.acquire_lock(watch_dir, self._pid):
            logger.warning(f"Could not acquire lock for {watch_dir}, skipping")
            stats["errors"] += 1
            return stats

        try:
            from datetime import datetime
            from ..project_discovery import (
                discover_projects_in_directory,
                NestedProjectError,
                DuplicateProjectIdError,
            )

            # Discover projects in this watch_dir
            try:
                discovered_projects = discover_projects_in_directory(watch_dir)
            except NestedProjectError as e:
                logger.error(
                    f"Nested project detected in {watch_dir}: {e}, skipping watch_dir"
                )
                stats["errors"] += 1
                return stats
            except DuplicateProjectIdError as e:
                logger.error(
                    f"Duplicate project_id detected in {watch_dir}: {e}, skipping watch_dir"
                )
                stats["errors"] += 1
                return stats

            if not discovered_projects:
                logger.debug(f"No projects found in watched directory: {watch_dir}")
                return stats

            # Auto-create projects in database if they don't exist (Phase 3.1)
            # Also validate that project_id is not used in different directories
            for project_root_obj in discovered_projects:
                try:
                    project_obj = database.get_project(project_root_obj.project_id)
                    project = (
                        {
                            "id": project_obj.id,
                            "root_path": project_obj.root_path,
                            "name": project_obj.name,
                            "comment": project_obj.comment,
                            "watch_dir_id": getattr(project_obj, "watch_dir_id", None),
                        }
                        if project_obj
                        else None
                    )
                    if project:
                        # Project exists - validate root_path matches
                        if project["root_path"] != str(project_root_obj.root_path):
                            logger.error(
                                f"Project ID {project_root_obj.project_id} already exists "
                                f"with different root_path: {project['root_path']} "
                                f"(found in {project_root_obj.root_path}). "
                                "One project_id cannot be used in different directories. Skipping."
                            )
                            stats["errors"] += 1
                            continue
                        # Project exists with correct root_path - update description and watch_dir_id if changed
                        current_comment = project.get("comment")
                        current_watch_dir_id = project.get("watch_dir_id")
                        watch_dir_id = spec.watch_dir_id
                        needs_update = False
                        update_fields = []
                        update_values = []

                        if current_comment != project_root_obj.description:
                            needs_update = True
                            update_fields.append("comment = ?")
                            update_values.append(project_root_obj.description)

                        if current_watch_dir_id != watch_dir_id:
                            needs_update = True
                            update_fields.append("watch_dir_id = ?")
                            update_values.append(watch_dir_id)

                        if needs_update:
                            update_values.append(project_root_obj.project_id)
                            database.execute(
                                f"""
                                UPDATE projects 
                                SET {', '.join(update_fields)}, updated_at = julianday('now')
                                WHERE id = ?
                                """,
                                tuple(update_values),
                            )
                            logger.debug(
                                f"Updated project {project_root_obj.project_id}: "
                                f"comment={current_comment} -> {project_root_obj.description}, "
                                f"watch_dir_id={current_watch_dir_id} -> {watch_dir_id}"
                            )
                    else:
                        # Check if project exists with different ID (by root_path)
                        existing_result = database.execute(
                            "SELECT id FROM projects WHERE root_path = ? LIMIT 1",
                            (str(project_root_obj.root_path),),
                        )
                        existing_rows = (
                            existing_result.get("data", [])
                            if isinstance(existing_result, dict)
                            else []
                        )
                        existing_project_id = (
                            existing_rows[0].get("id") if existing_rows else None
                        )
                        if existing_project_id:
                            if existing_project_id != project_root_obj.project_id:
                                logger.warning(
                                    f"Project at {project_root_obj.root_path} exists with "
                                    f"different ID ({existing_project_id}) than projectid file "
                                    f"({project_root_obj.project_id}), updating"
                                )
                                # Update project ID and description to match projectid file
                                database.execute(
                                    """
                                    UPDATE projects 
                                    SET id = ?, comment = ?, updated_at = julianday('now')
                                    WHERE id = ?
                                    """,
                                    (
                                        project_root_obj.project_id,
                                        project_root_obj.description,
                                        existing_project_id,
                                    ),
                                )
                            # Project exists with correct ID
                        else:
                            # Check if project_id is used by another root_path
                            existing_project_obj = database.get_project(
                                project_root_obj.project_id
                            )
                            existing_project = (
                                {
                                    "id": existing_project_obj.id,
                                    "root_path": existing_project_obj.root_path,
                                }
                                if existing_project_obj
                                else None
                            )
                            if existing_project:
                                logger.error(
                                    f"Project ID {project_root_obj.project_id} already exists "
                                    f"with root_path: {existing_project['root_path']} "
                                    f"(trying to use in {project_root_obj.root_path}). "
                                    "One project_id cannot be used in different directories. Skipping."
                                )
                                stats["errors"] += 1
                                continue

                            # Create project with ID from projectid file
                            project_name = project_root_obj.root_path.name
                            project_description = project_root_obj.description
                            # Get watch_dir_id from spec
                            watch_dir_id = spec.watch_dir_id
                            database.execute(
                                """
                                INSERT INTO projects (id, root_path, name, comment, watch_dir_id, updated_at)
                                VALUES (?, ?, ?, ?, ?, julianday('now'))
                                """,
                                (
                                    project_root_obj.project_id,
                                    str(project_root_obj.root_path),
                                    project_name,
                                    project_description,
                                    watch_dir_id,
                                ),
                            )
                            logger.info(
                                f"Auto-created project {project_root_obj.project_id} "
                                f"at {project_root_obj.root_path} "
                                f"with description: {project_description} "
                                f"and watch_dir_id: {watch_dir_id}"
                            )

                            # Start automatic indexing for newly created project in background thread
                            try:
                                import threading
                                import asyncio
                                from code_analysis.core.constants import (
                                    DEFAULT_MAX_FILE_LINES,
                                )
                                from code_analysis.commands.code_mapper_mcp_command import (
                                    UpdateIndexesMCPCommand,
                                )

                                def run_indexing():
                                    """Run indexing in background thread."""
                                    try:
                                        # Create new event loop for this thread
                                        loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(loop)

                                        try:
                                            cmd = UpdateIndexesMCPCommand()
                                            result = loop.run_until_complete(
                                                cmd.execute(
                                                    root_dir=str(
                                                        project_root_obj.root_path
                                                    ),
                                                    max_lines=DEFAULT_MAX_FILE_LINES,
                                                )
                                            )

                                            if not result.success:
                                                logger.warning(
                                                    f"Auto-indexing for new project {project_root_obj.project_id} "
                                                    f"completed with warnings: {result.message}"
                                                )
                                            else:
                                                logger.info(
                                                    f"Auto-indexing for new project {project_root_obj.project_id} "
                                                    f"completed: {result.data.get('files_processed', 0) if result.data else 0} files processed"
                                                )
                                        finally:
                                            loop.close()
                                    except Exception as e:
                                        logger.error(
                                            f"Failed to run auto-indexing for new project "
                                            f"{project_root_obj.project_id}: {e}",
                                            exc_info=True,
                                        )

                                thread = threading.Thread(
                                    target=run_indexing, daemon=True
                                )
                                thread.start()
                                logger.info(
                                    f"Started background indexing thread for newly created project "
                                    f"{project_root_obj.project_id}"
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to start auto-indexing for new project "
                                    f"{project_root_obj.project_id}: {e}"
                                )
                except Exception as e:
                    logger.error(
                        f"Failed to get/create project {project_root_obj.project_id} "
                        f"at {project_root_obj.root_path}: {e}",
                        exc_info=True,  # Include full traceback for debugging
                    )
                    stats["errors"] += 1

            logger.info(
                f"[SCAN START] Watch directory: {watch_dir} | "
                f"discovered_projects: {len(discovered_projects)} | "
                f"time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # Scan directory with project discovery
            scan_start = datetime.now()
            scanned_files = scan_directory(
                root_dir=watch_dir,
                watch_dirs=[spec.watch_dir],
                ignore_patterns=self.ignore_patterns,
            )

            # Compute delta (scan phase - returns Dict[str, FileDelta] in multi-project mode)
            delta = processor.compute_delta(watch_dir, scanned_files)
            scan_end = datetime.now()
            scan_duration = (scan_end - scan_start).total_seconds()

            # Log scan results (delta is always Dict[str, FileDelta])
            total_new = sum(len(d.new_files) for d in delta.values())
            total_changed = sum(len(d.changed_files) for d in delta.values())
            total_deleted = sum(len(d.deleted_files) for d in delta.values())
            logger.info(
                f"[SCAN END] Watch directory: {watch_dir} | "
                f"time: {scan_end.strftime('%Y-%m-%d %H:%M:%S')} | "
                f"duration: {scan_duration:.2f}s | "
                f"files_scanned: {len(scanned_files)} | "
                f"projects: {len(delta)} | "
                f"delta: new={total_new}, changed={total_changed}, deleted={total_deleted}"
            )

            # Queue phase - batch DB operations
            queue_start = datetime.now()
            dir_stats = processor.queue_changes(watch_dir, delta)
            queue_end = datetime.now()
            queue_duration = (queue_end - queue_start).total_seconds()
            logger.info(
                f"[QUEUE END] Watch directory: {watch_dir} | "
                f"duration: {queue_duration:.2f}s | "
                f"new: {dir_stats.get('new_files', 0)} | "
                f"changed: {dir_stats.get('changed_files', 0)} | "
                f"deleted: {dir_stats.get('deleted_files', 0)}"
            )

            # Update current_project_id for each project being processed
            # delta keys are project_ids
            if delta:
                # Get the last project being processed (or first if only one)
                # In practice, we track the most recent project
                current_project_id = list(delta.keys())[-1] if delta else None
                if current_project_id:
                    # Update statistics with current project ID
                    # Note: cycle_id is available from _scan_cycle context
                    # We'll need to pass it or get it from database
                    try:
                        # Get current cycle_id from database
                        cycle_result = database.execute(
                            """
                            SELECT cycle_id FROM file_watcher_stats
                            WHERE cycle_end_time IS NULL
                            ORDER BY cycle_start_time DESC
                            LIMIT 1
                            """,
                            None,
                        )
                        cycle_rows = (
                            cycle_result.get("data", [])
                            if isinstance(cycle_result, dict)
                            else []
                        )
                        if cycle_rows:
                            cycle_id = cycle_rows[0].get("cycle_id")
                            database.execute(
                                """
                                UPDATE file_watcher_stats
                                SET current_project_id = ?, last_updated = julianday('now')
                                WHERE cycle_id = ?
                                """,
                                (current_project_id, cycle_id),
                            )
                    except Exception as e:
                        logger.debug(f"Could not update current_project_id: {e}")

            stats["scanned_dirs"] += 1
            stats["new_files"] += int(dir_stats.get("new_files", 0))
            stats["changed_files"] += int(dir_stats.get("changed_files", 0))
            stats["deleted_files"] += int(dir_stats.get("deleted_files", 0))
            stats["errors"] += int(dir_stats.get("errors", 0))

        except Exception as e:
            logger.error(
                f"Error scanning watch directory {watch_dir}: {e}",
                exc_info=True,
            )
            stats["errors"] += 1
        finally:
            # Release lock
            lock_manager.release_lock(watch_dir)

        return stats

    def _initialize_watch_dirs(self, database: Any) -> None:
        """
        Initialize watch directories from config.

        This method:
        1. Creates/updates watch_dirs entries for each spec
        2. Updates watch_dir_paths with absolute normalized paths
        3. Sets NULL paths for watch_dirs not found in config or on disk
        4. Discovers projects and creates/updates them with watch_dir_id

        Args:
            database: CodeDatabase instance
        """
        from ..path_normalization import normalize_path_simple
        from ..project_discovery import discover_projects_in_directory

        logger.info("Initializing watch directories...")

        # Step 1: Create/update watch_dirs and watch_dir_paths from specs
        config_watch_dir_ids = set()
        for spec in self.watch_dirs:
            watch_dir_id = spec.watch_dir_id
            watch_dir_path = spec.watch_dir.resolve()
            config_watch_dir_ids.add(watch_dir_id)

            # Create/update watch_dir entry
            database.execute(
                """
                INSERT OR REPLACE INTO watch_dirs (id, name, updated_at)
                VALUES (?, ?, julianday('now'))
                """,
                (watch_dir_id, watch_dir_path.name),
            )

            # Update watch_dir_paths
            if watch_dir_path.exists():
                normalized_path = normalize_path_simple(str(watch_dir_path))
                database.execute(
                    """
                    INSERT OR REPLACE INTO watch_dir_paths (watch_dir_id, path, updated_at)
                    VALUES (?, ?, julianday('now'))
                    """,
                    (watch_dir_id, normalized_path),
                )
                logger.debug(
                    f"Updated watch_dir_path: {watch_dir_id} -> {normalized_path}"
                )

                # Step 2: Discover projects in this watch_dir
                try:
                    discovered_projects = discover_projects_in_directory(watch_dir_path)
                    for project_root_obj in discovered_projects:
                        # Check if project exists
                        project_obj = database.get_project(project_root_obj.project_id)
                        if project_obj:
                            # Update watch_dir_id if needed
                            if (
                                getattr(project_obj, "watch_dir_id", None)
                                != watch_dir_id
                            ):
                                database.execute(
                                    """
                                    UPDATE projects 
                                    SET watch_dir_id = ?, updated_at = julianday('now')
                                    WHERE id = ?
                                    """,
                                    (watch_dir_id, project_root_obj.project_id),
                                )
                                logger.debug(
                                    f"Updated project {project_root_obj.project_id} "
                                    f"watch_dir_id to {watch_dir_id}"
                                )
                        else:
                            # Create new project
                            project_name = project_root_obj.root_path.name
                            database.execute(
                                """
                                INSERT INTO projects (id, root_path, name, comment, watch_dir_id, updated_at)
                                VALUES (?, ?, ?, ?, ?, julianday('now'))
                                """,
                                (
                                    project_root_obj.project_id,
                                    str(project_root_obj.root_path),
                                    project_name,
                                    project_root_obj.description,
                                    watch_dir_id,
                                ),
                            )
                            logger.info(
                                f"Created project {project_root_obj.project_id} "
                                f"at {project_root_obj.root_path} "
                                f"with watch_dir_id: {watch_dir_id}"
                            )
                except Exception as e:
                    logger.error(
                        f"Error discovering projects in {watch_dir_path}: {e}",
                        exc_info=True,
                    )
            else:
                # Path doesn't exist on disk - set NULL
                database.execute(
                    """
                    INSERT OR REPLACE INTO watch_dir_paths (watch_dir_id, path, updated_at)
                    VALUES (?, NULL, julianday('now'))
                    """,
                    (watch_dir_id,),
                )
                logger.warning(
                    f"Watch dir path does not exist: {watch_dir_path}, "
                    f"setting NULL for watch_dir_id: {watch_dir_id}"
                )

        # Step 3: Set NULL paths for watch_dirs in DB but not in config
        all_watch_dirs_result = database.execute(
            "SELECT id FROM watch_dirs",
            None,
        )
        all_watch_dirs_rows = (
            all_watch_dirs_result.get("data", [])
            if isinstance(all_watch_dirs_result, dict)
            else []
        )
        for db_watch_dir in all_watch_dirs_rows:
            db_watch_dir_id = db_watch_dir["id"]
            if db_watch_dir_id not in config_watch_dir_ids:
                # Not in config - set path to NULL
                database.execute(
                    """
                    INSERT OR REPLACE INTO watch_dir_paths (watch_dir_id, path, updated_at)
                    VALUES (?, NULL, julianday('now'))
                    """,
                    (db_watch_dir_id,),
                )
                logger.debug(
                    f"Watch dir {db_watch_dir_id} not in config, setting path to NULL"
                )

        logger.info("Watch directories initialization completed")


def build_watch_dir_specs(
    watch_dirs: Sequence[Dict[str, str]],
) -> List[WatchDirSpec]:
    """
    Build `WatchDirSpec` list from watch directory config.

    Args:
        watch_dirs: Sequence of watch directory configs with 'id' and 'path' keys.

    Returns:
        List of watch directory specs.
    """
    specs: List[WatchDirSpec] = []
    for watch_dir_config in watch_dirs:
        if isinstance(watch_dir_config, str):
            # Old format (should not happen, but handle gracefully)
            raise ValueError(
                "Old watch_dirs format (string array) is not supported. "
                "Use format: [{'id': 'uuid4', 'path': '/path'}]"
            )
        watch_dir_id = watch_dir_config["id"]
        watch_dir_path = watch_dir_config["path"]
        watch_path = Path(watch_dir_path).resolve()
        specs.append(WatchDirSpec(watch_dir=watch_path, watch_dir_id=watch_dir_id))
    return specs
