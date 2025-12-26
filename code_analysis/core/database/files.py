"""
Module files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def get_file_by_path(
    self, path: str, project_id: str, include_deleted: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Get file record by path and project ID.

    Args:
        path: File path
        project_id: Project ID
        include_deleted: If True, include files marked as deleted (default: False)

    Returns:
        File record as dictionary or None if not found
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    if include_deleted:
        cursor.execute(
            "SELECT * FROM files WHERE path = ? AND project_id = ?",
            (path, project_id),
        )
    else:
        cursor.execute(
            "SELECT * FROM files WHERE path = ? AND project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (path, project_id),
    )
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


def add_file(
    self,
    path: str,
    lines: int,
    last_modified: float,
    has_docstring: bool,
    project_id: str,
) -> int:
    """Add or update file record. Returns file_id."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute(
        "\n            INSERT OR REPLACE INTO files\n            (project_id, path, lines, last_modified, has_docstring, updated_at)\n            VALUES (?, ?, ?, ?, ?, julianday('now'))\n        ",
        (project_id, path, lines, last_modified, has_docstring),
    )
    self.conn.commit()
    result = cursor.lastrowid
    assert result is not None
    return result


def get_file_id(
    self, path: str, project_id: str, include_deleted: bool = False
) -> Optional[int]:
    """
    Get file ID by path and project.

    Args:
        path: File path
        project_id: Project ID
        include_deleted: If True, include files marked as deleted (default: False)

    Returns:
        File ID or None if not found
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    if include_deleted:
        cursor.execute(
            "SELECT id FROM files WHERE path = ? AND project_id = ?",
            (path, project_id),
        )
    else:
        cursor.execute(
            "SELECT id FROM files WHERE path = ? AND project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (path, project_id),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def get_file_by_id(self, file_id: int) -> Optional[Dict[str, Any]]:
    """Get file record by ID."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


def delete_file(self, file_id: int) -> None:
    """Delete file and all related records (cascade)."""
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
    self.conn.commit()


