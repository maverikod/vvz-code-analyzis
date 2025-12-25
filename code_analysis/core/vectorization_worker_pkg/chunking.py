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
    from ..docstring_chunker import DocstringChunker

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

            try:
                file_content = Path(file_path).read_text(encoding="utf-8")
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
    """
    from ..docstring_chunker import DocstringChunker

    assert database.conn is not None
    cursor = database.conn.cursor()
    cursor.execute(
        """
        SELECT f.id, f.path, f.project_id
        FROM files f
        LEFT JOIN code_chunks c
          ON f.id = c.file_id AND c.source_type LIKE '%docstring%'
        WHERE f.project_id = ?
        GROUP BY f.id, f.path, f.project_id
        HAVING COUNT(c.id) = 0
        LIMIT ?
        """,
        (self.project_id, limit),
    )
    rows = cursor.fetchall()
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
        file_id = row[0]
        file_path = row[1]
        project_id = row[2]

        try:
            content = Path(file_path).read_text(encoding="utf-8")
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
    """
    try:
        assert database.conn is not None
        cursor = database.conn.cursor()
        cursor.execute(
            """
            SELECT f.path
            FROM files f
            LEFT JOIN code_chunks c
              ON f.id = c.file_id AND c.source_type LIKE '%docstring%'
            WHERE f.project_id = ?
            GROUP BY f.id, f.path
            HAVING COUNT(c.id) = 0
            LIMIT ?
            """,
            (self.project_id, sample),
        )
        rows = cursor.fetchall()
        if rows:
            paths = [row[0] for row in rows]
            logger.warning(
                f"⚠️  Files with no docstring chunks in DB (sample {len(paths)}/{sample}): {paths}"
            )
    except Exception as e:
        logger.warning(f"Failed to log missing docstring files: {e}", exc_info=True)
