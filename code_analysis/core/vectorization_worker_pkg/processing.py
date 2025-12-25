"""
Processing loop for VectorizationWorker.

This module holds the outer polling loop and delegates heavy batch processing
to `batch_processor.process_embedding_ready_chunks` to keep file sizes small.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

from .batch_processor import process_embedding_ready_chunks

logger = logging.getLogger(__name__)


async def process_chunks(self, poll_interval: int = 30) -> Dict[str, Any]:
    """
    Process non-vectorized chunks in continuous loop with polling interval.

    Runs indefinitely, checking for chunks to vectorize at specified intervals.
    Also requests chunking for files that need chunking.

    Args:
        poll_interval: Interval in seconds between polling cycles (default: 30)

    Returns:
        Dictionary with processing statistics (only when stopped)
    """
    from ..database import CodeDatabase

    if not self.svo_client_manager:
        logger.warning("SVO client manager not available, skipping vectorization")
        return {"processed": 0, "errors": 0}

    if not self.faiss_manager:
        logger.warning("FAISS manager not available, skipping vectorization")
        return {"processed": 0, "errors": 0}

    database = CodeDatabase(self.db_path)
    total_processed = 0
    total_errors = 0
    cycle_count = 0
    self._log_missing_docstring_files(database)

    try:
        logger.info(
            f"Starting continuous vectorization worker for project {self.project_id}, "
            f"poll interval: {poll_interval}s"
        )

        while not self._stop_event.is_set():
            cycle_count += 1
            cycle_start_time = time.time()
            logger.debug(f"[CYCLE #{cycle_count}] Starting vectorization cycle")
            cycle_activity = False

            # Refresh config to sync watch_dirs without restart
            try:
                self._refresh_config()
            except Exception as e:
                logger.error(f"Error refreshing worker config: {e}", exc_info=True)

            # Step 0: enqueue watch_dirs (filesystem scan)
            if getattr(self, "watch_dirs", None):
                try:
                    files_enqueued = await self._enqueue_watch_dirs(database)
                    if files_enqueued > 0:
                        cycle_activity = True
                        logger.info(f"Enqueued {files_enqueued} files from watch_dirs")
                except Exception as e:
                    logger.error(f"Error enqueuing watch_dirs: {e}", exc_info=True)

            # Step 1: Request chunking for files that need it
            try:
                files_to_chunk = database.get_files_needing_chunking(
                    project_id=self.project_id,
                    limit=5,  # Process 5 files per cycle
                )

                if files_to_chunk:
                    logger.info(
                        f"Found {len(files_to_chunk)} files needing chunking, "
                        "requesting chunking..."
                    )
                    chunked_count = await self._request_chunking_for_files(
                        database, files_to_chunk
                    )
                    logger.info(f"Requested chunking for {chunked_count} files")
            except Exception as e:
                logger.error(f"Error requesting chunking: {e}", exc_info=True)

            # Step 2: Assign vector_id in FAISS for chunks that already have embeddings.
            batch_processed, batch_errors = await process_embedding_ready_chunks(
                self, database
            )
            total_processed += batch_processed
            total_errors += batch_errors

            cycle_duration = time.time() - cycle_start_time
            if batch_processed > 0 or batch_errors > 0:
                logger.info(
                    f"[CYCLE #{cycle_count}] Complete in {cycle_duration:.3f}s: "
                    f"{batch_processed} processed, {batch_errors} errors "
                    f"(total: {total_processed} processed, {total_errors} errors)"
                )
                logger.debug(
                    f"[TIMING] [CYCLE #{cycle_count}] Total cycle time: {cycle_duration:.3f}s"
                )
                if batch_processed > 0:
                    cycle_activity = True
            else:
                logger.debug(
                    f"[CYCLE #{cycle_count}] No chunks processed in {cycle_duration:.3f}s"
                )

            # Step 3: Fallback — try to chunk files that have no docstring chunks at all
            if not cycle_activity:
                try:
                    missing_chunked = await self._chunk_missing_docstring_files(
                        database, limit=3
                    )
                    if missing_chunked > 0:
                        cycle_activity = True
                        logger.info(
                            f"Requested chunking for {missing_chunked} files without docstring chunks (fallback)"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to process files without docstring chunks: {e}",
                        exc_info=True,
                    )

            # Wait for next cycle (with early exit check)
            if not self._stop_event.is_set():
                logger.debug(f"Waiting {poll_interval}s before next cycle...")
                for _ in range(poll_interval):
                    if self._stop_event.is_set():
                        break
                    await asyncio.sleep(1)

    finally:
        database.close()

    logger.info(
        f"Vectorization worker stopped: {total_processed} total processed, "
        f"{total_errors} total errors over {cycle_count} cycles"
    )
    return {
        "processed": total_processed,
        "errors": total_errors,
        "cycles": cycle_count,
    }