def clear_file_data(self, file_id: int) -> None:
    """
    Clear all data for a file.

    Removes all related data including:
    - classes and their methods
    - functions
    - imports
    - issues
    - usages
    - dependencies (both as source and target)
    - code_content and FTS index
    - AST trees
    - code chunks
    - vector index entries

    NOTE: When FAISS is implemented, this method should:
    1. Get all vector_ids from code_chunks for this file_id
    2. Remove these vectors from FAISS index
    3. Then delete from database
    This ensures FAISS stays in sync when files are updated.
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute("SELECT id FROM classes WHERE file_id = ?", (file_id,))
    class_ids = [row[0] for row in cursor.fetchall()]
    cursor.execute("SELECT id FROM code_content WHERE file_id = ?", (file_id,))
    content_ids = [row[0] for row in cursor.fetchall()]
    if content_ids:
        placeholders = ",".join("?" * len(content_ids))
        cursor.execute(
            f"DELETE FROM code_content_fts WHERE rowid IN ({placeholders})", content_ids
        )
    if class_ids:
        placeholders = ",".join("?" * len(class_ids))
        cursor.execute(
            f"DELETE FROM methods WHERE class_id IN ({placeholders})", class_ids
        )
    cursor.execute("DELETE FROM classes WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM functions WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM imports WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM issues WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM usages WHERE file_id = ?", (file_id,))
    cursor.execute(
        "DELETE FROM dependencies WHERE source_file_id = ? OR target_file_id = ?",
        (file_id, file_id),
    )
    cursor.execute("DELETE FROM code_content WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM ast_trees WHERE file_id = ?", (file_id,))
    cursor.execute(
        "SELECT vector_id FROM code_chunks WHERE file_id = ? AND vector_id IS NOT NULL",
        (file_id,),
    )
    [row[0] for row in cursor.fetchall()]
    cursor.execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))
    cursor.execute(
        "\n            SELECT id FROM classes WHERE file_id = ?\n            UNION\n            SELECT id FROM functions WHERE file_id = ?\n        ",
        (file_id, file_id),
    )
    entity_ids = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        "DELETE FROM vector_index WHERE entity_type = 'file' AND entity_id = ?",
        (file_id,),
    )
    if entity_ids:
        placeholders = ",".join("?" * len(entity_ids))
        cursor.execute(
            f"\n                DELETE FROM vector_index\n                WHERE entity_type IN ('class', 'function', 'method')\n                AND entity_id IN ({placeholders})\n            ",
            entity_ids,
        )
    self.conn.commit()


async def remove_missing_files(
    self, project_id: str, root_path: Path
) -> Dict[str, Any]:
    """
    Remove files from database that no longer exist on disk.

    Args:
        project_id: Project ID (UUID4 string)
        root_path: Root directory path of the project

    Returns:
        Dictionary with removal statistics:
        - removed_count: Number of files removed
        - removed_files: List of removed file paths
    """
    assert self.conn is not None
    cursor = self.conn.cursor()
    files = self.get_project_files(project_id)
    removed_files = []
    removed_count = 0
    for file_record in files:
        file_path = Path(file_record["path"])
        if not file_path.exists():
            file_id = file_record["id"]
            logger.info(f"File not found on disk, removing from database: {file_path}")
            self.clear_file_data(file_id)
            cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
            removed_files.append(str(file_path))
            removed_count += 1
    if removed_count > 0:
        self.conn.commit()
        logger.info(
            f"Removed {removed_count} missing files from database for project {project_id}"
        )
    return {"removed_count": removed_count, "removed_files": removed_files}


def get_file_summary(self, file_path: str, project_id: str) -> Optional[Dict[str, Any]]:
    """Get summary for a file."""
    file_id = self.get_file_id(file_path, project_id)
    if not file_id:
        return None
    assert self.conn is not None
    cursor = self.conn.cursor()
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    file_info = dict(cursor.fetchone())
    cursor.execute("SELECT COUNT(*) FROM classes WHERE file_id = ?", (file_id,))
    file_info["class_count"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM functions WHERE file_id = ?", (file_id,))
    file_info["function_count"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM issues WHERE file_id = ?", (file_id,))
    file_info["issue_count"] = cursor.fetchone()[0]
    return file_info


def get_files_needing_chunking(
    self, project_id: str, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get files that need chunking (have docstrings but no chunks).

    Files are considered needing chunking if:
    - They have docstrings (has_docstring = 1) OR
    - They have classes/functions/methods with docstrings
    - AND they have no chunks in code_chunks table
    - AND they are NOT marked as deleted (deleted = 0 or NULL)

    **Important**: Deleted files are ALWAYS excluded from this query.

    Args:
        project_id: Project ID
        limit: Maximum number of files to return

    Returns:
        List of file records that need chunking
    """
    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            "\n                SELECT DISTINCT f.id, f.project_id, f.path, f.has_docstring\n                FROM files f\n                WHERE f.project_id = ?\n                AND (f.deleted = 0 OR f.deleted IS NULL)\n                AND (\n                    f.has_docstring = 1\n                    OR EXISTS (\n                        SELECT 1 FROM classes c\n                        WHERE c.file_id = f.id AND c.docstring IS NOT NULL AND c.docstring != ''\n                    )\n                    OR EXISTS (\n                        SELECT 1 FROM functions fn\n                        WHERE fn.file_id = f.id AND fn.docstring IS NOT NULL AND fn.docstring != ''\n                    )\n                    OR EXISTS (\n                        SELECT 1 FROM methods m\n                        JOIN classes c ON m.class_id = c.id\n                        WHERE c.file_id = f.id AND m.docstring IS NOT NULL AND m.docstring != ''\n                    )\n                )\n                AND NOT EXISTS (\n                    SELECT 1 FROM code_chunks cc\n                    WHERE cc.file_id = f.id\n                )\n                ORDER BY f.updated_at DESC\n                LIMIT ?\n                ",
            (project_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def mark_file_needs_chunking(self, file_path: str, project_id: str) -> bool:
    """
    Mark a file as needing (re-)chunking by deleting its existing chunks.

    The vectorization worker discovers files to chunk via `get_files_needing_chunking()`,
    which selects files that have docstrings but have **no** rows in `code_chunks`.
    To request re-chunking after a file change, we delete existing chunks so the file
    becomes eligible for that query.

    **Important**: Files with deleted=1 are NOT marked for chunking.

    Args:
        file_path: Absolute file path as stored in DB
        project_id: Project ID

    Returns:
        True if file was found and processed, False otherwise.
    """
    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()

        cursor.execute(
            "SELECT id, deleted FROM files WHERE project_id = ? AND path = ?",
            (project_id, file_path),
        )
        row = cursor.fetchone()
        if not row:
            return False

        file_id, is_deleted = row[0], row[1]
        
        # Do not mark deleted files for chunking
        if is_deleted:
            logger.debug(f"File {file_path} is marked as deleted, skipping chunking")
            return False

        # Delete chunks so worker will re-chunk and re-vectorize in background.
        cursor.execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))
        cursor.execute(
            "UPDATE files SET updated_at = julianday('now') WHERE id = ?",
            (file_id,),
        )
        self.conn.commit()
        return True


