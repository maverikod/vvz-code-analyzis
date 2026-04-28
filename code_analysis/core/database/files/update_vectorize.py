"""
File update: immediate vectorization and combined update+vectorize, remove missing files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


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
            file_id=str(file_id),
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
    update_result_raw = self.update_file_data(
        file_path=file_path,
        project_id=project_id,
        root_dir=root_dir,
    )
    if not isinstance(update_result_raw, dict):
        return {
            "success": False,
            "error": "update_file_data returned non-dict result",
        }
    update_result = update_result_raw

    if not update_result.get("success"):
        return update_result

    # Step 2: Try immediate vectorization
    file_id_raw = update_result.get("file_id")
    if not isinstance(file_id_raw, int):
        return {
            "success": False,
            "error": "update_file_data returned invalid file_id",
        }
    file_id = file_id_raw
    abs_path_raw = update_result.get("file_path")
    abs_path = str(abs_path_raw) if abs_path_raw is not None else file_path

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
