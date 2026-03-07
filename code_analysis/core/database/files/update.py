"""
File update: update_file_data (unified update after write).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ...constants import FILE_MODIFICATION_TOLERANCE, LAST_MODIFIED_EPSILON

from .helpers import _last_modified_to_unix

logger = logging.getLogger(__name__)


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
            from ...exceptions import ProjectIdMismatchError

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
                "SELECT id, path FROM files WHERE project_id = ? AND path LIKE ? AND (deleted = 0 OR deleted IS NULL)",
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
        normalized_lm = _last_modified_to_unix(file_record.get("last_modified"))
        if (
            Path(abs_path).exists()
            and normalized_lm is not None
            and abs(normalized_lm - current_mtime) <= FILE_MODIFICATION_TOLERANCE
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
                return {
                    "success": False,
                    "error": f"Failed on skip path: {e}",
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
            return {
                "success": False,
                "error": f"Failed to clear old records: {e}",
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

        # Call _analyze_file to recreate all records
        try:
            # Import from commands package (relative to code_analysis root)
            import sys

            # Add parent directory to path if needed
            code_analysis_root = Path(__file__).parent.parent.parent
            if str(code_analysis_root) not in sys.path:
                sys.path.insert(0, str(code_analysis_root))
            from code_analysis.commands.code_mapper_mcp_command import (
                UpdateIndexesMCPCommand,
            )

            # Create command instance
            update_cmd = UpdateIndexesMCPCommand()

            # Call _analyze_file with force=True to ensure AST/CST are saved
            # even if last_modified matches (after clear_file_data)
            result = update_cmd._analyze_file(
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

            entities_count = (
                result.get("classes", 0)
                + result.get("functions", 0)
                + result.get("methods", 0)
            )

            # After successful full reindex, set last_modified to actual disk mtime
            try:
                disk_mtime = Path(abs_path).stat().st_mtime
                self._execute(
                    "UPDATE files SET last_modified = ? WHERE id = ?",
                    (disk_mtime, file_id),
                )
                self._commit()
            except Exception as e:
                logger.warning(
                    "Failed to update last_modified after reindex for %s: %s",
                    abs_path,
                    e,
                )

            # Clear indexing error for this file on successful write
            try:
                self._execute(
                    "DELETE FROM indexing_errors WHERE project_id = ? AND file_path = ?",
                    (project_id, abs_path),
                )
                self._commit()
            except Exception:
                pass

            # Clear needs_chunking so direct callers (refactor, cst_save_tree, etc.)
            # get same behavior as index_file RPC: file is fully reindexed, no re-chunk request
            try:
                self._execute(
                    "UPDATE files SET needs_chunking = 0 WHERE id = ?",
                    (file_id,),
                )
                self._commit()
            except Exception as e:
                logger.warning(
                    "Failed to clear needs_chunking after reindex for %s: %s",
                    abs_path,
                    e,
                )

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
            return {
                "success": False,
                "error": f"Failed to analyze file: {e}",
                "file_path": abs_path,
                "file_id": file_id,
            }

    except ProjectIdMismatchError:
        # Re-raise project ID mismatch - this is a critical error that should not be swallowed
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in update_file_data for {file_path}: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "file_path": str(file_path),
        }


async def vectorize_file_immediately(
    self,
    file_id: int,
    project_id: str,
    file_path: str,
    svo_client_manager: Optional[Any] = None,
    faiss_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Immediately chunk and vectorize a file after database update.

    This method attempts to vectorize the file immediately. If SVO client
    manager is not available or chunking fails, file is marked for worker
    processing (non-blocking fallback).

    Process:
    1. Check if SVO client manager is available
    2. Read file content and parse AST
    3. Call DocstringChunker.process_file() to chunk and get embeddings
    4. If successful, chunks are saved with embeddings
    5. Worker will add vectors to FAISS in next cycle
    6. If failed, mark file for worker processing

    Args:
        file_id: File ID
        project_id: Project ID
        file_path: File path (absolute)
        svo_client_manager: Optional SVO client manager
        faiss_manager: Optional FAISS manager

    Returns:
        Dictionary with vectorization result:
        {
            "success": bool,
            "chunked": bool,  # True if chunking succeeded
            "chunks_created": int,
            "vectorized": bool,  # True if embeddings were created
            "marked_for_worker": bool,  # True if marked for worker processing
            "error": Optional[str]
        }
    """
    # If no SVO client manager, mark for worker processing
    if not svo_client_manager:
        logger.debug(
            f"No SVO client manager, marking {file_path} for worker processing"
        )
        self.mark_file_needs_chunking(file_path, project_id)
        return {
            "success": True,
            "chunked": False,
            "chunks_created": 0,
            "vectorized": False,
            "marked_for_worker": True,
            "error": None,
        }

    try:
        # Validate file path and project_id using unified normalization
        # Try to get project root from database for validation
        project_root = None
        try:
            db_project = self.get_project(project_id)
            if db_project:
                project_root = Path(db_project["root_path"])
        except Exception as e:
            logger.debug(f"Could not get project root from database: {e}")

        # Use unified path normalization if project_root is available
        if project_root and project_root.exists():
            try:
                from ...path_normalization import normalize_file_path
                from ...exceptions import ProjectIdMismatchError

                normalized = normalize_file_path(file_path, project_root=project_root)
                file_path = normalized.absolute_path

                # Validate project_id matches
                if normalized.project_id != project_id:
                    raise ProjectIdMismatchError(
                        message=(
                            f"Project ID mismatch: file {file_path} belongs to project "
                            f"{normalized.project_id} (from projectid file) "
                            f"but was provided with project_id {project_id}"
                        ),
                        file_project_id=normalized.project_id,
                        db_project_id=project_id,
                    )
            except (ProjectIdMismatchError, FileNotFoundError):
                # Re-raise critical errors
                raise
            except Exception as e:
                # Log but continue with simple normalization
                logger.debug(
                    f"Path normalization failed, using simple normalization: {e}"
                )

        # Read file content
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.warning(f"File not found for vectorization: {file_path}")
            self.mark_file_needs_chunking(file_path, project_id)
            return {
                "success": False,
                "chunked": False,
                "chunks_created": 0,
                "vectorized": False,
                "marked_for_worker": True,
                "error": "File not found",
            }

        file_content = file_path_obj.read_text(encoding="utf-8")

        # Parse AST
        try:
            tree = ast.parse(file_content, filename=file_path)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            self.mark_file_needs_chunking(file_path, project_id)
            return {
                "success": False,
                "chunked": False,
                "chunks_created": 0,
                "vectorized": False,
                "marked_for_worker": True,
                "error": f"Syntax error: {e}",
            }

        # Create chunker and process file
        from ...docstring_chunker_pkg.docstring_chunker import DocstringChunker

        chunker = DocstringChunker(
            database=self,
            svo_client_manager=svo_client_manager,
            faiss_manager=faiss_manager,
            min_chunk_length=30,
        )

        chunks_created = await chunker.process_file(
            file_id=file_id,
            project_id=project_id,
            file_path=file_path,
            tree=tree,
            file_content=file_content,
        )

        logger.info(
            f"Immediately vectorized file {file_path}: "
            f"{chunks_created} chunks created"
        )

        return {
            "success": True,
            "chunked": True,
            "chunks_created": chunks_created,
            "vectorized": chunks_created > 0,  # Chunks have embeddings if created
            "marked_for_worker": False,
            "error": None,
        }

    except Exception as e:
        logger.error(
            f"Error during immediate vectorization of {file_path}: {e}",
            exc_info=True,
        )
        # Fallback: mark for worker processing
        self.mark_file_needs_chunking(file_path, project_id)
        return {
            "success": False,
            "chunked": False,
            "chunks_created": 0,
            "vectorized": False,
            "marked_for_worker": True,
            "error": str(e),
        }


