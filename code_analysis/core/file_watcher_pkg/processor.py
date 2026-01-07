"""
File change processor for file watcher worker.

Implements Step 3 of refactor plan: scan → queue → process phases.
- Scan phase: compute delta (new/changed/deleted files) without DB operations
- Queue phase: batch DB operations for all changes
- Process phase: downstream workers consume queued items

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .scanner import find_missing_files

logger = logging.getLogger(__name__)


@dataclass
class FileDelta:
    """
    File change delta computed during scan phase.

    Attributes:
        new_files: List of (file_path, mtime, size) tuples for new files
        changed_files: List of (file_path, mtime, size) tuples for changed files
        deleted_files: List of file_path strings for deleted files
    """

    new_files: List[tuple[str, float, int]]
    changed_files: List[tuple[str, float, int]]
    deleted_files: List[str]


class FileChangeProcessor:
    """
    Processes file changes with separated scan → queue → process phases.

    Implements Step 3 of refactor plan:
    - compute_delta: Scan phase - compute delta without DB operations
    - queue_changes: Queue phase - batch DB operations
    - Process phase: handled by downstream workers
    
    Always works in multi-project mode: discovers projects automatically
    within watched directories.
    """

    def __init__(
        self,
        database: Any,
        watch_dirs: List[Path],
        version_dir: Optional[str] = None,
        dataset_id: Optional[str] = None,
    ) -> None:
        """
        Initialize file change processor.

        Implements dataset-scoped file processing (Step 2 of refactor plan).
        If dataset_id is provided, processes files only for that dataset.
        If dataset_id is None, resolves dataset_id from root_dir when processing.

        Args:
            database: CodeDatabase instance
            watch_dirs: List of watched directories for project discovery (REQUIRED)
            version_dir: Version directory for deleted files (optional)
            dataset_id: Optional dataset ID (if None, will be resolved from root_dir)
        """
        self.database = database
        self.watch_dirs = watch_dirs
        self.version_dir = version_dir
        self.dataset_id = dataset_id
        self.watch_dirs_resolved = [Path(wd).resolve() for wd in watch_dirs]

    def compute_delta(
        self, root_dir: Path, scanned_files: Dict[str, Dict]
    ) -> Dict[str, FileDelta]:
        """
        Compute file change delta for multiple projects (SCAN PHASE - no DB operations).
        
        Groups files by project_id and computes delta for each project separately.
        
        Args:
            root_dir: Root watched directory (will be normalized to absolute)
            scanned_files: Files found on disk (from scanner). Files must have
                          "project_id" and "project_root" in file_info.
        
        Returns:
            Dictionary mapping project_id to FileDelta
        """
        from ..project_resolution import normalize_root_dir
        
        # Group files by project_id
        files_by_project: Dict[str, Dict[str, Dict]] = defaultdict(dict)
        project_roots: Dict[str, Path] = {}
        
        for file_path_str, file_info in scanned_files.items():
            project_id = file_info.get("project_id")
            if not project_id:
                logger.warning(
                    f"File {file_path_str} has no project_id, skipping"
                )
                continue
            files_by_project[project_id][file_path_str] = file_info
            if project_id not in project_roots:
                project_root = file_info.get("project_root")
                if project_root:
                    project_roots[project_id] = Path(project_root)
        
        # Compute delta for each project
        deltas: Dict[str, FileDelta] = {}
        
        for project_id, project_files in files_by_project.items():
            project_root = project_roots.get(project_id)
            if not project_root:
                logger.warning(
                    f"Project {project_id} has no project_root, skipping"
                )
                continue
            
            new_files: List[tuple[str, float, int]] = []
            changed_files: List[tuple[str, float, int]] = []
            
            try:
                # Resolve dataset_id from project_root
                normalized_root = str(normalize_root_dir(project_root))
                dataset_id = self.dataset_id
                if not dataset_id:
                    dataset_id = self.database.get_dataset_id(
                        project_id, normalized_root
                    )
                    if not dataset_id:
                        # Create dataset if it doesn't exist
                        dataset_id = self.database.get_or_create_dataset(
                            project_id, normalized_root
                        )
                        logger.info(
                            f"Created dataset {dataset_id} for project {project_id} root {normalized_root}"
                        )
                
                # Get files from database for this project and dataset (read-only)
                db_files = self.database.get_project_files(
                    project_id, include_deleted=False
                )
                # Filter by dataset_id
                db_files = [f for f in db_files if f.get("dataset_id") == dataset_id]
                
                # Create mapping of path -> file record
                db_files_map = {f["path"]: f for f in db_files}
                
                # Compute delta for new and changed files (no DB writes)
                for file_path_str, file_info in project_files.items():
                    try:
                        mtime = file_info["mtime"]
                        size = file_info.get("size", 0)
                        
                        # Check if file is in database
                        db_file = db_files_map.get(file_path_str)
                        
                        if not db_file:
                            # New file
                            new_files.append((file_path_str, mtime, size))
                        else:
                            # Existing file - check if changed
                            db_mtime = db_file.get("last_modified")
                            if db_mtime is None or abs(mtime - db_mtime) > 0.1:
                                # File changed (tolerance 0.1 seconds for filesystem precision)
                                changed_files.append((file_path_str, mtime, size))
                    
                    except Exception as e:
                        logger.error(f"Error computing delta for file {file_path_str}: {e}")
                
                # Find missing files (in DB but not on disk)
                deleted_files = list(find_missing_files(project_files, db_files))
                
                deltas[project_id] = FileDelta(
                    new_files=new_files,
                    changed_files=changed_files,
                    deleted_files=deleted_files,
                )
                
            except Exception as e:
                logger.error(
                    f"Error computing delta for project {project_id} in {root_dir}: {e}"
                )
                # Return empty delta on error
                deltas[project_id] = FileDelta(
                    new_files=[], changed_files=[], deleted_files=[]
                )
        
        return deltas

    def queue_changes(
        self, root_dir: Path, deltas: Dict[str, FileDelta]
    ) -> Dict[str, Any]:
        """
        Queue file changes for multiple projects (QUEUE PHASE - batch DB operations).
        
        Processes each project's delta separately and aggregates statistics.
        
        Args:
            root_dir: Root watched directory (will be normalized to absolute)
            deltas: Dictionary mapping project_id to FileDelta
        
        Returns:
            Aggregated statistics across all projects
        """
        from ..project_resolution import normalize_root_dir
        
        total_stats = {
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }
        
        # Process each project's delta
        for project_id, delta in deltas.items():
            try:
                # Get project from database, or create if not exists
                project = self.database.get_project(project_id)
                if not project:
                    # Project not found - this should not happen if discovery worked correctly
                    # But we'll try to find project_root from discovered projects
                    # For now, log error and skip
                    logger.error(
                        f"[QUEUE] Project {project_id} not found in database. "
                        "Project should be created during discovery. Skipping."
                    )
                    total_stats["errors"] += (
                        len(delta.new_files)
                        + len(delta.changed_files)
                        + len(delta.deleted_files)
                    )
                    continue
                
                project_root = Path(project["root_path"])
                normalized_root = str(normalize_root_dir(project_root))
                
                # Resolve dataset_id
                dataset_id = self.dataset_id
                if not dataset_id:
                    dataset_id = self.database.get_dataset_id(
                        project_id, normalized_root
                    )
                    if not dataset_id:
                        dataset_id = self.database.get_or_create_dataset(
                            project_id, normalized_root
                        )
                
                if not dataset_id:
                    logger.error(
                        f"[QUEUE] Cannot determine dataset_id for project {project_id} root {root_dir}"
                    )
                    total_stats["errors"] += (
                        len(delta.new_files)
                        + len(delta.changed_files)
                        + len(delta.deleted_files)
                    )
                    continue
                
                # Process files for this project (reuse existing logic)
                project_stats = self._queue_project_delta(
                    project_id, delta, dataset_id
                )
                
                total_stats["new_files"] += project_stats["new_files"]
                total_stats["changed_files"] += project_stats["changed_files"]
                total_stats["deleted_files"] += project_stats["deleted_files"]
                total_stats["errors"] += project_stats["errors"]
                
            except Exception as e:
                logger.error(
                    f"Error queueing changes for project {project_id} in {root_dir}: {e}"
                )
                total_stats["errors"] += (
                    len(delta.new_files)
                    + len(delta.changed_files)
                    + len(delta.deleted_files)
                )
        
        return total_stats
    
    def _queue_project_delta(
        self, project_id: str, delta: FileDelta, dataset_id: str
    ) -> Dict[str, Any]:
        """
        Queue file changes for a single project.
        
        Args:
            project_id: Project ID
            delta: FileDelta for this project
            dataset_id: Dataset ID (already resolved)
        
        Returns:
            Statistics for this project
        """
        stats = {
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }
        
        # Batch process new files
        for file_path_str, mtime, size in delta.new_files:
            try:
                mtime_str = datetime.fromtimestamp(mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                logger.info(
                    f"[project={project_id}] [NEW FILE] {file_path_str} | "
                    f"mtime: {mtime_str} ({mtime}) | "
                    f"size: {size} bytes"
                )
                if self._queue_file_for_processing(
                    file_path_str, mtime, project_id, dataset_id
                ):
                    stats["new_files"] += 1
                    logger.info(
                        f"[project={project_id}] [NEW FILE] ✓ Queued for processing: {file_path_str}"
                    )
                else:
                    stats["errors"] += 1
                    logger.error(
                        f"[project={project_id}] [NEW FILE] ✗ Failed to queue: {file_path_str}"
                    )
            except Exception as e:
                logger.error(
                    f"[project={project_id}] Error queueing new file {file_path_str}: {e}"
                )
                stats["errors"] += 1
        
        # Batch process changed files
        for file_path_str, mtime, size in delta.changed_files:
            try:
                mtime_str = datetime.fromtimestamp(mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                logger.info(
                    f"[project={project_id}] [CHANGED FILE] {file_path_str} | "
                    f"mtime: {mtime_str} ({mtime}) | "
                    f"size: {size} bytes"
                )
                if self._queue_file_for_processing(
                    file_path_str, mtime, project_id, dataset_id
                ):
                    stats["changed_files"] += 1
                    logger.info(
                        f"[project={project_id}] [CHANGED FILE] ✓ Queued for processing: {file_path_str}"
                    )
                else:
                    stats["errors"] += 1
                    logger.error(
                        f"[project={project_id}] [CHANGED FILE] ✗ Failed to queue: {file_path_str}"
                    )
            except Exception as e:
                logger.error(
                    f"[project={project_id}] Error queueing changed file {file_path_str}: {e}"
                )
                stats["errors"] += 1
        
        # Batch process deleted files
        for file_path_str in delta.deleted_files:
            try:
                logger.info(
                    f"[project={project_id}] [DELETED FILE] {file_path_str} | action: soft_delete"
                )
                if self.version_dir:
                    if self.database.mark_file_deleted(
                        file_path_str, project_id, self.version_dir
                    ):
                        stats["deleted_files"] += 1
                        logger.info(
                            f"[project={project_id}] [DELETED FILE] ✓ Marked as deleted: {file_path_str}"
                        )
                    else:
                        stats["errors"] += 1
                        logger.error(
                            f"[project={project_id}] [DELETED FILE] ✗ Failed to mark as deleted: {file_path_str}"
                        )
                else:
                    logger.warning(
                        f"[project={project_id}] [DELETED FILE] ✗ version_dir not configured, cannot mark {file_path_str} as deleted"
                    )
                    stats["errors"] += 1
            except Exception as e:
                logger.error(
                    f"[project={project_id}] [DELETED FILE] ✗ Error marking file as deleted {file_path_str}: {e}"
                )
                stats["errors"] += 1
        
        return stats
    
    def _queue_file_for_processing(
        self, file_path: str, mtime: float, project_id: str, dataset_id: str
    ) -> bool:
        """
        Queue file for processing.
        
        Args:
            file_path: File path (will be normalized to absolute)
            mtime: File modification time
            project_id: Project ID
            dataset_id: Dataset ID (already resolved)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Mark file for chunking
            result = self.database.mark_file_needs_chunking(file_path, project_id)
            if not result:
                # New file: insert/update file record first
                path_obj = Path(file_path)
                lines = 0
                has_docstring = False
                try:
                    if path_obj.exists() and path_obj.is_file():
                        text = path_obj.read_text(encoding="utf-8", errors="ignore")
                        lines = text.count("\n") + (1 if text else 0)
                        stripped = text.lstrip()
                        has_docstring = stripped.startswith(
                            '"""'
                        ) or stripped.startswith("'''")
                except Exception:
                    logger.debug(
                        f"[QUEUE] Failed to read file for metadata, using defaults: {file_path}"
                    )
                
                try:
                    self.database.add_file(
                        path=file_path,
                        lines=lines,
                        last_modified=mtime,
                        has_docstring=has_docstring,
                        project_id=project_id,
                        dataset_id=dataset_id,
                    )
                except Exception as e:
                    logger.error(
                        f"[QUEUE] Failed to add new file record: {file_path} ({e})"
                    )
                    return False
                
                # Retry marking for chunking
                result = self.database.mark_file_needs_chunking(
                    file_path, project_id
                )
            
            if result:
                # Update last_modified if file exists
                self.database._execute(
                    """
                    UPDATE files 
                    SET last_modified = ?, updated_at = julianday('now')
                    WHERE project_id = ? AND path = ?
                    """,
                    (mtime, project_id, file_path),
                )
                self.database._commit()
                logger.debug(
                    f"[QUEUE] File queued for chunking: {file_path} | "
                    f"mtime updated to: {datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')}"
                )
            return result
        except Exception as e:
            logger.error(
                f"[QUEUE] ✗ Error queueing file for processing {file_path}: {e}"
            )
            return False

    def process_changes(
        self, root_dir: Path, scanned_files: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """
        Process file changes (combines scan and queue).

        This method combines compute_delta + queue_changes to implement scan → queue phases.

        Args:
            root_dir: Root watched directory (will be normalized to absolute)
            scanned_files: Files found on disk (from scanner)

        Returns:
            Dictionary with processing statistics
        """
        # Step 3: Separate scan and queue phases
        delta = self.compute_delta(root_dir, scanned_files)
        return self.queue_changes(root_dir, delta)

