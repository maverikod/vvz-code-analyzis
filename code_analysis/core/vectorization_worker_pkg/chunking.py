"""
Module chunking.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import logging
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

        try:
            file_id = file_record["id"]
            file_path = file_record["path"]
            project_id = file_record["project_id"]

            logger.info(f"Requesting chunking for file {file_path} (id={file_id})")

            # Check if file exists on disk before attempting to read
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.debug(
                    f"Skipping missing file (may have been split/refactored): {file_path}"
                )
                continue

            try:
                file_content = file_path_obj.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to read file {file_path}: {e}")
                continue

            # Parse AST
            try:
                tree = ast.parse(file_content, filename=file_path)
            except Exception as e:
                logger.warning(f"Failed to parse AST for {file_path}: {e}")
                continue

            # Process file with chunker
            await chunker.process_file(
                file_id=file_id,
                project_id=project_id,
                file_path=file_path,
                tree=tree,
                file_content=file_content,
            )

            chunked_count += 1
            logger.info(f"Successfully chunked file {file_path}")

        except Exception as e:
            logger.error(
                f"Error chunking file {file_record.get('path')}: {e}",
                exc_info=True,
            )
            continue

    return chunked_count


async def _chunk_missing_docstring_files(
    self, database: "CodeDatabase", limit: int = 3
) -> int:
    """
    Chunk files that currently have no docstring chunks in DB (fallback pass).

    **Important**: Only processes files that:
    - Are not marked as deleted
    - Actually exist on disk
    - Have no docstring chunks yet
    """
    from ..docstring_chunker_pkg import DocstringChunker

    rows = database._fetchall(
        """
        SELECT f.id, f.path, f.project_id
        FROM files f
        LEFT JOIN code_chunks c
          ON f.id = c.file_id AND c.source_type LIKE '%docstring%'
        WHERE f.project_id = ?
        AND (f.deleted = 0 OR f.deleted IS NULL)
        GROUP BY f.id, f.path, f.project_id
        HAVING COUNT(c.id) = 0
        LIMIT ?
        """,
        (self.project_id, limit),
    )
    if not rows:
        return 0

    chunker = DocstringChunker(
        database=database,
        svo_client_manager=self.svo_client_manager,
        faiss_manager=self.faiss_manager,
        min_chunk_length=self.min_chunk_length,
    )

    processed = 0
    for row in rows:
        if self._stop_event.is_set():
            break
        file_id = row["id"]
        file_path = row["path"]
        project_id = row["project_id"]

        # Check if file exists on disk before attempting to process
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.debug(
                f"Skipping missing file (may have been split/refactored): {file_path}"
            )
            continue

        try:
            content = file_path_obj.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=file_path)
            await chunker.process_file(
                file_id=file_id,
                project_id=project_id,
                file_path=file_path,
                tree=tree,
                file_content=content,
            )
            processed += 1
            logger.info(f"Fallback chunked missing-docstring file: {file_path}")
        except Exception as e:
            logger.warning(
                f"Failed fallback chunking for {file_path}: {e}", exc_info=True
            )

    return processed


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
