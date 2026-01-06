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
    """

    def __init__(
        self,
        database: Any,
        project_id: str,
        version_dir: Optional[str] = None,
        dataset_id: Optional[str] = None,
    ):
        """
        Initialize file change processor.

        Implements dataset-scoped file processing (Step 2 of refactor plan).
        If dataset_id is provided, processes files only for that dataset.
        If dataset_id is None, resolves dataset_id from root_dir when processing.

        Args:
            database: CodeDatabase instance
            project_id: Project ID (REQUIRED)
            version_dir: Version directory for deleted files (optional)
            dataset_id: Optional dataset ID (if None, will be resolved from root_dir)
        """
        self.database = database
        self.project_id = project_id
        self.version_dir = version_dir
        self.dataset_id = dataset_id

    def compute_delta(
        self, root_dir: Path, scanned_files: Dict[str, Dict]
    ) -> FileDelta:
        """
        Compute file change delta (SCAN PHASE - no DB operations).

        Implements Step 3 of refactor plan: scan phase computes delta
        without performing any database operations.

        Args:
            root_dir: Root watched directory (will be normalized to absolute)
            scanned_files: Files found on disk (from scanner)

        Returns:
            FileDelta with new/changed/deleted file lists
        """
        from ..project_resolution import normalize_root_dir

        new_files: List[tuple[str, float, int]] = []
        changed_files: List[tuple[str, float, int]] = []

        try:
            # Resolve dataset_id from root_dir if not already set
            normalized_root = str(normalize_root_dir(root_dir))
            dataset_id = self.dataset_id
            if not dataset_id:
                dataset_id = self.database.get_dataset_id(
                    self.project_id, normalized_root
                )
                if not dataset_id:
                    # Create dataset if it doesn't exist (minimal DB read for dataset resolution)
                    dataset_id = self.database.get_or_create_dataset(
                        self.project_id, normalized_root
                    )
                    logger.info(
                        f"Created dataset {dataset_id} for root {normalized_root}"
                    )

            # Get files from database for this project and dataset (read-only)
            db_files = self.database.get_project_files(
                self.project_id, include_deleted=False
            )
            # Filter by dataset_id
            db_files = [f for f in db_files if f.get("dataset_id") == dataset_id]

            # Create mapping of path -> file record
            db_files_map = {f["path"]: f for f in db_files}

            # Compute delta for new and changed files (no DB writes)
            for file_path_str, file_info in scanned_files.items():
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
            deleted_files = list(find_missing_files(scanned_files, db_files))

        except Exception as e:
            logger.error(f"Error computing delta for {root_dir}: {e}")
            # Return empty delta on error
            return FileDelta(new_files=[], changed_files=[], deleted_files=[])

        return FileDelta(
            new_files=new_files,
            changed_files=changed_files,
            deleted_files=deleted_files,
        )

    def queue_changes(self, root_dir: Path, delta: FileDelta) -> Dict[str, Any]:
        """
        Queue file changes in database (QUEUE PHASE - batch DB operations).

        Implements Step 3 of refactor plan: queue phase performs batch
        database operations for all changes computed in scan phase.

        Args:
            root_dir: Root watched directory (will be normalized to absolute)
            delta: FileDelta computed in scan phase

        Returns:
            Dictionary with processing statistics:
            {
                "new_files": int,
                "changed_files": int,
                "deleted_files": int,
                "errors": int,
            }
        """
        from ..project_resolution import normalize_root_dir

        stats = {
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }

        try:
            # Resolve dataset_id from root_dir
            normalized_root = str(normalize_root_dir(root_dir))
            dataset_id = self.dataset_id
            if not dataset_id:
                dataset_id = self.database.get_dataset_id(
                    self.project_id, normalized_root
                )
                if not dataset_id:
                    dataset_id = self.database.get_or_create_dataset(
                        self.project_id, normalized_root
                    )

            if not dataset_id:
                logger.error(f"[QUEUE] Cannot determine dataset_id for root {root_dir}")
                stats["errors"] = (
                    len(delta.new_files)
                    + len(delta.changed_files)
                    + len(delta.deleted_files)
                )
                return stats

            # Batch process new files
            for file_path_str, mtime, size in delta.new_files:
                try:
                    mtime_str = datetime.fromtimestamp(mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    logger.info(
                        f"[NEW FILE] {file_path_str} | "
                        f"mtime: {mtime_str} ({mtime}) | "
                        f"size: {size} bytes"
                    )
                    if self._queue_file_for_processing(
                        file_path_str, mtime, dataset_id
                    ):
                        stats["new_files"] += 1
                        logger.info(
                            f"[NEW FILE] ✓ Queued for processing: {file_path_str}"
                        )
                    else:
                        stats["errors"] += 1
                        logger.error(f"[NEW FILE] ✗ Failed to queue: {file_path_str}")
                except Exception as e:
                    logger.error(f"Error queueing new file {file_path_str}: {e}")
                    stats["errors"] += 1

            # Batch process changed files
            for file_path_str, mtime, size in delta.changed_files:
                try:
                    mtime_str = datetime.fromtimestamp(mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    logger.info(
                        f"[CHANGED FILE] {file_path_str} | "
                        f"mtime: {mtime_str} ({mtime}) | "
                        f"size: {size} bytes"
                    )
                    if self._queue_file_for_processing(
                        file_path_str, mtime, dataset_id
                    ):
                        stats["changed_files"] += 1
                        logger.info(
                            f"[CHANGED FILE] ✓ Queued for processing: {file_path_str}"
                        )
                    else:
                        stats["errors"] += 1
                        logger.error(
                            f"[CHANGED FILE] ✗ Failed to queue: {file_path_str}"
                        )
                except Exception as e:
                    logger.error(f"Error queueing changed file {file_path_str}: {e}")
                    stats["errors"] += 1

            # Batch process deleted files
            for file_path_str in delta.deleted_files:
                try:
                    logger.info(f"[DELETED FILE] {file_path_str} | action: soft_delete")
                    if self.version_dir:
                        if self.database.mark_file_deleted(
                            file_path_str, self.project_id, self.version_dir
                        ):
                            stats["deleted_files"] += 1
                            logger.info(
                                f"[DELETED FILE] ✓ Marked as deleted: {file_path_str}"
                            )
                        else:
                            stats["errors"] += 1
                            logger.error(
                                f"[DELETED FILE] ✗ Failed to mark as deleted: {file_path_str}"
                            )
                    else:
                        logger.warning(
                            f"[DELETED FILE] ✗ version_dir not configured, cannot mark {file_path_str} as deleted"
                        )
                        stats["errors"] += 1
                except Exception as e:
                    logger.error(
                        f"[DELETED FILE] ✗ Error marking file as deleted {file_path_str}: {e}"
                    )
                    stats["errors"] += 1

        except Exception as e:
            logger.error(f"Error queueing changes for {root_dir}: {e}")
            stats["errors"] += (
                len(delta.new_files)
                + len(delta.changed_files)
                + len(delta.deleted_files)
            )

        return stats

    def process_changes(
        self, root_dir: Path, scanned_files: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """
        Process file changes (legacy method - combines scan and queue).

        This method is kept for backward compatibility but internally
        uses compute_delta + queue_changes to implement scan → queue phases.

        Args:
            root_dir: Root watched directory (will be normalized to absolute)
            scanned_files: Files found on disk (from scanner)

        Returns:
            Dictionary with processing statistics
        """
        # Step 3: Separate scan and queue phases
        delta = self.compute_delta(root_dir, scanned_files)
        return self.queue_changes(root_dir, delta)

    def _queue_file_for_processing(
        self, file_path: str, mtime: float, dataset_id: str
    ) -> bool:
        """
        Queue file for processing (chunking) - used in queue phase.

        Implements dataset-scoped file processing (Step 2 of refactor plan).

        Args:
            file_path: File path (will be normalized to absolute)
            mtime: File modification time
            dataset_id: Dataset ID (already resolved)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Mark file for chunking (this will delete existing chunks and update updated_at).
            # If the file is not yet present in DB (new file), we first create a minimal
            # file record and then mark it for chunking.
            result = self.database.mark_file_needs_chunking(file_path, self.project_id)
            if not result:
                # New file: insert/update file record first.
                path_obj = Path(file_path)
                lines = 0
                has_docstring = False
                try:
                    if path_obj.exists() and path_obj.is_file():
                        # Lightweight docstring detection: module docstring at file start.
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
                        project_id=self.project_id,
                        dataset_id=dataset_id,
                    )
                except Exception as e:
                    logger.error(
                        f"[QUEUE] Failed to add new file record: {file_path} ({e})"
                    )
                    return False

                # Retry marking for chunking after inserting the file record.
                result = self.database.mark_file_needs_chunking(
                    file_path, self.project_id
                )
            if result:
                # Update last_modified if file exists
                self.database._execute(
                    """
                    UPDATE files 
                    SET last_modified = ?, updated_at = julianday('now')
                    WHERE project_id = ? AND path = ?
                    """,
                    (mtime, self.project_id, file_path),
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

    def _mark_file_for_processing(
        self, file_path: str, mtime: float, root_dir: Optional[Path] = None
    ) -> bool:
        """
        Mark file for processing (legacy method - kept for backward compatibility).

        This method resolves dataset_id and calls _queue_file_for_processing.
        New code should use _queue_file_for_processing directly with resolved dataset_id.

        Args:
            file_path: File path (will be normalized to absolute)
            mtime: File modification time
            root_dir: Optional root directory for dataset resolution

        Returns:
            True if successful, False otherwise
        """
        from ..project_resolution import normalize_root_dir

        try:
            # Resolve dataset_id from root_dir if not already set
            dataset_id = self.dataset_id
            if not dataset_id and root_dir:
                normalized_root = str(normalize_root_dir(root_dir))
                dataset_id = self.database.get_dataset_id(
                    self.project_id, normalized_root
                )
                if not dataset_id:
                    # Create dataset if it doesn't exist
                    dataset_id = self.database.get_or_create_dataset(
                        self.project_id, normalized_root
                    )

            if not dataset_id:
                logger.error(
                    f"[QUEUE] Cannot determine dataset_id for file {file_path}, "
                    "root_dir must be provided if dataset_id not set"
                )
                return False

            return self._queue_file_for_processing(file_path, mtime, dataset_id)
        except Exception as e:
            logger.error(
                f"[QUEUE] ✗ Error marking file for processing {file_path}: {e}"
            )
            return False
