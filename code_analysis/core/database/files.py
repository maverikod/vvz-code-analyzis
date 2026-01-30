"""
Module files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def get_file_by_path(
    self, path: str, project_id: str, include_deleted: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Get file record by path and project ID.

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized to absolute before querying.

    Args:
        path: File path (will be normalized to absolute)
        project_id: Project ID
        include_deleted: If True, include files marked as deleted (default: False)

    Returns:
        File record as dictionary or None if not found
    """
    from ..path_normalization import normalize_path_simple

    # Normalize path to absolute (Step 5: absolute paths everywhere)
    # Ensure consistent normalization - use resolve() to handle symlinks and relative paths
    abs_path = normalize_path_simple(path)
    
    # Log normalization for debugging path mismatches
    if path != abs_path:
        logger.debug(
            f"[get_file_by_path] Path normalized: {path!r} -> {abs_path!r} | "
            f"project_id={project_id} | include_deleted={include_deleted}"
        )

    if include_deleted:
        row = self._fetchone(
            "SELECT * FROM files WHERE path = ? AND project_id = ?",
            (abs_path, project_id),
        )
    else:
        row = self._fetchone(
            "SELECT * FROM files WHERE path = ? AND project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (abs_path, project_id),
        )
    return row


def add_file(
    self,
    path: str,
    lines: int,
    last_modified: float,
    has_docstring: bool,
    project_id: str,
) -> int:
    """
    Add or update file record. Returns file_id.

    Files are stored with relative_path from project root.
    Files are uniquely identified by (project_id, path).

    **Important**: If file exists in a different project, it will be marked as deleted
    in the old project and all related data will be cleared before adding to the new project.

    Args:
        path: File path (will be normalized to absolute, then converted to relative)
        lines: Number of lines in file
        last_modified: Last modification timestamp
        has_docstring: Whether file has docstring
        project_id: Project ID (UUID4 string)

    Returns:
        File ID
    """
    from ..path_normalization import normalize_file_path, normalize_path_simple
    from ..exceptions import ProjectIdMismatchError, ProjectNotFoundError

    # Get project to find project root and watch_dir_id
    project = self.get_project(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    project_root = Path(project["root_path"]).resolve()
    watch_dir_id = project.get("watch_dir_id")

    # Normalize input path to absolute
    abs_path = normalize_path_simple(path)
    abs_path_obj = Path(abs_path)

    # Calculate relative path from project root
    try:
        relative_path = abs_path_obj.relative_to(project_root)
    except ValueError:
        raise ValueError(
            f"File {abs_path} is not within project root {project_root}"
        )

    # Validate project_id matches (if projectid file exists)
    try:
        normalized = normalize_file_path(abs_path_obj, project_root=project_root)
        if normalized.project_id != project_id:
            raise ProjectIdMismatchError(
                message=(
                    f"Project ID mismatch: file {abs_path} belongs to project "
                    f"{normalized.project_id} (from projectid file) but was provided "
                    f"with project_id {project_id}"
                ),
                file_project_id=normalized.project_id,
                db_project_id=project_id,
            )
    except (ProjectNotFoundError, FileNotFoundError):
        # File doesn't exist or project not found - continue anyway
        pass
    except ProjectIdMismatchError:
        # Re-raise project ID mismatch - this is a critical error
        raise

    # Check if file exists in a different project (by relative_path or path)
    existing_file = self._fetchone(
        """
        SELECT id, project_id FROM files 
        WHERE (relative_path = ? OR path = ?) 
        AND project_id != ? 
        AND (deleted = 0 OR deleted IS NULL) 
        LIMIT 1
        """,
        (str(relative_path), abs_path, project_id),
    )
    
    if existing_file:
        wrong_file_id = existing_file["id"]
        wrong_project_id = existing_file["project_id"]
        
        logger.error(
            f"Data inconsistency detected: file {abs_path} exists in project {wrong_project_id} "
            f"but is being added to project {project_id}. Marking as deleted in old project and clearing related data."
        )
        
        # Clear all related data for the file in wrong project
        try:
            self.clear_file_data(wrong_file_id)
            logger.info(f"Cleared all related data for file_id={wrong_file_id} in project {wrong_project_id}")
            
            # Mark file as deleted in wrong project
            self._execute(
                """
                UPDATE files 
                SET deleted = 1, updated_at = julianday('now')
                WHERE id = ?
                """,
                (wrong_file_id,),
            )
            logger.info(f"Marked file_id={wrong_file_id} as deleted in project {wrong_project_id}")
        except Exception as e:
            logger.error(f"Failed to clear data and mark file as deleted: {e}", exc_info=True)
            # Continue anyway - we'll still add the file to the correct project

    # Check if file already exists in the correct project (by relative_path or path)
    existing_in_correct_project = self._fetchone(
        """
        SELECT id FROM files 
        WHERE project_id = ?
        AND (relative_path = ? OR path = ?)
        """,
        (project_id, str(relative_path), abs_path),
    )
    
    if existing_in_correct_project:
        # Update existing file (including relative_path and watch_dir_id)
        file_id = existing_in_correct_project["id"]
        self._execute(
            """
            UPDATE files 
            SET watch_dir_id = ?, path = ?, relative_path = ?, lines = ?, 
                last_modified = ?, has_docstring = ?, updated_at = julianday('now')
            WHERE id = ?
            """,
            (watch_dir_id, abs_path, str(relative_path), lines, last_modified, has_docstring, file_id),
        )
        # Only commit if not in a transaction (transaction will commit all changes)
        if not self._in_transaction():
            self._commit()
        return file_id
    else:
        # Insert new file with relative_path and watch_dir_id
        self._execute(
            """
                INSERT INTO files
                (project_id, watch_dir_id, path, relative_path, lines, last_modified, has_docstring, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, julianday('now'))
            """,
            (project_id, watch_dir_id, abs_path, str(relative_path), lines, last_modified, has_docstring),
        )
        # Only commit if not in a transaction (transaction will commit all changes)
        if not self._in_transaction():
            self._commit()
        result = self._lastrowid()
        assert result is not None
        return result


def get_file_id(
    self, path: str, project_id: str, include_deleted: bool = False
) -> Optional[int]:
    """
    Get file ID by path and project.

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized to absolute before querying.

    Args:
        path: File path (will be normalized to absolute)
        project_id: Project ID
        include_deleted: If True, include files marked as deleted (default: False)

    Returns:
        File ID or None if not found
    """
    from ..path_normalization import normalize_path_simple

    # Normalize path to absolute (Step 5: absolute paths everywhere)
    abs_path = normalize_path_simple(path)

    if include_deleted:
        row = self._fetchone(
            "SELECT id FROM files WHERE path = ? AND project_id = ?",
            (abs_path, project_id),
        )
    else:
        row = self._fetchone(
            "SELECT id FROM files WHERE path = ? AND project_id = ? AND (deleted = 0 OR deleted IS NULL)",
            (abs_path, project_id),
        )
    return row["id"] if row else None


def get_file_by_id(self, file_id: int) -> Optional[Dict[str, Any]]:
    """Get file record by ID."""
    return self._fetchone("SELECT * FROM files WHERE id = ?", (file_id,))


def delete_file(self, file_id: int) -> None:
    """Delete file and all related records (cascade)."""
    self._execute("DELETE FROM files WHERE id = ?", (file_id,))
    self._commit()


def clear_file_data(self, file_id: int) -> None:
    """
    Clear all data for a file.

    Removes all related data including:
    - classes and their methods
    - functions
    - imports
    - issues
    - usages
    - code_content and FTS index
    - AST trees
    - CST trees
    - code chunks
    - vector index entries

    NOTE: When FAISS is implemented, this method should:
    1. Get all vector_ids from code_chunks for this file_id
    2. Remove these vectors from FAISS index
    3. Then delete from database
    This ensures FAISS stays in sync when files are updated.
    """
    self.delete_entity_cross_ref_for_file(file_id)
    class_rows = self._fetchall("SELECT id FROM classes WHERE file_id = ?", (file_id,))
    class_ids = [row["id"] for row in class_rows]
    content_rows = self._fetchall(
        "SELECT id FROM code_content WHERE file_id = ?", (file_id,)
    )
    content_ids = [row["id"] for row in content_rows]
    if content_ids:
        placeholders = ",".join("?" * len(content_ids))
        self._execute(
            f"DELETE FROM code_content_fts WHERE rowid IN ({placeholders})",
            tuple(content_ids),
        )
    if class_ids:
        placeholders = ",".join("?" * len(class_ids))
        self._execute(
            f"DELETE FROM methods WHERE class_id IN ({placeholders})", tuple(class_ids)
        )
    self._execute("DELETE FROM classes WHERE file_id = ?", (file_id,))
    self._execute("DELETE FROM functions WHERE file_id = ?", (file_id,))
    self._execute("DELETE FROM imports WHERE file_id = ?", (file_id,))
    self._execute("DELETE FROM issues WHERE file_id = ?", (file_id,))
    self._execute("DELETE FROM usages WHERE file_id = ?", (file_id,))
    self._execute("DELETE FROM code_content WHERE file_id = ?", (file_id,))
    self._execute("DELETE FROM ast_trees WHERE file_id = ?", (file_id,))
    self._execute("DELETE FROM cst_trees WHERE file_id = ?", (file_id,))
    vector_rows = self._fetchall(
        "SELECT vector_id FROM code_chunks WHERE file_id = ? AND vector_id IS NOT NULL",
        (file_id,),
    )
    # Store vector_ids for future FAISS cleanup
    _ = [row["vector_id"] for row in vector_rows]
    self._execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))
    entity_rows = self._fetchall(
        "\n            SELECT id FROM classes WHERE file_id = ?\n            UNION\n            SELECT id FROM functions WHERE file_id = ?\n        ",
        (file_id, file_id),
    )
    entity_ids = [row["id"] for row in entity_rows]
    self._execute(
        "DELETE FROM vector_index WHERE entity_type = 'file' AND entity_id = ?",
        (file_id,),
    )
    if entity_ids:
        placeholders = ",".join("?" * len(entity_ids))
        self._execute(
            f"\n                DELETE FROM vector_index\n                WHERE entity_type IN ('class', 'function', 'method')\n                AND entity_id IN ({placeholders})\n            ",
            tuple(entity_ids),
        )
    self._commit()


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
    from ..path_normalization import normalize_path_simple

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
            from ..project_resolution import load_project_id
            from ..exceptions import ProjectIdMismatchError

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
            logger.warning(f"[update_file_data] Failed to validate project_id for {abs_path}: {e}")

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
        # This ensures _analyze_file will process the file and save AST/CST
        # We add a small epsilon to ensure last_modified != file_mtime
        epsilon = 0.001
        updated_mtime = current_mtime + epsilon
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
            from code_analysis.commands.code_mapper_mcp_command import UpdateIndexesMCPCommand

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
            logger.error(
                f"Error analyzing file {file_path}: {e}", exc_info=True
            )
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
        logger.debug(f"No SVO client manager, marking {file_path} for worker processing")
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
                from ..path_normalization import normalize_file_path
                from ..exceptions import ProjectIdMismatchError
                
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
                logger.debug(f"Path normalization failed, using simple normalization: {e}")
        
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
        from ..docstring_chunker_pkg.docstring_chunker import DocstringChunker
        
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


