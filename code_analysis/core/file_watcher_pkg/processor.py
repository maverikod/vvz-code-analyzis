"""
File change processor for file watcher worker.

Detects file changes and marks them for processing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .scanner import find_missing_files

logger = logging.getLogger(__name__)


class FileChangeProcessor:
    """
    Processes file changes detected by scanner.

    Compares file mtime with database last_modified and marks changed files.
    """

    def __init__(
        self, database: Any, project_id: str, version_dir: Optional[str] = None
    ):
        """
        Initialize file change processor.

        Args:
            database: CodeDatabase instance
            project_id: Project ID
            version_dir: Version directory for deleted files (optional)
        """
        self.database = database
        self.project_id = project_id
        self.version_dir = version_dir

    def process_changes(
        self, root_dir: Path, scanned_files: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """
        Process file changes for a root directory.

        Args:
            root_dir: Root watched directory
            scanned_files: Files found on disk (from scanner)

        Returns:
            Dictionary with processing statistics:
            {
                "new_files": int,
                "changed_files": int,
                "deleted_files": int,
                "errors": int,
            }
        """
        stats = {
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }

        try:
            # Get files from database for this project
            db_files = self.database.get_project_files(
                self.project_id, include_deleted=False
            )

            # Create mapping of path -> file record
            db_files_map = {f["path"]: f for f in db_files}

            # Process new and changed files
            for file_path_str, file_info in scanned_files.items():
                try:
                    mtime = file_info["mtime"]

                    # Check if file is in database
                    db_file = db_files_map.get(file_path_str)

                    if not db_file:
                        # New file - mark for processing
                        mtime_str = datetime.fromtimestamp(mtime).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        logger.info(
                            f"[NEW FILE] {file_path_str} | "
                            f"mtime: {mtime_str} ({mtime}) | "
                            f"size: {file_info.get('size', 0)} bytes"
                        )
                        if self._mark_file_for_processing(file_path_str, mtime):
                            stats["new_files"] += 1
                            logger.info(
                                f"[NEW FILE] ✓ Queued for processing: {file_path_str}"
                            )
                        else:
                            stats["errors"] += 1
                            logger.error(
                                f"[NEW FILE] ✗ Failed to queue: {file_path_str}"
                            )
                    else:
                        # Existing file - check if changed
                        db_mtime = db_file.get("last_modified")
                        if db_mtime is None or abs(mtime - db_mtime) > 0.1:
                            # File changed (tolerance 0.1 seconds for filesystem precision)
                            mtime_str = datetime.fromtimestamp(mtime).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                            db_mtime_str = (
                                datetime.fromtimestamp(db_mtime).strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                                if db_mtime
                                else "N/A"
                            )
                            logger.info(
                                f"[CHANGED FILE] {file_path_str} | "
                                f"disk_mtime: {mtime_str} ({mtime}) | "
                                f"db_mtime: {db_mtime_str} ({db_mtime}) | "
                                f"size: {file_info.get('size', 0)} bytes | "
                                f"diff: {abs(mtime - (db_mtime or 0)):.2f}s"
                            )
                            if self._mark_file_for_processing(file_path_str, mtime):
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
                    logger.error(f"Error processing file {file_path_str}: {e}")
                    stats["errors"] += 1

            # Find missing files (in DB but not on disk)
            missing_paths = find_missing_files(scanned_files, db_files)
            for file_path_str in missing_paths:
                try:
                    # Get file info from DB before marking as deleted
                    db_file = db_files_map.get(file_path_str)
                    db_mtime = db_file.get("last_modified") if db_file else None
                    db_mtime_str = (
                        datetime.fromtimestamp(db_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        if db_mtime
                        else "N/A"
                    )
                    logger.info(
                        f"[DELETED FILE] {file_path_str} | "
                        f"last_known_mtime: {db_mtime_str} ({db_mtime}) | "
                        f"action: soft_delete"
                    )
                    # Mark as deleted (soft delete)
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
            logger.error(f"Error processing changes for {root_dir}: {e}")
            stats["errors"] += 1

        return stats

    def _mark_file_for_processing(self, file_path: str, mtime: float) -> bool:
        """
        Mark file for processing (chunking).

        Args:
            file_path: File path
            mtime: File modification time

        Returns:
            True if successful, False otherwise
        """
        try:
            # Mark file for chunking (this will delete existing chunks and update updated_at)
            result = self.database.mark_file_needs_chunking(file_path, self.project_id)
            if result:
                # Update last_modified if file exists
                with self.database._lock:
                    cursor = self.database.conn.cursor()
                    cursor.execute(
                        """
                        UPDATE files 
                        SET last_modified = ?, updated_at = julianday('now')
                        WHERE project_id = ? AND path = ?
                        """,
                        (mtime, self.project_id, file_path),
                    )
                    self.database.conn.commit()
                logger.debug(
                    f"[QUEUE] File queued for chunking: {file_path} | "
                    f"mtime updated to: {datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')}"
                )
            return result
        except Exception as e:
            logger.error(
                f"[QUEUE] ✗ Error marking file for processing {file_path}: {e}"
            )
            return False
