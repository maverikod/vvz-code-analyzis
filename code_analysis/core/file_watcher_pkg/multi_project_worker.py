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
class ProjectWatchSpec:
    """
    Project watch specification.

    Attributes:
        project_id: Database project id used for scoping DB operations.
        watch_dirs: Root directories to scan (lock file is created in each root).
        project_root: Root directory used to compute relative paths (optional).
    """

    project_id: str
    watch_dirs: Tuple[Path, ...]
    project_root: Optional[Path]


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
        projects: Sequence[ProjectWatchSpec],
        scan_interval: int = 60,
        lock_file_name: str = ".file_watcher.lock",
        version_dir: Optional[str] = None,
        ignore_patterns: Optional[List[str]] = None,
    ) -> None:
        """
        Initialize multi-project file watcher.

        Args:
            db_path: Path to SQLite database file.
            projects: Projects to scan (project_id + dirs).
            scan_interval: Delay between cycles in seconds.
            lock_file_name: Lock file name created in each root watch_dir.
            version_dir: Version directory for deleted files (optional).
            ignore_patterns: Glob patterns to ignore (optional).
        """
        self.db_path = db_path
        self.projects = list(projects)
        self.scan_interval = int(scan_interval)
        self.lock_manager = LockManager(lock_file_name)
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
            "projects": len(self.projects),
        }

        logger.info(
            "Starting multi-project file watcher worker | "
            f"pid={self._pid} | projects={len(self.projects)} | "
            f"scan_interval={self.scan_interval}s"
        )

        from ..database import CodeDatabase, create_driver_config_for_worker

        driver_config = create_driver_config_for_worker(self.db_path)

        database: Any = None
        processors: Dict[str, FileChangeProcessor] = {}

        backoff = 1.0
        backoff_max = 60.0

        try:
            while not self._stop_event.is_set():
                if database is None:
                    try:
                        database = CodeDatabase(driver_config=driver_config)
                        processors = {
                            spec.project_id: FileChangeProcessor(
                                database=database,
                                project_id=spec.project_id,
                                version_dir=self.version_dir,
                            )
                            for spec in self.projects
                        }
                        backoff = 1.0
                    except Exception as e:
                        total_stats["errors"] += 1
                        logger.warning(
                            f"DB worker unavailable; retrying in {backoff:.1f}s: {e}"
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2.0, backoff_max)
                        continue

                try:
                    cycle_stats = await self._scan_cycle(database, processors)
                except Exception as e:
                    total_stats["errors"] += 1
                    logger.error(
                        f"File watcher cycle failed (will retry after reconnect): {e}",
                        exc_info=True,
                    )
                    try:
                        database.close()
                    except Exception:
                        pass
                    database = None
                    processors = {}
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
                    f"projects: {len(self.projects)} | "
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

    async def _scan_cycle(
        self, database: Any, processors: Dict[str, FileChangeProcessor]
    ) -> Dict[str, Any]:
        """
        Perform one scan cycle for all configured projects.

        Args:
            database: CodeDatabase instance.
            processors: Mapping project_id -> FileChangeProcessor.

        Returns:
            Dictionary with cycle statistics.
        """
        _ = database  # kept for symmetry with single-project worker API
        cycle_stats: Dict[str, Any] = {
            "scanned_dirs": 0,
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }

        for spec in self.projects:
            if self._stop_event.is_set():
                break
            processor = processors.get(spec.project_id)
            if processor is None:
                cycle_stats["errors"] += 1
                logger.error(
                    f"[project={spec.project_id}] Missing processor, skipping project"
                )
                continue

            project_stats = self._scan_project(spec, processor)
            cycle_stats["scanned_dirs"] += project_stats.get("scanned_dirs", 0)
            cycle_stats["new_files"] += project_stats.get("new_files", 0)
            cycle_stats["changed_files"] += project_stats.get("changed_files", 0)
            cycle_stats["deleted_files"] += project_stats.get("deleted_files", 0)
            cycle_stats["errors"] += project_stats.get("errors", 0)

        return cycle_stats

    def _scan_project(
        self, spec: ProjectWatchSpec, processor: FileChangeProcessor
    ) -> Dict[str, Any]:
        """
        Scan all root directories for a single project.

        Args:
            spec: Project watch specification.
            processor: FileChangeProcessor bound to `spec.project_id`.

        Returns:
            Per-project scan stats.
        """
        stats: Dict[str, Any] = {
            "scanned_dirs": 0,
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }

        for root_dir in spec.watch_dirs:
            if self._stop_event.is_set():
                break

            if not root_dir.exists():
                logger.warning(
                    f"[project={spec.project_id}] Watched directory does not exist: {root_dir}"
                )
                continue

            if not self.lock_manager.acquire_lock(root_dir, self._pid):
                logger.warning(
                    f"[project={spec.project_id}] Could not acquire lock for {root_dir}, skipping"
                )
                stats["errors"] += 1
                continue

            try:
                from datetime import datetime

                scan_start = datetime.now()
                logger.info(
                    f"[project={spec.project_id}] [SCAN START] Directory: {root_dir} | "
                    f"time: {scan_start.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                scanned_files = scan_directory(
                    root_dir=root_dir,
                    project_root=spec.project_root,
                    ignore_patterns=self.ignore_patterns,
                )

                dir_stats = processor.process_changes(root_dir, scanned_files)

                scan_end = datetime.now()
                duration = (scan_end - scan_start).total_seconds()
                logger.info(
                    f"[project={spec.project_id}] [SCAN END] Directory: {root_dir} | "
                    f"time: {scan_end.strftime('%Y-%m-%d %H:%M:%S')} | "
                    f"duration: {duration:.2f}s | "
                    f"files_scanned: {len(scanned_files)} | "
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
                    f"[project={spec.project_id}] Error scanning directory {root_dir}: {e}",
                    exc_info=True,
                )
                stats["errors"] += 1
            finally:
                self.lock_manager.release_lock(root_dir)

        return stats


def build_project_specs(
    project_watch_dirs: Sequence[Tuple[str, str]],
) -> List[ProjectWatchSpec]:
    """
    Build `ProjectWatchSpec` list from `(project_id, watch_dir)` tuples.

    Args:
        project_watch_dirs: Sequence of (project_id, watch_dir).

    Returns:
        List of project specs (one directory per project).
    """
    specs: List[ProjectWatchSpec] = []
    for project_id, watch_dir in project_watch_dirs:
        watch_path = Path(watch_dir).resolve()
        specs.append(
            ProjectWatchSpec(
                project_id=str(project_id),
                watch_dirs=(watch_path,),
                project_root=watch_path,
            )
        )
    return specs
