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

from code_analysis.core.docs_indexing_defaults import DOCS_INDEX_FILE_SUFFIXES
from code_analysis.core.file_identity import absolute_path_for_indexed_file
from code_analysis.core.resolve_indexed_file_path import resolve_indexed_file_path
from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE, WHERE_FILES_ACTIVE_F
from code_analysis.core.worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY

if TYPE_CHECKING:
    from ..database_client.client import DatabaseClient

logger = logging.getLogger(__name__)


async def _request_chunking_for_files(
    self, database: "DatabaseClient", files: List[Dict[str, Any]]
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

    from .batch_processor import process_embedding_ready_chunks
    from .timing_log import log_operation_timing

    chunker = DocstringChunker(
        database=database,
        svo_client_manager=self.svo_client_manager,
        faiss_manager=self.faiss_manager,
        min_chunk_length=self.min_chunk_length,
        log_timing=getattr(self, "log_timing", False),
        docs_markdown_embeddings_enabled=getattr(
            self, "docs_markdown_embeddings_enabled", True
        ),
    )

    chunked_count = 0

    for file_record in files:
        if self._stop_event.is_set():
            break

        file_start_time = time.time()
        try:
            file_id = file_record["id"]
            project_id = file_record["project_id"]

            file_path_obj = resolve_indexed_file_path(file_record)
            if file_path_obj is None:
                logger.info(
                    "[FILE %s] Skipping chunking: no file on disk after resolving path "
                    "from DB (watch_dir + project + relative_path / root_path / stored path)",
                    file_id,
                )
                continue

            file_path = str(file_path_obj)
            logger.info(f"[FILE {file_id}] Starting chunking for file {file_path}")

            # Check that file and project still exist in DB and file is not marked deleted
            try:
                check_result = database.execute(
                    "SELECT 1 FROM files WHERE id = ? AND project_id = ? AND "
                    + WHERE_FILES_ACTIVE,
                    (file_id, project_id),
                    priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                )
                check_data = (
                    check_result.get("data", [])
                    if isinstance(check_result, dict)
                    else []
                )
                if not check_data:
                    logger.debug(
                        f"[FILE {file_id}] Skipping: file or project no longer exists or file is marked deleted: {file_path}"
                    )
                    continue
            except Exception as e:
                logger.warning(
                    f"[FILE {file_id}] Failed to verify file/project in DB: {e}, skipping"
                )
                continue

            logger.debug(f"[FILE {file_id}] Reading file from disk...")
            try:
                t0_read = time.time()
                file_content = file_path_obj.read_text(encoding="utf-8")
                log_operation_timing(
                    getattr(self, "log_timing", False),
                    logger,
                    "file_read",
                    time.time() - t0_read,
                    file_id=file_id,
                    bytes=len(file_content),
                )
                logger.debug(f"[FILE {file_id}] File read: {len(file_content)} bytes")
            except Exception as e:
                logger.warning(f"[FILE {file_id}] Failed to read file {file_path}: {e}")
                continue

            if Path(file_path).suffix.lower() in DOCS_INDEX_FILE_SUFFIXES:
                logger.debug(
                    f"[FILE {file_id}] Documentation file ({Path(file_path).suffix}): "
                    "skipping ast.parse; routing to DocBlock chunker process_markdown_document"
                )
                chunking_start_time = time.time()
                await chunker.process_markdown_document(
                    file_id=str(file_id),
                    project_id=project_id,
                    file_path=file_path,
                    text=file_content,
                )
                chunking_duration = time.time() - chunking_start_time
                log_operation_timing(
                    getattr(self, "log_timing", False),
                    logger,
                    "chunker_process_markdown",
                    chunking_duration,
                    file_id=file_id,
                )
                try:
                    database.execute(
                        "UPDATE files SET needs_chunking = 0 WHERE id = ?",
                        (file_id,),
                        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                    )
                except Exception as e:
                    logger.debug(
                        f"[FILE {file_id}] Could not clear needs_chunking: {e}"
                    )
                chunked_count += 1
                await process_embedding_ready_chunks(self, database)
                continue

            # Parse AST (Python / .pyi only)
            logger.debug(f"[FILE {file_id}] Parsing AST...")
            try:
                t0_ast = time.time()
                tree = ast.parse(file_content, filename=file_path)
                log_operation_timing(
                    getattr(self, "log_timing", False),
                    logger,
                    "ast_parse",
                    time.time() - t0_ast,
                    file_id=file_id,
                )
                logger.debug(f"[FILE {file_id}] AST parsed successfully")
            except Exception as e:
                logger.warning(
                    f"[FILE {file_id}] Failed to parse AST for {file_path}: {e}"
                )
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
            log_operation_timing(
                getattr(self, "log_timing", False),
                logger,
                "chunker_process_file",
                chunking_duration,
                file_id=file_id,
            )
            logger.info(
                f"[FILE {file_id}] Chunking completed in {chunking_duration:.3f}s"
            )

            # Clear needs_chunking so file is not re-selected until next change
            try:
                t0_clear = time.time()
                database.execute(
                    "UPDATE files SET needs_chunking = 0 WHERE id = ?",
                    (file_id,),
                    priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
                )
                log_operation_timing(
                    getattr(self, "log_timing", False),
                    logger,
                    "DB_UPDATE_needs_chunking",
                    time.time() - t0_clear,
                    file_id=file_id,
                )
            except Exception as e:
                logger.debug(f"[FILE {file_id}] Could not clear needs_chunking: {e}")

            chunked_count += 1
            file_duration = time.time() - file_start_time
            logger.info(
                f"[FILE {file_id}] Successfully chunked file {file_path} in {file_duration:.3f}s total"
            )

            # Step 5 (mandatory): add to index and batch update after writing to DB
            logger.info(
                f"[STEP] Step 5 after file: process_embedding_ready_chunks (project={project_id}, file_id={file_id})"
            )
            t0_step5 = time.time()
            await process_embedding_ready_chunks(self, database)
            log_operation_timing(
                getattr(self, "log_timing", False),
                logger,
                "Step5_after_file",
                time.time() - t0_step5,
                file_id=file_id,
                project_id=project_id,
            )

        except Exception as e:
            logger.error(
                f"Error chunking file {file_record.get('path')}: {e}",
                exc_info=True,
            )
            continue

    return chunked_count


def _log_missing_docstring_files(
    self, database: "DatabaseClient", sample: int = 10
) -> None:
    """
    Log files that have no docstring chunks in the database.

    **Important**: Only logs files that are not marked as deleted.
    """
    try:
        rows_result = database.execute(
            f"""
            SELECT f.path, f.relative_path, p.root_path AS project_root_path
            FROM files f
            INNER JOIN projects p ON p.id = f.project_id
            LEFT JOIN code_chunks c
              ON f.id = c.file_id AND c.source_type LIKE '%docstring%'
            WHERE f.project_id = ?
            AND {WHERE_FILES_ACTIVE_F}
            GROUP BY f.id, f.path, f.relative_path, p.root_path
            HAVING COUNT(c.id) = 0
            LIMIT ?
            """,
            (self.project_id, sample),
            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
        )
        # Extract data from result - execute() returns dict with "data" key
        rows = rows_result.get("data", []) if isinstance(rows_result, dict) else []
        if rows:
            paths = [
                absolute_path_for_indexed_file(row["project_root_path"], row)
                for row in rows
            ]
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