async def update_and_vectorize_file(
    self,
    file_path: str,
    project_id: str,
    root_dir: Path,
    svo_client_manager: Optional[Any] = None,
    faiss_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Update database and immediately vectorize file.

    This is the recommended method for file write operations.
    It combines update_file_data + vectorize_file_immediately.

    Args:
        file_path: File path (relative to root_dir or absolute)
        project_id: Project ID
        root_dir: Project root directory
        svo_client_manager: Optional SVO client manager
        faiss_manager: Optional FAISS manager

    Returns:
        Combined result from update_file_data + vectorize_file_immediately
    """
    # Step 1: Update database
    update_result = self.update_file_data(
        file_path=file_path,
        project_id=project_id,
        root_dir=root_dir,
    )

    if not update_result.get("success"):
        return update_result

    # Step 2: Try immediate vectorization
    file_id = update_result.get("file_id")
    abs_path = update_result.get("file_path")

    if svo_client_manager:
        try:
            vectorization_result = await self.vectorize_file_immediately(
                file_id=file_id,
                project_id=project_id,
                file_path=abs_path,
                svo_client_manager=svo_client_manager,
                faiss_manager=faiss_manager,
            )
        except Exception as e:
            logger.warning(f"Immediate vectorization failed: {e}")
            # Fallback: mark for worker
            self.mark_file_needs_chunking(abs_path, project_id)
            vectorization_result = {
                "chunked": False,
                "marked_for_worker": True,
                "error": str(e),
            }
    else:
        # No SVO manager, mark for worker
        self.mark_file_needs_chunking(abs_path, project_id)
        vectorization_result = {
            "chunked": False,
            "marked_for_worker": True,
        }

    # Combine results
    update_result["vectorization"] = vectorization_result
    return update_result


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
    files = self.get_project_files(project_id)
    removed_files = []
    removed_count = 0
    for file_record in files:
        file_path = Path(file_record["path"])
        if not file_path.exists():
            file_id = file_record["id"]
            logger.info(f"File not found on disk, removing from database: {file_path}")
            self.clear_file_data(file_id)
            self._execute("DELETE FROM files WHERE id = ?", (file_id,))
            removed_files.append(str(file_path))
            removed_count += 1
    if removed_count > 0:
        self._commit()
        logger.info(
            f"Removed {removed_count} missing files from database for project {project_id}"
        )
    return {"removed_count": removed_count, "removed_files": removed_files}
