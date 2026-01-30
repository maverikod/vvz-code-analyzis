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
    ) -> None:
        """
        Initialize file change processor.

        Args:
            database: CodeDatabase instance
            watch_dirs: List of watched directories for project discovery (REQUIRED)
            version_dir: Version directory for deleted files (optional)
        """
        self.database = database
        self.watch_dirs = watch_dirs
        self.version_dir = version_dir
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
        # Group files by project_id
        files_by_project: Dict[str, Dict[str, Dict]] = defaultdict(dict)
        project_roots: Dict[str, Path] = {}

        for file_path_str, file_info in scanned_files.items():
            project_id = file_info.get("project_id")
            if not project_id:
                logger.warning(f"File {file_path_str} has no project_id, skipping")
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
                logger.warning(f"Project {project_id} has no project_root, skipping")
                continue

            new_files: List[tuple[str, float, int]] = []
            changed_files: List[tuple[str, float, int]] = []

            try:
                # Get files from database for this project (read-only)
                db_files_list = self.database.get_project_files(
                    project_id, include_deleted=False
                )
                # Convert File objects to dict format
                db_files = [
                    {
                        "id": f.id,
                        "path": f.path,
                        "last_modified": f.last_modified,
                    }
                    for f in db_files_list
                ]

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
                            if db_mtime is not None and hasattr(db_mtime, "timestamp"):
                                db_mtime = db_mtime.timestamp()
                            if db_mtime is None or abs(mtime - float(db_mtime)) > 0.1:
                                # File changed (tolerance 0.1 seconds for filesystem precision)
                                changed_files.append((file_path_str, mtime, size))

                    except Exception as e:
                        logger.error(
                            f"Error computing delta for file {file_path_str}: {e}"
                        )

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
            # Get all projects from database (DatabaseClient has select(), not _fetchall)
            if hasattr(self.database, "select"):
                all_projects = (
                    self.database.select("projects", columns=["id", "root_path"]) or []
                )
            else:
                all_projects = (
                    self.database.execute("SELECT id, root_path FROM projects").get(
                        "data"
                    )
                    or []
                )
            if not isinstance(all_projects, list):
                all_projects = []

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
                        logger.warning(
                            f"Project {db_project_id} root_path {db_root_path} does not exist. "
                            f"This may be temporary (e.g., during project reupload). "
                            f"Skipping automatic deletion to prevent data loss. "
                            f"Files will be checked again in next scan cycle."
                        )
                        # CRITICAL FIX: Do NOT mark all files as deleted if project directory
                        # doesn't exist. This prevents accidental deletion during:
                        # - Project reupload
                        # - Temporary directory removal
                        # - Path normalization issues
                        # Files will be properly detected as deleted in next scan if they
                        # are still missing after project directory is restored.
                        # If project is permanently deleted, use explicit cleanup command.
                        continue
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
                project_obj = self.database.get_project(project_id)
                project = (
                    {
                        "id": project_obj.id,
                        "root_path": project_obj.root_path,
                        "name": project_obj.name,
                    }
                    if project_obj
                    else None
                )
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

                # Process files for this project
                project_stats = self._queue_project_delta(
                    project_id, delta, project_root
                )

                total_stats["new_files"] += project_stats["new_files"]
                total_stats["changed_files"] += project_stats["changed_files"]
                total_stats["deleted_files"] += project_stats["deleted_files"]
                total_stats["errors"] += project_stats["errors"]

            except Exception as e:
                logger.error(
                    f"Error queueing changes for project {project_id} in {root_dir}: {e}",
                    exc_info=True,
                )
                total_stats["errors"] += (
                    len(delta.new_files)
                    + len(delta.changed_files)
                    + len(delta.deleted_files)
                )

        return total_stats

    def _queue_project_delta(
        self, project_id: str, delta: FileDelta, project_root: Path
    ) -> Dict[str, Any]:
        """
        Queue file changes for a single project.

        Args:
            project_id: Project ID
            delta: FileDelta for this project
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
                mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                logger.info(
                    f"[project={project_id}] [NEW FILE] {file_path_str} | "
                    f"mtime: {mtime_str} ({mtime}) | "
                    f"size: {size} bytes"
                )
                if self._queue_file_for_processing(
                    file_path_str, mtime, project_id, project_root
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
                mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                logger.info(
                    f"[project={project_id}] [CHANGED FILE] {file_path_str} | "
                    f"mtime: {mtime_str} ({mtime}) | "
                    f"size: {size} bytes"
                )
                if self._queue_file_for_processing(
                    file_path_str, mtime, project_id, project_root
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
                    self.database._execute(
                        """
                        UPDATE files 
                        SET deleted = 1, deleted_at = julianday('now')
                        WHERE path = ? AND project_id = ?
                        """,
                        (file_path_str, project_id),
                    )
                    self.database._commit()
                    # Check if row was updated
                    row = self.database._fetchone(
                        "SELECT id FROM files WHERE path = ? AND project_id = ? AND deleted = 1",
                        (file_path_str, project_id),
                    )
                    if row:
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
        self,
        file_path: str,
        mtime: float,
        project_id: str,
        project_root: Optional[Path] = None,
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
            project_root: Project root directory (optional, will be resolved if not provided)

        Returns:
            True if successful, False otherwise
        """
        from ..path_normalization import normalize_file_path
        from ..exceptions import ProjectIdMismatchError

        try:
            # Use unified path normalization method
            # This ensures consistent path usage and project validation
            normalized = normalize_file_path(
                file_path,
                watch_dirs=(
                    self.watch_dirs_resolved
                    if hasattr(self, "watch_dirs_resolved")
                    else None
                ),
                project_root=project_root,
            )
            abs_file_path = normalized.absolute_path

            # Validate that provided project_id matches the one from projectid file
            if normalized.project_id != project_id:
                raise ProjectIdMismatchError(
                    message=(
                        f"Project ID mismatch: file {abs_file_path} belongs to project "
                        f"{normalized.project_id} (from projectid file) "
                        f"but was provided with project_id {project_id}"
                    ),
                    file_project_id=normalized.project_id,
                    db_project_id=project_id,
                )

            # Use validated project_root from normalization
            if project_root is None:
                project_root = normalized.project_root
            root_dir = project_root

            # Get project root directory
            root_dir = project_root
            if not root_dir:
                root_dir = self._get_project_root_dir(project_id, abs_file_path)
                if not root_dir:
                    logger.warning(
                        f"Could not determine root_dir for {abs_file_path}, "
                        "falling back to mark_file_needs_chunking"
                    )
                    # Check if file already exists before UPDATE
                    existing = self.database._fetchone(
                        "SELECT id FROM files WHERE path = ? AND project_id = ?",
                        (abs_file_path, project_id),
                    )
                    if not existing:
                        # New file: insert/update file record first
                        path_obj = Path(abs_file_path)
                        lines = 0
                        has_docstring = False
                        try:
                            if path_obj.exists() and path_obj.is_file():
                                text = path_obj.read_text(
                                    encoding="utf-8", errors="ignore"
                                )
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
                            self.database._execute(
                                """
                                INSERT INTO files (path, lines, last_modified, has_docstring, project_id, created_at)
                                VALUES (?, ?, ?, ?, ?, julianday('now'))
                                """,
                                (
                                    abs_file_path,
                                    lines,
                                    mtime,
                                    has_docstring,
                                    project_id,
                                ),
                            )
                            self.database._commit()
                        except Exception as e:
                            logger.error(
                                f"[QUEUE] Failed to add new file record: {abs_file_path} ({e})"
                            )
                            return False

                        # Retry marking for chunking
                        self.database._execute(
                            """
                            UPDATE files SET needs_chunking = 1 WHERE path = ? AND project_id = ?
                            """,
                            (abs_file_path, project_id),
                        )
                        self.database._commit()
                    else:
                        # File already existed: just mark for chunking
                        self.database._execute(
                            """
                            UPDATE files SET needs_chunking = 1 WHERE path = ? AND project_id = ?
                            """,
                            (abs_file_path, project_id),
                        )
                        self.database._commit()
                    return True

            # Path is already normalized by normalize_file_path above
            # No need to re-normalize

            # Project validation is already done by normalize_file_path
            # No need to re-validate here
            root_dir = project_root
            if root_dir:
                logger.debug(
                    f"[QUEUE] File path normalized and validated: "
                    f"file={abs_file_path}, project_root={root_dir}, project_id={project_id}"
                )

            # Always call add_file to ensure relative_path and watch_dir_id are set/updated
            # This handles both new files (INSERT) and existing files (UPDATE)
            path_obj = Path(abs_file_path)
            lines = 0
            has_docstring = False
            try:
                if path_obj.exists() and path_obj.is_file():
                    text = path_obj.read_text(encoding="utf-8", errors="ignore")
                    lines = text.count("\n") + (1 if text else 0)
                    stripped = text.lstrip()
                    has_docstring = stripped.startswith('"""') or stripped.startswith(
                        "'''"
                    )
            except Exception:
                logger.debug(
                    f"[QUEUE] Failed to read file for metadata, using defaults: {abs_file_path}"
                )

            try:
                # Add/update file and get file_id (add_file handles both INSERT and UPDATE)
                # This ensures relative_path and watch_dir_id are always set correctly
                # Use execute() for add_file
                self.database._execute(
                    """
                    INSERT OR REPLACE INTO files (path, lines, last_modified, has_docstring, project_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, julianday('now'), julianday('now'))
                    """,
                    (
                        abs_file_path,
                        lines,
                        mtime,
                        has_docstring,
                        project_id,
                    ),
                )
                self.database._commit()
                # Get file_id by querying
                file_row = self.database._fetchone(
                    "SELECT id FROM files WHERE path = ? AND project_id = ? LIMIT 1",
                    (abs_file_path, project_id),
                )
                file_id = file_row.get("id", 0) if file_row else 0
                logger.debug(
                    f"[QUEUE] File added/updated in database: {abs_file_path} | "
                    f"file_id={file_id} | project_id={project_id}"
                )

                # Verify file was added/updated successfully by checking file_id
                file_record = self.database.get_file_by_id(file_id) if file_id else None
                if not file_record:
                    logger.error(
                        f"[QUEUE] File was added/updated (file_id={file_id}) but not found in database: {abs_file_path}. "
                        "This may indicate a transaction issue."
                    )
                    return False
                else:
                    logger.debug(
                        f"[QUEUE] File verified in database: file_id={file_id}, "
                        f"path={file_record.get('path')}, relative_path={file_record.get('relative_path')}, "
                        f"watch_dir_id={file_record.get('watch_dir_id')}, project_id={file_record.get('project_id')}"
                    )
            except Exception as e:
                logger.error(
                    f"[QUEUE] Failed to add/update file in database: {abs_file_path} ({e})",
                    exc_info=True,
                )
                return False

            # Update all database records for changed file (using normalized path)
            # Note: update_file_data is a complex method that updates AST/CST/entities
            # For now, we'll mark file for chunking and let the worker handle the full update
            logger.debug(
                f"[QUEUE] Marking file for processing: file_id={file_id}, "
                f"path={abs_file_path}, project_id={project_id}"
            )

            # Mark for chunking (vectorization worker will process)
            # Note: Immediate vectorization is not done here because this is sync context
            # Worker will handle vectorization in background
            self.database._execute(
                """
                UPDATE files SET needs_chunking = 1 WHERE path = ? AND project_id = ?
                """,
                (abs_file_path, project_id),
            )
            self.database._commit()
            logger.debug(
                f"[QUEUE] File marked for worker vectorization: {abs_file_path}"
            )

            return True
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
            project_obj = self.database.get_project(project_id)
            if project_obj and project_obj.root_path:
                return Path(project_obj.root_path)

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
