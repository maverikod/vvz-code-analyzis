"""
File trash: mark_file_deleted, unmark_file_deleted, get_deleted_files, hard_delete_file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path

from code_analysis.core.sql_portable import WHERE_FILES_TRASHED
from typing import Any, Dict, List, Optional, cast

logger = logging.getLogger(__name__)


def mark_file_deleted(
    self,
    file_path: str,
    project_id: str,
    version_dir: Optional[str] = None,
    reason: Optional[str] = None,
    trash_dir: Optional[str] = None,
) -> bool:
    """
    Mark file as deleted (soft delete) and move to file trash.

    Process:
    1. Move file from original path to trash (trash_dir/project_id/... or version_dir/project_id/...)
    2. Store original path in original_path column
    3. Store trash/version dir in version_dir column, path = path in trash
    4. Set deleted=1, update updated_at
    5. File will NOT be chunked or processed

    If trash_dir is provided, file trash root is trash_dir/project_id (FILE_TRASH_SPEC).
    Otherwise version_dir is used (backward compat). Replace-if-exists: if the same
    project_id+original_path is already in trash, the old file is removed before move.

    Path resolution: project root is taken from the projects table (get_project(project_id));
    a **relative** ``file_path`` is always resolved against that root (logical cwd = project
    root), never the process current working directory.

    Args:
        file_path: Original file path (relative to project root or absolute; normalized and moved)
        project_id: Project ID
        version_dir: Legacy directory for deleted files (used when trash_dir is None)
        reason: Optional reason for deletion
        trash_dir: Preferred root for file trash; files go under trash_dir/project_id/...

    Returns:
        True if file was found and marked, False otherwise
    """
    import shutil

    if trash_dir is not None:
        from ...storage_paths import get_file_trash_dir

        file_trash_root = get_file_trash_dir(Path(trash_dir), project_id)
    elif version_dir is not None:
        file_trash_root = Path(version_dir) / project_id
    else:
        logger.error("mark_file_deleted: either trash_dir or version_dir must be set")
        return False

    # Resolve project root from projects table
    project_root = None
    try:
        db_project = self.get_project(project_id)
        if db_project:
            project_root = Path(db_project["root_path"])
    except Exception as e:
        logger.debug(f"Could not get project root from database: {e}")

    # Use unified path normalization if project_root is available.
    # Important: normalize_file_path() validates file existence before applying
    # project_root semantics, so for relative paths we pre-resolve against
    # project_root to avoid false "File not found" from current working dir.
    abs_path = None
    if project_root and project_root.exists():
        try:
            from ...path_normalization import normalize_file_path
            from ...exceptions import ProjectIdMismatchError

            candidate_path = (
                str((project_root / file_path).resolve())
                if not Path(file_path).is_absolute()
                else file_path
            )
            normalized = normalize_file_path(candidate_path, project_root=project_root)
            abs_path = normalized.absolute_path

            # Validate project_id matches
            if normalized.project_id != project_id:
                raise ProjectIdMismatchError(
                    message=(
                        f"Project ID mismatch: file {abs_path} belongs to project "
                        f"{normalized.project_id} (from projectid file) "
                        f"but was provided with project_id {project_id}"
                    ),
                    file_project_id=normalized.project_id,
                    db_project_id=project_id,
                )
        except ProjectIdMismatchError:
            # Re-raise critical mismatch
            raise
        except FileNotFoundError:
            # File can be absent on disk but still tracked in DB (soft-delete path).
            from ...path_normalization import normalize_path_simple

            if Path(file_path).is_absolute():
                abs_path = normalize_path_simple(file_path)
            else:
                abs_path = normalize_path_simple(project_root / file_path)
        except Exception as e:
            # Log but continue with simple normalization
            logger.debug(f"Path normalization failed, using simple normalization: {e}")
            from ...path_normalization import normalize_path_simple

            if Path(file_path).is_absolute():
                abs_path = normalize_path_simple(file_path)
            elif project_root:
                abs_path = normalize_path_simple(project_root / file_path)
            else:
                abs_path = normalize_path_simple(file_path)
    else:
        # project_root missing on disk or branch skipped: still anchor relative paths to DB root
        from ...path_normalization import normalize_path_simple

        if project_root:
            if Path(file_path).is_absolute():
                abs_path = normalize_path_simple(file_path)
            else:
                abs_path = normalize_path_simple(project_root / file_path)
        else:
            abs_path = normalize_path_simple(file_path)

    row = self._fetchone(
        "SELECT id FROM files WHERE project_id = ? AND path = ?",
        (project_id, abs_path),
    )
    if not row:
        return False

    file_id = row["id"]
    original_path = Path(abs_path)

    # Check if file exists
    if not original_path.exists():
        logger.warning(f"File not found at {file_path}, marking as deleted in DB only")
        self._execute(
            """
            UPDATE files 
            SET deleted = 1, original_path = ?, version_dir = ?, updated_at = julianday('now')
            WHERE id = ?
            """,
            (str(original_path), str(file_trash_root), file_id),
        )
        self._commit()
        return True

    # Target under file trash root: {file_trash_root}/{relative_path}
    try:
        project_row = self._fetchone(
            "SELECT root_path FROM projects WHERE id = ?", (project_id,)
        )
        if project_row:
            project_root = Path(project_row["root_path"])
            try:
                relative_path = original_path.relative_to(project_root)
                target_path = file_trash_root / relative_path
            except ValueError:
                import hashlib

                path_hash = hashlib.md5(str(original_path).encode()).hexdigest()[:8]
                target_path = file_trash_root / f"{path_hash}_{original_path.name}"
        else:
            import hashlib

            path_hash = hashlib.md5(str(original_path).encode()).hexdigest()[:8]
            target_path = file_trash_root / f"{path_hash}_{original_path.name}"
    except Exception as e:
        logger.warning(f"Error calculating relative path: {e}, using hash")
        import hashlib

        path_hash = hashlib.md5(str(original_path).encode()).hexdigest()[:8]
        target_path = file_trash_root / f"{path_hash}_{original_path.name}"

    # Replace-if-exists: remove existing file at target or old trashed copy (FILE_TRASH_SPEC)
    try:
        if target_path.exists():
            target_path.unlink()
            logger.debug(f"Replaced existing file at {target_path}")
        existing = self._fetchone(
            f"""
            SELECT id, path FROM files
            WHERE project_id = ? AND original_path = ? AND {WHERE_FILES_TRASHED} AND id != ?
            """,
            (project_id, str(original_path), file_id),
        )
        if existing:
            old_path = Path(existing["path"])
            if old_path.exists():
                old_path.unlink()
                logger.debug(f"Removed previous trashed copy at {old_path}")
    except Exception as e:
        logger.warning(f"Replace-if-exists cleanup: {e}")

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create trash directory {target_path.parent}: {e}")
        return False

    try:
        shutil.move(str(original_path), str(target_path))
        logger.info(f"Moved file from {original_path} to {target_path}")
    except Exception as e:
        logger.error(f"Failed to move file from {original_path} to {target_path}: {e}")
        return False

    self._execute(
        """
        UPDATE files 
        SET deleted = 1, original_path = ?, version_dir = ?, path = ?, updated_at = julianday('now')
        WHERE id = ?
        """,
        (str(original_path), str(file_trash_root), str(target_path), file_id),
    )
    self._commit()
    logger.info(
        f"Marked file as deleted: {file_path} -> {target_path} (reason: {reason or 'N/A'})"
    )
    return True


def unmark_file_deleted(
    self,
    file_path: str,
    project_id: str,
    out_error: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Unmark file as deleted (recovery) and move back to original location.

    Process:
    1. Find file record by path (current in trash/version_dir) or original_path
    2. Pre-check: if original_path already exists on disk, do not overwrite (return False, FILE_EXISTS_AT_TARGET)
    3. Check if file exists in trash/version directory
    4. Move file from trash back to original_path, clear deleted flag

    Args:
        file_path: Current file path (in trash) or original_path to search (normalized to absolute)
        project_id: Project ID
        out_error: Optional dict to receive error_code and message when returning False (e.g. FILE_EXISTS_AT_TARGET)

    Returns:
        True if file was found and unmarked, False otherwise
    """
    import shutil

    from ...path_normalization import normalize_path_simple

    abs_path = normalize_path_simple(file_path)
    row = self._fetchone(
        """
        SELECT id, path, original_path, version_dir 
        FROM files 
        WHERE project_id = ? AND (path = ? OR original_path = ?)
        ORDER BY last_modified DESC
        LIMIT 1
        """,
        (project_id, abs_path, abs_path),
    )
    if not row:
        return False

    file_id, current_path, original_path_str = (
        row["id"],
        row["path"],
        row["original_path"],
    )

    if not original_path_str:
        logger.warning(f"File {file_id} has no original_path, cannot restore")
        return False

    original_path = Path(original_path_str)

    # Pre-check: do not overwrite existing file at target (FILE_TRASH_SPEC Req. 2)
    if original_path.exists():
        if out_error is not None:
            out_error["error_code"] = "FILE_EXISTS_AT_TARGET"
            out_error["message"] = (
                f"File already exists at {original_path}. "
                "Delete or rename it before restoring."
            )
        logger.warning(f"Restore skipped: target already exists at {original_path}")
        return False

    current_path_obj = Path(current_path)

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
    self._execute(
        """
        UPDATE files 
        SET deleted = 0, path = ?, original_path = NULL, version_dir = NULL, updated_at = julianday('now')
        WHERE id = ?
        """,
        (str(original_path), file_id),
    )
    self._commit()
    logger.info(f"Unmarked file as deleted and restored: {original_path}")
    return True


