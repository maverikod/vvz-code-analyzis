"""
File update: update_file_data (unified update after write).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ...constants import FILE_MODIFICATION_TOLERANCE, LAST_MODIFIED_EPSILON
from ...exceptions import ProjectIdMismatchError
from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE

from .helpers import _last_modified_to_unix

logger = logging.getLogger(__name__)


def _is_fk_or_integrity_error(exc: Exception) -> bool:
    """True if the exception is FK or integrity-related (no silent swallow)."""
    s = str(exc).lower()
    return "foreign key" in s or "integrity" in s


def update_file_data(
    self,
    file_path: str,
    project_id: str,
    root_dir: Path,
) -> Dict[str, Any]:
    """
    Update all database records for a file after it was written.

    This is the unified update mechanism that ensures consistency across
    all data structures (AST, CST, code entities, chunks).

    Process:
    1. Find file_id by path
    2. Clear all old records (including CST trees)
    3. Call update_indexes to recreate all records:
       - Parse AST
       - Save AST tree
       - Save CST tree
       - Extract code entities
    4. Return result

    Args:
        file_path: File path (relative to root_dir or absolute)
        project_id: Project ID
        root_dir: Project root directory

    Returns:
        Dictionary with update result:
        {
            "success": bool,
            "file_id": int,
            "file_path": str,
            "ast_updated": bool,
            "cst_updated": bool,
            "entities_updated": int,
            "error": Optional[str]
        }
    """
    from ...path_normalization import normalize_path_simple

    try:
        # Normalize path to absolute
        abs_path = normalize_path_simple(file_path)
        if not Path(abs_path).is_absolute():
            abs_path = str((Path(root_dir) / file_path).resolve())

        # Log normalization for debugging
        if file_path != abs_path:
            logger.debug(
                f"[update_file_data] Path normalized: {file_path!r} -> {abs_path!r} | "
                f"project_id={project_id} | root_dir={root_dir}"
            )

        # Validate project_id: check if project_id from parameter matches projectid file
        # This is a safety gate to prevent data inconsistency
        try:
            from ...project_resolution import load_project_id

            root_dir_path = Path(root_dir).resolve()
            file_project_id = load_project_id(root_dir_path)
            if file_project_id != project_id:
                raise ProjectIdMismatchError(
                    message=(
                        f"Project ID mismatch: file {abs_path} belongs to project "
                        f"{file_project_id} (from projectid file at {root_dir_path}) "
                        f"but was provided with project_id {project_id}"
                    ),
                    file_project_id=file_project_id,
                    db_project_id=project_id,
                )
        except ProjectIdMismatchError:
            # Re-raise project ID mismatch
            raise
        except Exception as e:
            # Log but don't fail - validation is a safety check
            logger.warning(
                f"[update_file_data] Failed to validate project_id for {abs_path}: {e}"
            )

        # Early project existence guard: avoid FK race / write when project was deleted
        if self.get_project(project_id) is None:
            return {
                "success": False,
                "error": f"Project not found: {project_id}",
                "file_path": abs_path,
            }

        # Get file record
        file_record = self.get_file_by_path(abs_path, project_id)
        if not file_record:
            # Try to find file by searching all files in project (fallback for debugging)
            logger.warning(
                f"[update_file_data] File not found by path: {abs_path} | "
                f"project_id={project_id}. Searching in project..."
            )
            # Try to find by filename only (last resort)
            filename = Path(abs_path).name
            all_files = self._fetchall(
                "SELECT id, path FROM files WHERE project_id = ? AND path LIKE ? AND "
                + WHERE_FILES_ACTIVE,
                (project_id, f"%{filename}"),
            )
            if all_files:
                logger.warning(
                    f"[update_file_data] Found {len(all_files)} files with same name. "
                    f"Expected: {abs_path}, Found: {[f['path'] for f in all_files[:3]]}"
                )

            return {
                "success": False,
                "error": f"File not found in database: {file_path}",
                "file_path": abs_path,
            }

        file_id = file_record["id"]

        # Get current file mtime from disk
        try:
            file_path_obj = Path(abs_path)
            if file_path_obj.exists():
                current_mtime = file_path_obj.stat().st_mtime
            else:
                current_mtime = file_record.get("last_modified", 0)
        except Exception:
            current_mtime = file_record.get("last_modified", 0)

        # Skip full reindex if file exists and stored last_modified matches disk mtime
        # *and* we already have structural index (AST). Watcher rows often have
        # last_modified equal to disk mtime on first insert; without this guard,
        # index_file would "succeed" with skipped=True while never creating AST/chunks.
        normalized_lm = _last_modified_to_unix(file_record.get("last_modified"))
        ast_exists = self._fetchone(
            "SELECT 1 AS ok FROM ast_trees WHERE file_id = ? LIMIT 1",
            (file_id,),
        )
        if (
            Path(abs_path).exists()
            and normalized_lm is not None
            and abs(normalized_lm - current_mtime) <= FILE_MODIFICATION_TOLERANCE
            and ast_exists is not None
        ):
            try:
                self._clear_file_vectors(file_id)
                self._execute(
                    "UPDATE files SET needs_chunking = 1 WHERE id = ?",
                    (file_id,),
                )
                self._commit()
            except Exception as e:
                logger.error(
                    "Error clearing vectors / setting needs_chunking on skip: %s",
                    e,
                    exc_info=True,
                )
                err_msg = (
                    f"Database foreign key constraint error: {e}"
                    if _is_fk_or_integrity_error(e)
                    else f"Failed on skip path: {e}"
                )
                return {
                    "success": False,
                    "error": err_msg,
                    "file_path": abs_path,
                    "file_id": file_id,
                }
            return {
                "success": True,
                "file_path": abs_path,
                "file_id": file_id,
                "skipped": True,
            }

        # Clear all old records (including CST trees - fixed in Phase 1)
        try:
            self.clear_file_data(file_id)
        except Exception as e:
            logger.error(
                f"Error clearing file data for {file_path}: {e}", exc_info=True
            )
            err_msg = (
                f"Database foreign key constraint error: {e}"
                if _is_fk_or_integrity_error(e)
                else f"Failed to clear old records: {e}"
            )
            return {
                "success": False,
                "error": err_msg,
                "file_path": abs_path,
                "file_id": file_id,
            }

        # Update last_modified to be slightly different from file_mtime
        # so _analyze_file will process the file; overwritten with real mtime after success
        updated_mtime = current_mtime + LAST_MODIFIED_EPSILON
        try:
            self._execute(
                """
                UPDATE files 
                SET last_modified = ?, updated_at = julianday('now')
                WHERE id = ?
                """,
                (updated_mtime, file_id),
            )
            self._commit()
        except Exception as e:
            logger.warning(f"Failed to update last_modified: {e}", exc_info=True)

        # Recreate all records via analyze_file (no dependency on MCP command class)
        try:
            from ....commands.update_indexes_analyzer import analyze_file

            result = analyze_file(
                database=self,
                file_path=Path(abs_path),
                project_id=project_id,
                root_path=Path(root_dir),
                force=True,  # Force update after clear_file_data
            )

            # Check for errors (including syntax errors)
            if result.get("status") in ("error", "syntax_error"):
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "file_path": abs_path,
                    "file_id": file_id,
                    "result": result,  # Include full result for debugging
                }

            # Log result for debugging
            if result.get("status") != "success":
                logger.warning(
                    f"_analyze_file returned unexpected status: {result.get('status')}, "
                    f"result: {result}"
                )

            # After _analyze_file, file_id might have changed if file was re-added
            # Get the current file_id (this is critical - file_id can change after add_file)
            updated_file_record = self.get_file_by_path(abs_path, project_id)
            if updated_file_record:
                new_file_id = updated_file_record["id"]
                if new_file_id != file_id:
                    logger.debug(
                        f"File ID changed after _analyze_file: {file_id} -> {new_file_id} for {abs_path}"
                    )
                file_id = new_file_id
            else:
                # File was not found - this should not happen, but log it
                logger.warning(
                    f"File not found after _analyze_file: {abs_path}, "
                    f"using original file_id: {file_id}"
                )

            # Check if AST and CST were saved by verifying they exist in database
            ast_updated = False
            cst_updated = False
            try:
                ast_record = self._fetchone(
                    "SELECT id FROM ast_trees WHERE file_id = ?", (file_id,)
                )
                ast_updated = ast_record is not None
                if not ast_updated:
                    logger.warning(
                        f"AST not found after _analyze_file for file_id={file_id}, "
                        f"file={abs_path}"
                    )
            except Exception as e:
                logger.warning(f"Error checking AST: {e}", exc_info=True)

            try:
                cst_record = self._fetchone(
                    "SELECT id FROM cst_trees WHERE file_id = ?", (file_id,)
                )
                cst_updated = cst_record is not None
                if not cst_updated:
                    logger.warning(
                        f"CST not found after _analyze_file for file_id={file_id}, "
                        f"file={abs_path}"
                    )
            except Exception as e:
                logger.warning(f"Error checking CST: {e}", exc_info=True)

            # Prefer entities_updated from _analyze_file (sync_file_to_db_atomic);
            # fall back to sum of classes/functions/methods for older callers.
            entities_count = result.get("entities_updated")
            if entities_count is None:
                entities_count = (
                    result.get("classes", 0)
                    + result.get("functions", 0)
                    + result.get("methods", 0)
                )

            # Batch final updates: last_modified, clear indexing_errors, clear needs_chunking
            tid = None
            try:
                disk_mtime = Path(abs_path).stat().st_mtime
                final_ops = [
                    (
                        "UPDATE files SET last_modified = ? WHERE id = ?",
                        (disk_mtime, file_id),
                    ),
                    (
                        "DELETE FROM indexing_errors WHERE project_id = ? AND file_path = ?",
                        (project_id, abs_path),
                    ),
                    (
                        "UPDATE files SET needs_chunking = 0 WHERE id = ?",
                        (file_id,),
                    ),
                ]
                tid = self.begin_transaction()
                self.execute_batch(final_ops, tid)
                self.commit_transaction(tid)
            except Exception as e:
                logger.warning(
                    "Failed batch final updates after reindex for %s: %s",
                    abs_path,
                    e,
                )
                if tid is not None:
                    try:
                        self.rollback_transaction(tid)
                    except Exception:
                        pass

            return {
                "success": True,
                "file_id": file_id,
                "file_path": abs_path,
                "ast_updated": ast_updated,
                "cst_updated": cst_updated,
                "entities_updated": entities_count,
                "result": result,  # Full result from _analyze_file
            }

        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}", exc_info=True)
            err_msg = (
                f"Database foreign key constraint error: {e}"
                if _is_fk_or_integrity_error(e)
                else f"Failed to analyze file: {e}"
            )
            return {
                "success": False,
                "error": err_msg,
                "file_path": abs_path,
                "file_id": file_id,
            }

    except ProjectIdMismatchError:
        # Re-raise project ID mismatch - this is a critical error that should not be swallowed
        raise
    except Exception as e:
        if _is_fk_or_integrity_error(e):
            logger.error(
                "FK/integrity error in update_file_data for %s: %s",
                file_path,
                e,
                exc_info=True,
            )
            return {
                "success": False,
                "error": f"Database foreign key constraint error: {e}",
                "file_path": str(file_path),
            }
        logger.error(
            f"Unexpected error in update_file_data for {file_path}: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "file_path": str(file_path),
        }
