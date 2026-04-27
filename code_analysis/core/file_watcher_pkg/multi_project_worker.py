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
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from ..project_ignore_policy import filter_ignore_exception_py_paths_for_watcher
from ..venv_path_policy import (
    allowed_venv_py_files_for_watch_dir,
    build_ignore_exception_files_for_projects,
    load_ignore_exceptions_from_config,
    load_ignore_exceptions_from_config_path,
)
from .multi_project_worker_cycle import run_scan_cycle
from .multi_project_worker_init import initialize_watch_dirs
from .multi_project_worker_specs import WatchDirSpec, build_watch_dir_specs
from .processor import FileChangeProcessor
from .scanner import scan_directory

logger = logging.getLogger(__name__)

__all__ = ["MultiProjectFileWatcherWorker", "WatchDirSpec", "build_watch_dir_specs"]


class MultiProjectFileWatcherWorker:
    """
    Single-process file watcher that iterates over multiple projects.

    Responsibilities:
    - Establish a DB connection from config (``create_worker_database_client``):
      PostgreSQL in-process or SQLite RPC to an already running driver (never spawns DB worker).
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
        status_file_path: Optional[Path] = None,
        config_path: Optional[str] = None,
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
            status_file_path: Optional path to write current_operation/current_file for monitoring.
        """
        self.db_path = db_path
        self.watch_dirs = list(watch_dirs)
        self.scan_interval = int(scan_interval)
        self.locks_dir = Path(locks_dir).resolve()
        self.version_dir = version_dir
        self.ignore_patterns = ignore_patterns or []
        self.status_file_path = Path(status_file_path) if status_file_path else None
        self.config_path = config_path

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

        from ..database_client.factory import create_worker_database_client

        _cfg_raw = getattr(self, "config_path", None)
        cfg_path = Path(_cfg_raw) if _cfg_raw else None
        if cfg_path is None:
            logger.error(
                "Multi-project file watcher requires config_path (server config.json) "
                "so the database is opened via code_analysis.database.driver."
            )
            return {
                **total_stats,
                "errors": max(1, total_stats.get("errors", 0)),
            }

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
                        database = create_worker_database_client(
                            config_path=cfg_path,
                        )
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

                            # Initialize watch_dirs on first connection (always, not just when db becomes available)
                            if not watch_dirs_initialized:
                                try:
                                    logger.info("Initializing watch directories...")
                                    self._initialize_watch_dirs(database)
                                    watch_dirs_initialized = True
                                    logger.info(
                                        "Watch directories initialization completed"
                                    )
                                except Exception as init_e:
                                    logger.error(
                                        f"Failed to initialize watch_dirs: {init_e}",
                                        exc_info=True,
                                    )
                                    # Avoid tight CPU loop if the next scan fails fast;
                                    # init retries only after DB reconnect.
                                    pause = min(5.0, float(self.scan_interval or 60))
                                    await asyncio.sleep(pause)
                                    # Continue anyway - will retry on next reconnect
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
                # Ignore policy is defined per watch_dir, not from file_watcher section.
                merged_ignore = list(spec.ignore_patterns)
                allowed_venv = allowed_venv_py_files_for_watch_dir(watch_dir)
                if self.config_path:
                    exc_patterns = load_ignore_exceptions_from_config_path(
                        Path(self.config_path)
                    )
                else:
                    exc_patterns = load_ignore_exceptions_from_config()
                from ..project_discovery import (
                    DuplicateProjectIdError,
                    NestedProjectError,
                    discover_projects_in_directory,
                )

                try:
                    discovered = discover_projects_in_directory(watch_dir)
                except (
                    NestedProjectError,
                    DuplicateProjectIdError,
                    OSError,
                    ValueError,
                ):
                    discovered = []
                exc_files_raw: Set[Path] = set()
                if exc_patterns:
                    exc_files_raw = build_ignore_exception_files_for_projects(
                        [Path(p.root_path) for p in discovered],
                        list(exc_patterns),
                    )
                exc_files_filtered = filter_ignore_exception_py_paths_for_watcher(
                    exc_files_raw,
                    [Path(p.root_path) for p in discovered],
                    allowed_venv or None,
                )
                immediate_roots = {Path(p.root_path).resolve() for p in discovered}
                scanned_files = scan_directory(
                    root_dir=watch_dir,
                    watch_dirs=[spec.watch_dir],
                    ignore_patterns=merged_ignore,
                    allowed_venv_py_files=allowed_venv or None,
                    ignore_exception_files=exc_files_filtered or None,
                    ignore_exception_patterns=exc_patterns or None,
                    immediate_project_roots=immediate_roots,
                )
                total_files += len(scanned_files)
            except Exception as e:
                logger.debug(f"Error counting files in {watch_dir}: {e}")
                continue

        return total_files

    async def _scan_cycle(self, database: Any, processors: Any) -> Dict[str, Any]:
        """Perform one scan cycle for all watched directories (delegate to cycle module)."""
        return await run_scan_cycle(self, database, processors)

    def _initialize_watch_dirs(self, database: Any) -> None:
        """Initialize watch directories from config (delegate to init module)."""
        initialize_watch_dirs(database, self.watch_dirs)
