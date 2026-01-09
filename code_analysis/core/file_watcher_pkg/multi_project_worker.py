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
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
    """

    watch_dir: Path


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

        from ..database import CodeDatabase
        from ..database.base import create_driver_config_for_worker

        driver_config = create_driver_config_for_worker(self.db_path)

        database: Any = None
        # Processors are created dynamically per discovered project

        # Track database availability status
        db_available = False
        db_status_logged = False  # Track if we've logged the current status

        backoff = 1.0
        backoff_max = 60.0

        try:
            while not self._stop_event.is_set():
                if database is None:
                    try:
                        database = CodeDatabase(driver_config=driver_config)
                        # Test connection with a simple query
                        try:
                            # Try to get a project to test connection
                            database._execute("SELECT 1", ())
                            # Connection successful
                            if not db_available:
                                # Status changed: unavailable -> available
                                logger.info("✅ Database is now available")
                                db_available = True
                                db_status_logged = True
                                backoff = 1.0  # Reset backoff
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
                                database.close()
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
                        database.close()
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
                    database.close()
            except Exception:
                pass

        return total_stats

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

        for spec in self.watch_dirs:
            if self._stop_event.is_set():
                break

            watch_dir_stats = self._scan_watch_dir(spec, processor, database)
            cycle_stats["scanned_dirs"] += watch_dir_stats.get("scanned_dirs", 0)
            cycle_stats["new_files"] += watch_dir_stats.get("new_files", 0)
            cycle_stats["changed_files"] += watch_dir_stats.get("changed_files", 0)
            cycle_stats["deleted_files"] += watch_dir_stats.get("deleted_files", 0)
            cycle_stats["errors"] += watch_dir_stats.get("errors", 0)

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
                    project = database.get_project(project_root_obj.project_id)
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
                        # Project exists with correct root_path - update description if changed
                        current_comment = project.get("comment")
                        if current_comment != project_root_obj.description:
                            database._execute(
                                """
                                UPDATE projects 
                                SET comment = ?, updated_at = julianday('now')
                                WHERE id = ?
                                """,
                                (
                                    project_root_obj.description,
                                    project_root_obj.project_id,
                                ),
                            )
                            database._commit()
                            logger.debug(
                                f"Updated description for project {project_root_obj.project_id}: "
                                f"{current_comment} -> {project_root_obj.description}"
                            )
                    else:
                        # Check if project exists with different ID (by root_path)
                        existing_project_id = database.get_project_id(
                            str(project_root_obj.root_path)
                        )
                        if existing_project_id:
                            if existing_project_id != project_root_obj.project_id:
                                logger.warning(
                                    f"Project at {project_root_obj.root_path} exists with "
                                    f"different ID ({existing_project_id}) than projectid file "
                                    f"({project_root_obj.project_id}), updating"
                                )
                                # Update project ID and description to match projectid file
                                database._execute(
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
                                database._commit()
                            # Project exists with correct ID
                        else:
                            # Check if project_id is used by another root_path
                            existing_project = database.get_project(
                                project_root_obj.project_id
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
                            database._execute(
                                """
                                INSERT INTO projects (id, root_path, name, comment, updated_at)
                                VALUES (?, ?, ?, ?, julianday('now'))
                                """,
                                (
                                    project_root_obj.project_id,
                                    str(project_root_obj.root_path),
                                    project_name,
                                    project_description,
                                ),
                            )
                            database._commit()
                            logger.info(
                                f"Auto-created project {project_root_obj.project_id} "
                                f"at {project_root_obj.root_path} "
                                f"with description: {project_description}"
                            )
                except Exception as e:
                    logger.warning(
                        f"Failed to get/create project {project_root_obj.project_id}: {e}"
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


def build_watch_dir_specs(
    watch_dirs: Sequence[str],
) -> List[WatchDirSpec]:
    """
    Build `WatchDirSpec` list from watch directory paths.

    Args:
        watch_dirs: Sequence of watch directory paths.

    Returns:
        List of watch directory specs.
    """
    specs: List[WatchDirSpec] = []
    for watch_dir in watch_dirs:
        watch_path = Path(watch_dir).resolve()
        specs.append(WatchDirSpec(watch_dir=watch_path))
    return specs