def get_deleted_files(self, project_id: str) -> List[Dict[str, Any]]:
    """
    Get all deleted files for a project.

    Returns files where deleted=1. For files moved to trash (mark_file_deleted),
    path is the trash path (under trash_dir/project_id); original_path is the
    project path. For watcher-only deleted files, path remains the former
    project path and version_dir is null (FILE_TRASH_SPEC step 11).

    Args:
        project_id: Project ID

    Returns:
        List of deleted file records (path, original_path, version_dir, etc.)
    """
    return cast(
        List[Dict[str, Any]],
        self._fetchall(
            f"""
        SELECT * FROM files 
        WHERE project_id = ? AND {WHERE_FILES_TRASHED}
        ORDER BY updated_at DESC
        """,
            (project_id,),
        ),
    )


def hard_delete_file(self, file_id: int) -> None:
    """
    Permanently delete file and all related data (hard delete).

    Order: get path from DB -> delete physical file at path (and empty parents under trash)
    -> clear_file_data(file_id) -> DELETE FROM files -> commit.
    File trash and version storage are the same place: trash_dir/{project_id}/...
    (path in files.path points there when deleted).

    Removes:
    - Physical file at files.path (trash/version location)
    - File record and all dependent data (chunks, FAISS, classes, methods, AST, etc.)

    Args:
        file_id: File ID to delete
    """
    # Get file info before deletion
    row = self._fetchone("SELECT path, version_dir FROM files WHERE id = ?", (file_id,))
    file_path = row["path"] if row else None
    version_dir = row["version_dir"] if row else None

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
    self._execute("DELETE FROM files WHERE id = ?", (file_id,))
    self._commit()
    logger.info(f"Hard deleted file ID {file_id}")