def mark_file_deleted(
    self,
    file_path: str,
    project_id: str,
    version_dir: str,
    reason: Optional[str] = None,
) -> bool:
    """
    Mark file as deleted (soft delete) and move to version directory.

    Process:
    1. Move file from original path to version directory
    2. Store original path in original_path column
    3. Store version directory in version_dir column
    4. Set deleted=1, update updated_at
    5. File will NOT be chunked or processed

    Args:
        file_path: Original file path (will be moved)
        project_id: Project ID
        version_dir: Directory where deleted files are stored
        reason: Optional reason for deletion

    Returns:
        True if file was found and marked, False otherwise
    """
    import shutil
    from pathlib import Path

    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()

        cursor.execute(
            "SELECT id FROM files WHERE project_id = ? AND path = ?",
            (project_id, file_path),
        )
        row = cursor.fetchone()
        if not row:
            return False

        file_id = row[0]
        original_path = Path(file_path)

        # Check if file exists
        if not original_path.exists():
            logger.warning(
                f"File not found at {file_path}, marking as deleted in DB only"
            )
            # Still mark as deleted in DB, but don't move file
            cursor.execute(
                """
                UPDATE files 
                SET deleted = 1, original_path = ?, version_dir = ?, updated_at = julianday('now')
                WHERE id = ?
                """,
                (str(original_path), version_dir, file_id),
            )
            self.conn.commit()
            return True

        # Create version directory structure: {version_dir}/{project_id}/{relative_path}
        version_dir_path = Path(version_dir) / project_id
        # Get relative path from project root (if possible) or use full path
        try:
            # Try to get project root
            cursor.execute("SELECT root_path FROM projects WHERE id = ?", (project_id,))
            project_row = cursor.fetchone()
            if project_row:
                project_root = Path(project_row[0])
                try:
                    relative_path = original_path.relative_to(project_root)
                    target_path = version_dir_path / relative_path
                except ValueError:
                    # Path not relative to project root, use full path hash
                    import hashlib
                    path_hash = hashlib.md5(str(original_path).encode()).hexdigest()[:8]
                    target_path = version_dir_path / f"{path_hash}_{original_path.name}"
            else:
                # No project root, use path hash
                import hashlib
                path_hash = hashlib.md5(str(original_path).encode()).hexdigest()[:8]
                target_path = version_dir_path / f"{path_hash}_{original_path.name}"
        except Exception as e:
            logger.warning(f"Error calculating relative path: {e}, using hash")
            import hashlib
            path_hash = hashlib.md5(str(original_path).encode()).hexdigest()[:8]
            target_path = version_dir_path / f"{path_hash}_{original_path.name}"

        # Create target directory
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create version directory {target_path.parent}: {e}")
            return False

        # Move file
        try:
            shutil.move(str(original_path), str(target_path))
            logger.info(f"Moved file from {original_path} to {target_path}")
        except Exception as e:
            logger.error(f"Failed to move file from {original_path} to {target_path}: {e}")
            return False

        # Update database
        cursor.execute(
            """
            UPDATE files 
            SET deleted = 1, original_path = ?, version_dir = ?, path = ?, updated_at = julianday('now')
            WHERE id = ?
            """,
            (str(original_path), str(version_dir_path), str(target_path), file_id),
        )
        self.conn.commit()
        logger.info(
            f"Marked file as deleted: {file_path} -> {target_path} (reason: {reason or 'N/A'})"
        )
        return True


def unmark_file_deleted(self, file_path: str, project_id: str) -> bool:
    """
    Unmark file as deleted (recovery) and move back to original location.

    Process:
    1. Find file record by path (current in version_dir) or original_path
    2. Check if file exists in version_dir
    3. Ensure original directory exists (create if needed)
    4. Move file from version_dir back to original_path
    5. Clear original_path and version_dir columns (set to NULL)
    6. Set deleted=0, update updated_at
    7. File will be processed again

    Args:
        file_path: Current file path (in version_dir) or original_path to search
        project_id: Project ID

    Returns:
        True if file was found and unmarked, False otherwise
    """
    import shutil
    from pathlib import Path

    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()

        # Try to find by current path (in version_dir) or original_path
        cursor.execute(
            """
            SELECT id, path, original_path, version_dir 
            FROM files 
            WHERE project_id = ? AND (path = ? OR original_path = ?)
            ORDER BY last_modified DESC
            LIMIT 1
            """,
            (project_id, file_path, file_path),
        )
        row = cursor.fetchone()
        if not row:
            return False

        file_id, current_path, original_path_str, version_dir_str = (
            row[0],
            row[1],
            row[2],
            row[3],
        )

        if not original_path_str:
            logger.warning(f"File {file_id} has no original_path, cannot restore")
            return False

        original_path = Path(original_path_str)
        current_path_obj = Path(current_path)

        # Check if file exists in version directory
        if not current_path_obj.exists():
            logger.error(f"File not found at {current_path_obj}, cannot restore")
            return False

        # Ensure original directory exists
        try:
            original_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create original directory {original_path.parent}: {e}")
            return False

        # Move file back
        try:
            shutil.move(str(current_path_obj), str(original_path))
            logger.info(f"Moved file from {current_path_obj} back to {original_path}")
        except Exception as e:
            logger.error(
                f"Failed to move file from {current_path_obj} to {original_path}: {e}"
            )
            return False

        # Update database: restore original path, clear original_path and version_dir
        cursor.execute(
            """
            UPDATE files 
            SET deleted = 0, path = ?, original_path = NULL, version_dir = NULL, updated_at = julianday('now')
            WHERE id = ?
            """,
            (str(original_path), file_id),
        )
        self.conn.commit()
        logger.info(f"Unmarked file as deleted and restored: {original_path}")
        return True