def get_file_summary(self, file_path: str, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Get summary for a file.

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized via get_file_id which normalizes to absolute.
    """
    file_id = self.get_file_id(file_path, project_id)
    if not file_id:
        return None
    file_info = self._fetchone("SELECT * FROM files WHERE id = ?", (file_id,))
    if not file_info:
        return None
    class_count_row = self._fetchone(
        "SELECT COUNT(*) as count FROM classes WHERE file_id = ?", (file_id,)
    )
    file_info["class_count"] = class_count_row["count"] if class_count_row else 0
    function_count_row = self._fetchone(
        "SELECT COUNT(*) as count FROM functions WHERE file_id = ?", (file_id,)
    )
    file_info["function_count"] = (
        function_count_row["count"] if function_count_row else 0
    )
    issue_count_row = self._fetchone(
        "SELECT COUNT(*) as count FROM issues WHERE file_id = ?", (file_id,)
    )
    file_info["issue_count"] = issue_count_row["count"] if issue_count_row else 0
    return file_info


def get_files_needing_chunking(
    self, project_id: str, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get files that need chunking (have docstrings but no chunks, or marked needs_chunking).

    Files are considered needing chunking if:
    - They have docstrings (has_docstring = 1) OR
    - They have classes/functions/methods with docstrings
    - AND (they have no chunks in code_chunks table OR needs_chunking = 1)
    - AND they are NOT marked as deleted (deleted = 0 or NULL)

    **Important**: Deleted files are ALWAYS excluded from this query.

    Args:
        project_id: Project ID
        limit: Maximum number of files to return

    Returns:
        List of file records that need chunking
    """
    return self._fetchall(
        "\n                SELECT DISTINCT f.id, f.project_id, f.path, f.has_docstring\n                FROM files f\n                WHERE f.project_id = ?\n                AND (f.deleted = 0 OR f.deleted IS NULL)\n                AND (\n                    f.has_docstring = 1\n                    OR EXISTS (\n                        SELECT 1 FROM classes c\n                        WHERE c.file_id = f.id AND c.docstring IS NOT NULL AND c.docstring != ''\n                    )\n                    OR EXISTS (\n                        SELECT 1 FROM functions fn\n                        WHERE fn.file_id = f.id AND fn.docstring IS NOT NULL AND fn.docstring != ''\n                    )\n                    OR EXISTS (\n                        SELECT 1 FROM methods m\n                        JOIN classes c ON m.class_id = c.id\n                        WHERE c.file_id = f.id AND m.docstring IS NOT NULL AND m.docstring != ''\n                    )\n                )\n                AND (f.needs_chunking = 1 OR NOT EXISTS (\n                    SELECT 1 FROM code_chunks cc\n                    WHERE cc.file_id = f.id\n                ))\n                ORDER BY f.updated_at DESC\n                LIMIT ?\n                ",
        (project_id, limit),
    )


def mark_file_needs_chunking(self, file_path: str, project_id: str) -> bool:
    """
    Mark a file as needing (re-)chunking by deleting its existing chunks.

    The vectorization worker discovers files to chunk via `get_files_needing_chunking()`,
    which selects files that have docstrings but have **no** rows in `code_chunks`.
    To request re-chunking after a file change, we delete existing chunks so the file
    becomes eligible for that query.

    **Important**: Files with deleted=1 are NOT marked for chunking.

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized to absolute before querying.

    Args:
        file_path: File path (will be normalized to absolute)
        project_id: Project ID

    Returns:
        True if file was found and processed, False otherwise.
    """
    from ..path_normalization import normalize_path_simple

    # Normalize path to absolute (Step 5: absolute paths everywhere)
    abs_path = normalize_path_simple(file_path)

    row = self._fetchone(
        "SELECT id, deleted FROM files WHERE project_id = ? AND path = ?",
        (project_id, abs_path),
    )
    if not row:
        return False

    file_id, is_deleted = row["id"], row["deleted"]

    # Do not mark deleted files for chunking
    if is_deleted:
        logger.debug(f"File {file_path} is marked as deleted, skipping chunking")
        return False

    # Delete chunks so worker will re-chunk and re-vectorize in background.
    self._execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))
    self._execute(
        "UPDATE files SET updated_at = julianday('now') WHERE id = ?",
        (file_id,),
    )
    self._commit()
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

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized to absolute before querying.

    Args:
        file_path: Original file path (will be normalized to absolute and moved)
        project_id: Project ID
        version_dir: Directory where deleted files are stored
        reason: Optional reason for deletion

    Returns:
        True if file was found and marked, False otherwise
    """
    import shutil
    from pathlib import Path

    # Try to get project root from database for validation
    project_root = None
    try:
        db_project = self.get_project(project_id)
        if db_project:
            project_root = Path(db_project["root_path"])
    except Exception as e:
        logger.debug(f"Could not get project root from database: {e}")

    # Use unified path normalization if project_root is available
    abs_path = None
    if project_root and project_root.exists():
        try:
            from ..path_normalization import normalize_file_path
            from ..exceptions import ProjectIdMismatchError
            
            normalized = normalize_file_path(file_path, project_root=project_root)
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
        except (ProjectIdMismatchError, FileNotFoundError):
            # Re-raise critical errors
            raise
        except Exception as e:
            # Log but continue with simple normalization
            logger.debug(f"Path normalization failed, using simple normalization: {e}")
            from ..path_normalization import normalize_path_simple
            abs_path = normalize_path_simple(file_path)
    else:
        # Fallback to simple normalization
        from ..path_normalization import normalize_path_simple
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
        # Still mark as deleted in DB, but don't move file
        self._execute(
            """
            UPDATE files 
            SET deleted = 1, original_path = ?, version_dir = ?, updated_at = julianday('now')
            WHERE id = ?
            """,
            (str(original_path), version_dir, file_id),
        )
        self._commit()
        return True

    # Create version directory structure: {version_dir}/{project_id}/{relative_path}
    version_dir_path = Path(version_dir) / project_id
    # Get relative path from project root (if possible) or use full path
    try:
        # Try to get project root
        project_row = self._fetchone(
            "SELECT root_path FROM projects WHERE id = ?", (project_id,)
        )
        if project_row:
            project_root = Path(project_row["root_path"])
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
    self._execute(
        """
        UPDATE files 
        SET deleted = 1, original_path = ?, version_dir = ?, path = ?, updated_at = julianday('now')
        WHERE id = ?
        """,
        (str(original_path), str(version_dir_path), str(target_path), file_id),
    )
    self._commit()
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

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized to absolute before querying.

    Args:
        file_path: Current file path (in version_dir) or original_path to search (will be normalized to absolute)
        project_id: Project ID

    Returns:
        True if file was found and unmarked, False otherwise
    """
    import shutil
    from pathlib import Path
    from ..path_normalization import normalize_path_simple

    # Normalize path to absolute (Step 5: absolute paths everywhere)
    abs_path = normalize_path_simple(file_path)

    # Try to find by current path (in version_dir) or original_path
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

    Returns files where deleted=1.

    Args:
        project_id: Project ID

    Returns:
        List of deleted file records
    """
    return self._fetchall(
        """
        SELECT * FROM files 
        WHERE project_id = ? AND deleted = 1
        ORDER BY updated_at DESC
        """,
        (project_id,),
    )


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


def get_file_versions(self, file_path: str, project_id: str) -> List[Dict[str, Any]]:
    """
    Get all versions of a file (same path, different last_modified).

    Version = last_modified timestamp.
    Multiple records with same path but different last_modified are considered versions.

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized to absolute before querying.

    Args:
        file_path: File path (will be normalized to absolute)
        project_id: Project ID

    Returns:
        List of file versions sorted by last_modified (newest first)
    """
    from ..path_normalization import normalize_path_simple

    # Normalize path to absolute (Step 5: absolute paths everywhere)
    abs_path = normalize_path_simple(file_path)

    return self._fetchall(
        """
        SELECT * FROM files 
        WHERE project_id = ? AND path = ?
        ORDER BY last_modified DESC
        """,
        (project_id, abs_path),
    )


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
    # Find all files with multiple versions (same path, different last_modified)
    files_with_versions = self._fetchall(
        """
        SELECT path, COUNT(*) as version_count
        FROM files
        WHERE project_id = ?
        GROUP BY path
        HAVING COUNT(*) > 1
        """,
        (project_id,),
    )

    kept_count = 0
    deleted_count = 0
    collapsed_files = []

    for path_row in files_with_versions:
        file_path = path_row["path"]
        collapsed_files.append(file_path)

        # Get all versions for this file
        versions = self.get_file_versions(file_path, project_id)

        if keep_latest:
            # Keep the first one (newest by last_modified DESC)
            delete_versions = versions[1:]
        else:
            # Keep the oldest
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


def update_file_data_atomic(
    self,
    file_path: str,
    project_id: str,
    root_dir: Path,
    source_code: str,
    file_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Atomically update all file data in a transaction.

    IMPORTANT: Must be called within an active transaction.
    This method updates AST, CST, and entities for a file using source_code directly.

    Process:
    1. Find file_id by path
    2. Clear all old records (AST, CST, entities) in transaction
    3. Parse entire file from source_code
    4. Save AST tree in transaction
    5. Save CST tree in transaction
    6. Extract and save entities (classes, functions, methods, imports) in transaction
    7. Return result

    Args:
        file_path: File path (relative to root_dir or absolute)
        project_id: Project ID
        root_dir: Project root directory
        source_code: Full source code of the file (for parsing entire file)

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

    Raises:
        RuntimeError: If not called within an active transaction
    """
    from ..path_normalization import normalize_path_simple
    from ..exceptions import ProjectIdMismatchError

    # Check that we're in a transaction
    if not self._in_transaction():
        raise RuntimeError(
            "update_file_data_atomic must be called within a transaction"
        )

    try:
        # If file_id is provided, use it directly (useful when file was just added in transaction)
        if file_id is not None:
            file_record = self.get_file_by_id(file_id)
            if not file_record:
                return {
                    "success": False,
                    "error": f"File not found in database by file_id: {file_id}",
                    "file_path": file_path,
                }
            abs_path = file_record.get("path") or file_path
        else:
            # Normalize path to absolute
            abs_path = normalize_path_simple(file_path)

            # Get file record
            file_record = self.get_file_by_path(abs_path, project_id)
            if not file_record:
                return {
                    "success": False,
                    "error": f"File not found in database: {file_path}",
                    "file_path": abs_path,
                }

            file_id = file_record["id"]

        # Clear all old records in transaction
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

        # Parse AST from source_code
        try:
            from ..ast_utils import parse_with_comments

            tree = parse_with_comments(source_code, filename=abs_path)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            return {
                "success": False,
                "error": f"Syntax error: {e}",
                "file_path": abs_path,
                "file_id": file_id,
            }
        except Exception as e:
            logger.error(f"Error parsing AST for {file_path}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to parse AST: {e}",
                "file_path": abs_path,
                "file_id": file_id,
            }

        # Calculate file metadata
        import time

        file_mtime = time.time()  # Use current time as mtime for atomic update

        # Save AST tree in transaction
        import hashlib
        import json

        ast_json = json.dumps(ast.dump(tree))
        ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()

        try:
            ast_tree_id = self.save_ast_tree(
                file_id,
                project_id,
                ast_json,
                ast_hash,
                file_mtime,
                overwrite=True,
            )
            logger.debug(f"AST saved with id={ast_tree_id} for file_id={file_id}")
        except Exception as e:
            logger.error(f"Error saving AST for {file_path}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to save AST: {e}",
                "file_path": abs_path,
                "file_id": file_id,
            }

        # Save CST tree in transaction
        cst_hash = hashlib.sha256(source_code.encode()).hexdigest()
        try:
            cst_tree_id = self.save_cst_tree(
                file_id,
                project_id,
                source_code,
                cst_hash,
                file_mtime,
                overwrite=True,
            )
            logger.debug(f"CST saved with id={cst_tree_id} for file_id={file_id}")
        except Exception as e:
            logger.error(f"Error saving CST for {file_path}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to save CST: {e}",
                "file_path": abs_path,
                "file_id": file_id,
            }

        # Extract and save entities in transaction
        # Use helper methods from UpdateIndexesMCPCommand
        from ...commands.code_mapper_mcp_command import UpdateIndexesMCPCommand

        update_cmd = UpdateIndexesMCPCommand()

        classes_added = 0
        functions_added = 0
        methods_added = 0
        imports_added = 0
        usages_added = 0

        class_nodes: Dict[ast.ClassDef, int] = {}

        # Add module-level content to full-text search
        try:
            module_docstring = ast.get_docstring(tree)
        except Exception:
            module_docstring = None
        try:
            self.add_code_content(
                file_id=file_id,
                entity_type="file",
                entity_name=str(abs_path),
                content=source_code,
                docstring=module_docstring,
                entity_id=file_id,
            )
        except Exception as e:
            logger.warning(
                f"Failed to add file content to FTS for {abs_path}: {e}",
                exc_info=True,
            )

        # Extract classes and methods
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                docstring = update_cmd._extract_docstring(node)
                bases: List[str] = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    else:
                        try:
                            bases.append(ast.unparse(base))
                        except AttributeError:
                            bases.append(str(base))
                end_line_class = getattr(node, "end_lineno", node.lineno)
                class_id = self.add_class(
                    file_id, node.name, node.lineno, docstring, bases, end_line=end_line_class
                )
                classes_added += 1
                class_nodes[node] = class_id

                # Store class content for full-text search
                try:
                    class_src = ast.get_source_segment(source_code, node)
                    self.add_code_content(
                        file_id=file_id,
                        entity_type="class",
                        entity_name=node.name,
                        content=class_src or "",
                        docstring=docstring,
                        entity_id=class_id,
                    )
                except Exception as e:
                    logger.debug(
                        f"Failed to add class content to FTS ({abs_path}.{node.name}): {e}",
                        exc_info=True,
                    )

                # Extract methods from class
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_docstring = update_cmd._extract_docstring(item)
                        method_args = update_cmd._extract_args(item)
                        # Calculate cyclomatic complexity
                        try:
                            from ..core.complexity import calculate_complexity

                            method_complexity = calculate_complexity(item)
                        except Exception as e:
                            logger.debug(
                                f"Failed to calculate complexity for method {node.name}.{item.name}: {e}",
                                exc_info=True,
                            )
                            method_complexity = None
                        end_line_method = getattr(item, "end_lineno", item.lineno)
                        method_id = self.add_method(
                            class_id,
                            item.name,
                            item.lineno,
                            method_args,
                            method_docstring,
                            complexity=method_complexity,
                            end_line=end_line_method,
                        )
                        methods_added += 1

                        # Store method content for full-text search
                        try:
                            method_src = ast.get_source_segment(source_code, item)
                            self.add_code_content(
                                file_id=file_id,
                                entity_type="method",
                                entity_name=f"{node.name}.{item.name}",
                                content=method_src or "",
                                docstring=method_docstring,
                                entity_id=method_id,
                            )
                        except Exception as e:
                            logger.debug(
                                f"Failed to add method content to FTS ({abs_path}.{node.name}.{item.name}): {e}",
                                exc_info=True,
                            )

        # Extract top-level functions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_method = False
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.ClassDef):
                        if any(
                            node == item
                            for item in parent.body
                            if isinstance(
                                item, (ast.FunctionDef, ast.AsyncFunctionDef)
                            )
                        ):
                            is_method = True
                            break

                if not is_method:
                    docstring = update_cmd._extract_docstring(node)
                    args = update_cmd._extract_args(node)
                    # Calculate cyclomatic complexity
                    try:
                        from ..core.complexity import calculate_complexity

                        function_complexity = calculate_complexity(node)
                    except Exception as e:
                        logger.debug(
                            f"Failed to calculate complexity for function {node.name}: {e}",
                            exc_info=True,
                        )
                        function_complexity = None
                    end_line_func = getattr(node, "end_lineno", node.lineno)
                    function_id = self.add_function(
                        file_id,
                        node.name,
                        node.lineno,
                        args,
                        docstring,
                        complexity=function_complexity,
                        end_line=end_line_func,
                    )
                    functions_added += 1

                    # Store function content for full-text search
                    try:
                        function_src = ast.get_source_segment(source_code, node)
                        self.add_code_content(
                            file_id=file_id,
                            entity_type="function",
                            entity_name=node.name,
                            content=function_src or "",
                            docstring=docstring,
                            entity_id=function_id,
                        )
                    except Exception as e:
                        logger.debug(
                            f"Failed to add function content to FTS ({abs_path}.{node.name}): {e}",
                            exc_info=True,
                        )

        # Extract imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.add_import(
                        file_id, alias.name, None, "import", node.lineno
                    )
                    imports_added += 1
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    self.add_import(
                        file_id, alias.name, module, "from", node.lineno
                    )
                    imports_added += 1

        # Track usages (function calls, method calls, class instantiations)
        try:
            from ..usage_tracker import UsageTracker

            def add_usage_callback(usage_record: Dict[str, Any]) -> None:
                """Callback to add usage record to database."""
                nonlocal usages_added
                try:
                    self.add_usage(
                        file_id=file_id,
                        line=usage_record["line"],
                        usage_type=usage_record["usage_type"],
                        target_type=usage_record["target_type"],
                        target_name=usage_record["target_name"],
                        target_class=usage_record.get("target_class"),
                        context=usage_record.get("context"),
                    )
                    usages_added += 1
                except Exception as e:
                    logger.debug(
                        f"Failed to add usage for {usage_record.get('target_name')} "
                        f"at line {usage_record.get('line')}: {e}",
                        exc_info=True,
                    )

            usage_tracker = UsageTracker(add_usage_callback)
            usage_tracker.visit(tree)
            logger.debug(
                f"Tracked {usages_added} usages in {abs_path}",
            )
        except Exception as e:
            logger.warning(
                f"Failed to track usages for {abs_path}: {e}",
                exc_info=True,
            )
            # Continue even if usage tracking fails

        # Build entity cross-ref from usages (caller/callee by entity id)
        try:
            from ..entity_cross_ref_builder import build_entity_cross_ref_for_file

            cross_ref_added = build_entity_cross_ref_for_file(
                self, file_id, project_id, source_code
            )
            logger.debug(
                f"Built {cross_ref_added} entity cross-refs for {abs_path}",
            )
        except Exception as e:
            logger.warning(
                f"Failed to build entity cross-ref for {abs_path}: {e}",
                exc_info=True,
            )
            # Do not fail the whole file update

        entities_count = classes_added + functions_added + methods_added

        return {
            "success": True,
            "file_id": file_id,
            "file_path": abs_path,
            "ast_updated": True,
            "cst_updated": True,
            "entities_updated": entities_count,
            "classes": classes_added,
            "functions": functions_added,
            "methods": methods_added,
            "imports": imports_added,
            "usages": usages_added,
        }

    except ProjectIdMismatchError:
        # Re-raise project ID mismatch - this is a critical error
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in update_file_data_atomic for {file_path}: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "file_path": str(file_path),
        }
