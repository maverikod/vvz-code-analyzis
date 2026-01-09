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
        
        # Also check projects from database that are in this watch_dir but their directories don't exist
        # This handles the case where a project directory was deleted but files remain in database
        try:
            root_dir_resolved = root_dir.resolve()
            # Get all projects from database
            all_projects = self.database._fetchall("SELECT id, root_path FROM projects")
            
            for project_row in all_projects:
                db_project_id = project_row["id"]
                db_root_path_str = project_row["root_path"]
                
                # Skip if already processed
                if db_project_id in deltas:
                    continue
                
                # Check if project root_path is within root_dir
                try:
                    db_root_path = Path(db_root_path_str).resolve()
                    # Check if root_path is within any watch_dir
                    is_in_watch_dir = False
                    for watch_dir in self.watch_dirs_resolved:
                        try:
                            db_root_path.relative_to(watch_dir)
                            is_in_watch_dir = True
                            break
                        except ValueError:
                            # Not in this watch_dir, continue
                            continue
                    
                    if not is_in_watch_dir:
                        continue
                    
                    # Check if project root directory exists
                    if not db_root_path.exists():
                        logger.info(
                            f"Project {db_project_id} root_path {db_root_path} does not exist, "
                            f"checking for deleted files"
                        )
                        
                        # Get all files for this project
                        db_files = self.database.get_project_files(
                            db_project_id, include_deleted=False
                        )
                        
                        if db_files:
                            # All files from this project should be marked as deleted
                            # since the project directory doesn't exist
                            deleted_files = [f["path"] for f in db_files]
                            logger.info(
                                f"Found {len(deleted_files)} files in database for deleted project "
                                f"{db_project_id}, marking as deleted"
                            )
                            
                            deltas[db_project_id] = FileDelta(
                                new_files=[],
                                changed_files=[],
                                deleted_files=deleted_files,
                            )
                except Exception as e:
                    logger.debug(
                        f"Error checking project {db_project_id} root_path {db_root_path_str}: {e}"
                    )
                    continue
        except Exception as e:
            logger.warning(
                f"Error checking database projects for deleted directories in {root_dir}: {e}"
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
                
                # Normalize root_dir - handle case where directory doesn't exist
                try:
                    normalized_root = str(normalize_root_dir(project_root))
                except (FileNotFoundError, NotADirectoryError):
                    # Project directory doesn't exist - use path as-is for dataset resolution
                    # This happens when project was deleted but files remain in database
                    normalized_root = str(project_root.resolve())
                
                # Resolve dataset_id
                dataset_id = self.dataset_id
                if not dataset_id:
                    # Try to get existing dataset_id first (works even if directory doesn't exist)
                    try:
                        dataset_id = self.database.get_dataset_id(
                            project_id, normalized_root
                        )
                    except (FileNotFoundError, NotADirectoryError):
                        # Directory doesn't exist - get dataset_id from any existing files
                        db_files = self.database.get_project_files(
                            project_id, include_deleted=False
                        )
                        if db_files:
                            # Get dataset_id from first file
                            dataset_id = db_files[0].get("dataset_id")
                    
                    if not dataset_id:
                        # Try to create dataset, but handle case where directory doesn't exist
                        try:
                            dataset_id = self.database.get_or_create_dataset(
                                project_id, normalized_root
                            )
                        except (FileNotFoundError, NotADirectoryError):
                            # Directory doesn't exist - get dataset_id from any existing files
                            # or use None (will be handled in _queue_project_delta)
                            db_files = self.database.get_project_files(
                                project_id, include_deleted=False
                            )
                            if db_files:
                                # Get dataset_id from first file
                                dataset_id = db_files[0].get("dataset_id")
                            if not dataset_id:
                                logger.warning(
                                    f"Cannot resolve dataset_id for project {project_id} "
                                    f"with non-existent root {normalized_root}, "
                                    "files may not be processed correctly"
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
                    project_id, delta, dataset_id, project_root
                )
                
                total_stats["new_files"] += project_stats["new_files"]
                total_stats["changed_files"] += project_stats["changed_files"]
                total_stats["deleted_files"] += project_stats["deleted_files"]
                total_stats["errors"] += project_stats["errors"]
                
            except Exception as e:
                logger.error(
                    f"Error queueing changes for project {project_id} in {root_dir}: {e}",
                    exc_info=True
                )
                total_stats["errors"] += (
                    len(delta.new_files)
                    + len(delta.changed_files)
                    + len(delta.deleted_files)
                )
        
        return total_stats
    
    def _queue_project_delta(
        self, project_id: str, delta: FileDelta, dataset_id: str, project_root: Path
    ) -> Dict[str, Any]:
        """
        Queue file changes for a single project.
        
        Args:
            project_id: Project ID
            delta: FileDelta for this project
            dataset_id: Dataset ID (already resolved)
            project_root: Project root directory
        
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
                    file_path_str, mtime, project_id, dataset_id, project_root
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
                    file_path_str, mtime, project_id, dataset_id, project_root
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
        self, file_path: str, mtime: float, project_id: str, dataset_id: str, project_root: Optional[Path] = None
    ) -> bool:
        """
        Queue file for processing.
        
        Updates all database records for a file after it was changed.
        This replaces the old mark_file_needs_chunking approach with
        unified update_file_data that ensures AST/CST/entities consistency.
        
        Args:
            file_path: File path (will be normalized to absolute)
            mtime: File modification time
            project_id: Project ID
            dataset_id: Dataset ID (already resolved)
            project_root: Project root directory (optional, will be resolved if not provided)
        
        Returns:
            True if successful, False otherwise
        """
        from ..project_resolution import normalize_abs_path
        
        try:
            # Normalize path to absolute once at the beginning
            # This ensures consistent path usage throughout the method
            abs_file_path = normalize_abs_path(file_path)
            
            # Get project root directory
            root_dir = project_root
            if not root_dir:
                root_dir = self._get_project_root_dir(project_id, abs_file_path)
                if not root_dir:
                    logger.warning(
                        f"Could not determine root_dir for {abs_file_path}, "
                        "falling back to mark_file_needs_chunking"
                    )
                    # Fallback to old behavior
                    result = self.database.mark_file_needs_chunking(abs_file_path, project_id)
                    if not result:
                        # New file: insert/update file record first
                        path_obj = Path(abs_file_path)
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
                                f"[QUEUE] Failed to read file for metadata, using defaults: {abs_file_path}"
                            )
                        
                        try:
                            self.database.add_file(
                                path=abs_file_path,
                                lines=lines,
                                last_modified=mtime,
                                has_docstring=has_docstring,
                                project_id=project_id,
                                dataset_id=dataset_id,
                            )
                        except Exception as e:
                            logger.error(
                                f"[QUEUE] Failed to add new file record: {abs_file_path} ({e})"
                            )
                            return False
                        
                        # Retry marking for chunking
                        result = self.database.mark_file_needs_chunking(
                            abs_file_path, project_id
                        )
                    return result
            
            # Check if file exists in database (using normalized path)
            # Normalize path consistently - ensure we use the same normalization everywhere
            # Path should be absolute and resolved (symlinks resolved, relative parts resolved)
            from ..project_resolution import normalize_abs_path as norm_path
            normalized_path = norm_path(abs_file_path)
            if normalized_path != abs_file_path:
                logger.debug(
                    f"[QUEUE] Path re-normalized: {abs_file_path} -> {normalized_path}"
                )
                abs_file_path = normalized_path
            
            # Verify that file path is within project root (safety check)
            if root_dir:
                try:
                    file_path_obj = Path(abs_file_path)
                    project_root_obj = Path(root_dir).resolve()
                    # Check if file is within project root
                    file_path_obj.relative_to(project_root_obj)
                    logger.debug(
                        f"[QUEUE] File path verified within project root: "
                        f"file={abs_file_path}, project_root={project_root_obj}"
                    )
                except ValueError:
                    logger.warning(
                        f"[QUEUE] File path is outside project root: "
                        f"file={abs_file_path}, project_root={root_dir}"
                    )
                    # Continue anyway - file might be in a different location
            
            file_record = self.database.get_file_by_path(abs_file_path, project_id)
            if not file_record:
                # New file: insert/update file record first
                path_obj = Path(abs_file_path)
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
                        f"[QUEUE] Failed to read file for metadata, using defaults: {abs_file_path}"
                    )
                
                try:
                    # Add file and get file_id (add_file returns file_id on success)
                    file_id = self.database.add_file(
                        path=abs_file_path,
                        lines=lines,
                        last_modified=mtime,
                        has_docstring=has_docstring,
                        project_id=project_id,
                        dataset_id=dataset_id,
                    )
                    logger.debug(
                        f"[QUEUE] File added to database: {abs_file_path} | "
                        f"file_id={file_id} | project_id={project_id} | dataset_id={dataset_id}"
                    )
                    
                    # Verify file was added successfully by checking file_id
                    # Use get_file_by_id instead of get_file_by_path to avoid path normalization issues
                    file_record = self.database.get_file_by_id(file_id)
                    if not file_record:
                        logger.error(
                            f"[QUEUE] File was added (file_id={file_id}) but not found in database: {abs_file_path}. "
                            "This may indicate a transaction issue."
                        )
                        # Try to get by path as fallback for debugging
                        file_record_by_path = self.database.get_file_by_path(abs_file_path, project_id)
                        if file_record_by_path:
                            logger.warning(
                                f"[QUEUE] File found by path but not by id: file_id={file_id}, "
                                f"found_file_id={file_record_by_path.get('id')}, path={abs_file_path}"
                            )
                            file_record = file_record_by_path
                        else:
                            # Log detailed debug info
                            logger.error(
                                f"[QUEUE] File not found by path either. "
                                f"Normalized path: {abs_file_path}, project_id: {project_id}"
                            )
                            return False
                    else:
                        logger.debug(
                            f"[QUEUE] File verified in database: file_id={file_id}, "
                            f"path={file_record.get('path')}, project_id={file_record.get('project_id')}"
                        )
                except Exception as e:
                    logger.error(
                        f"[QUEUE] Failed to add new file record: {abs_file_path} ({e})",
                        exc_info=True
                    )
                    return False
            
            # Update all database records for changed file (using normalized path)
            # Use file_id if available to avoid path lookup issues
            if file_record and file_record.get("id"):
                # File already exists - use file_id for update
                # But update_file_data requires path, so we still pass it
                # However, we ensure the path is correctly normalized
                logger.debug(
                    f"[QUEUE] Updating file data: file_id={file_record.get('id')}, "
                    f"path={abs_file_path}, project_id={project_id}"
                )
            
            update_result = self.database.update_file_data(
                file_path=abs_file_path,
                project_id=project_id,
                root_dir=root_dir,
            )
            
            if update_result.get("success"):
                logger.debug(
                    f"[QUEUE] File updated in database: {abs_file_path} | "
                    f"AST={update_result.get('ast_updated')}, "
                    f"CST={update_result.get('cst_updated')}"
                )
                
                # Mark for chunking (vectorization worker will process)
                # Note: Immediate vectorization is not done here because this is sync context
                # Worker will handle vectorization in background
                self.database.mark_file_needs_chunking(abs_file_path, project_id)
                logger.debug(f"[QUEUE] File marked for worker vectorization: {abs_file_path}")
                
                return True
            else:
                logger.error(
                    f"[QUEUE] Failed to update file in database: {abs_file_path} | "
                    f"Error: {update_result.get('error')}"
                )
                return False
        except Exception as e:
            logger.error(
                f"[QUEUE] ✗ Error queueing file for processing {file_path}: {e}",
                exc_info=True,
            )
            return False
    
    def _get_project_root_dir(self, project_id: str, file_path: str) -> Optional[Path]:
        """
        Get project root directory for a file.
        
        Args:
            project_id: Project ID
            file_path: File path (absolute)
            
        Returns:
            Project root directory or None if not found
        """
        try:
            # Get project record
            project = self.database.get_project(project_id)
            if project and project.get("root_path"):
                return Path(project["root_path"])
            
            # Fallback: try to find root from watch_dirs
            abs_path = Path(file_path).resolve()
            for watch_dir in self.watch_dirs_resolved:
                try:
                    abs_path.relative_to(watch_dir)
                    return watch_dir
                except ValueError:
                    continue
            
            return None
        except Exception as e:
            logger.error(f"Error getting project root dir: {e}", exc_info=True)
            return None

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

