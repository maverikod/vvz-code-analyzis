"""
Module chunking.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from ..database import CodeDatabase

logger = logging.getLogger(__name__)


async def _request_chunking_for_files(
    self, database: "CodeDatabase", files: List[Dict[str, Any]]
) -> int:
    """
    Request chunking for files that need it.

    Args:
        database: Database instance
        files: List of file records that need chunking

    Returns:
        Number of files successfully chunked
    """
    from ..docstring_chunker_pkg import DocstringChunker

    chunker = DocstringChunker(
        database=database,
        svo_client_manager=self.svo_client_manager,
        faiss_manager=self.faiss_manager,
        min_chunk_length=self.min_chunk_length,
    )

    chunked_count = 0

    for file_record in files:
        if self._stop_event.is_set():
            break

        file_start_time = time.time()
        try:
            file_id = file_record["id"]
            file_path = file_record["path"]
            project_id = file_record["project_id"]

            logger.info(f"[FILE {file_id}] Starting chunking for file {file_path}")

            # Check if file exists on disk before attempting to read
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.debug(
                    f"[FILE {file_id}] Skipping missing file (may have been split/refactored): {file_path}"
                )
                continue

            logger.debug(f"[FILE {file_id}] Reading file from disk...")
            try:
                file_content = file_path_obj.read_text(encoding="utf-8")
                logger.debug(f"[FILE {file_id}] File read: {len(file_content)} bytes")
            except Exception as e:
                logger.warning(f"[FILE {file_id}] Failed to read file {file_path}: {e}")
                continue

            # Parse AST
            logger.debug(f"[FILE {file_id}] Parsing AST...")
            try:
                tree = ast.parse(file_content, filename=file_path)
                logger.debug(f"[FILE {file_id}] AST parsed successfully")
            except Exception as e:
                logger.warning(f"[FILE {file_id}] Failed to parse AST for {file_path}: {e}")
                continue

            # Process file with chunker
            logger.info(f"[FILE {file_id}] Processing file with chunker...")
            chunking_start_time = time.time()
            await chunker.process_file(
                file_id=file_id,
                project_id=project_id,
                file_path=file_path,
                tree=tree,
                file_content=file_content,
            )
            chunking_duration = time.time() - chunking_start_time
            logger.info(f"[FILE {file_id}] Chunking completed in {chunking_duration:.3f}s")

            chunked_count += 1
            file_duration = time.time() - file_start_time
            logger.info(f"[FILE {file_id}] Successfully chunked file {file_path} in {file_duration:.3f}s total")

        except Exception as e:
            logger.error(
                f"Error chunking file {file_record.get('path')}: {e}",
                exc_info=True,
            )
            continue

    return chunked_count




def _log_missing_docstring_files(
    self, database: "CodeDatabase", sample: int = 10
) -> None:
    """
    Log files that have no docstring chunks in the database.

    **Important**: Only logs files that are not marked as deleted.
    """
    try:
        rows = database._fetchall(
            """
            SELECT f.path
            FROM files f
            LEFT JOIN code_chunks c
              ON f.id = c.file_id AND c.source_type LIKE '%docstring%'
            WHERE f.project_id = ?
            AND (f.deleted = 0 OR f.deleted IS NULL)
            GROUP BY f.id, f.path
            HAVING COUNT(c.id) = 0
            LIMIT ?
            """,
            (self.project_id, sample),
        )
        if rows:
            paths = [row["path"] for row in rows]
            # Filter out paths that don't exist on disk (may have been split/refactored)
            existing_paths = [p for p in paths if Path(p).exists()]
            if existing_paths:
                logger.warning(
                    f"⚠️  Files with no docstring chunks in DB (sample {len(existing_paths)}/{sample}): {existing_paths}"
                )
            if len(existing_paths) < len(paths):
                missing_count = len(paths) - len(existing_paths)
                logger.debug(
                    f"Skipped {missing_count} missing file(s) in log (may have been split/refactored)"
                )
    except Exception as e:
        logger.warning(f"Failed to log missing docstring files: {e}", exc_info=True)