def get_deleted_files(self, project_id: str) -> List[Dict[str, Any]]:
    """
    Get all deleted files for a project.

    Returns files where deleted=1.

    Args:
        project_id: Project ID

    Returns:
        List of deleted file records
    """
    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM files 
            WHERE project_id = ? AND deleted = 1
            ORDER BY updated_at DESC
            """,
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def hard_delete_file(self, file_id: int) -> None:
    """
    Permanently delete file and all related data (hard delete).

    This is final deletion - removes:
    - Physical file from version_dir (if exists)
    - File record
    - All chunks (and removes from FAISS)
    - All classes, functions, methods
    - All AST trees
    - All vector indexes

    Use with caution - cannot be recovered.

    Args:
        file_id: File ID to delete
    """
    from pathlib import Path

    # Get file info before deletion
    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT path, version_dir FROM files WHERE id = ?", (file_id,)
        )
        row = cursor.fetchone()
        file_path = row[0] if row else None
        version_dir = row[1] if row and len(row) > 1 else None

    # Delete physical file if it exists in version directory
    if file_path and version_dir:
        try:
            file_path_obj = Path(file_path)
            if file_path_obj.exists():
                file_path_obj.unlink()
                logger.info(f"Deleted physical file: {file_path}")
                # Try to remove empty parent directories
                try:
                    parent = file_path_obj.parent
                    if parent.exists() and not any(parent.iterdir()):
                        parent.rmdir()
                except Exception:
                    pass  # Ignore errors removing directories
        except Exception as e:
            logger.warning(f"Failed to delete physical file {file_path}: {e}")

    # Use existing clear_file_data method which handles all cleanup
    self.clear_file_data(file_id)

    # Then delete the file record itself
    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
        self.conn.commit()
        logger.info(f"Hard deleted file ID {file_id}")


def get_file_versions(
    self, file_path: str, project_id: str
) -> List[Dict[str, Any]]:
    """
    Get all versions of a file (same path, different last_modified).

    Version = last_modified timestamp.
    Multiple records with same path but different last_modified are considered versions.

    Args:
        file_path: File path
        project_id: Project ID

    Returns:
        List of file versions sorted by last_modified (newest first)
    """
    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM files 
            WHERE project_id = ? AND path = ?
            ORDER BY last_modified DESC
            """,
            (project_id, file_path),
        )
        return [dict(row) for row in cursor.fetchall()]


def collapse_file_versions(
    self, project_id: str, keep_latest: bool = True
) -> Dict[str, Any]:
    """
    Collapse file versions, keeping only latest by last_modified.

    Finds all records with same path but different last_modified.
    Keeps the one with latest last_modified, deletes others (hard delete).

    Args:
        project_id: Project ID
        keep_latest: If True, keep latest version (default: True)

    Returns:
        Dictionary with:
        - kept_count: Number of versions kept
        - deleted_count: Number of versions deleted
        - collapsed_files: List of file paths that had multiple versions
    """
    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()
        
        # Find all files with multiple versions (same path, different last_modified)
        cursor.execute(
            """
            SELECT path, COUNT(*) as version_count
            FROM files
            WHERE project_id = ?
            GROUP BY path
            HAVING COUNT(*) > 1
            """,
            (project_id,),
        )
        files_with_versions = cursor.fetchall()
        
        kept_count = 0
        deleted_count = 0
        collapsed_files = []
        
        for path_row in files_with_versions:
            file_path = path_row[0]
            collapsed_files.append(file_path)
            
            # Get all versions for this file
            versions = self.get_file_versions(file_path, project_id)
            
            if keep_latest:
                # Keep the first one (newest by last_modified DESC)
                keep_version = versions[0]
                delete_versions = versions[1:]
            else:
                # Keep the oldest
                keep_version = versions[-1]
                delete_versions = versions[:-1]
            
            # Hard delete old versions
            for version in delete_versions:
                self.hard_delete_file(version["id"])
                deleted_count += 1
            
            kept_count += 1
        
        logger.info(
            f"Collapsed versions for {len(collapsed_files)} files: "
            f"kept {kept_count}, deleted {deleted_count}"
        )
        
        return {
            "kept_count": kept_count,
            "deleted_count": deleted_count,
            "collapsed_files": collapsed_files,
        }
