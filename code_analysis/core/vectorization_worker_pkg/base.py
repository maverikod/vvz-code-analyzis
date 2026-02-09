"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..svo_client_manager import SVOClientManager


class VectorizationWorker:
    """Worker that transfers already-embedded chunks into FAISS.

    Only processes chunks that already have embedding_vector set in the DB (ready vectors).
    Chunking and embedding are the responsibility of the indexer; this worker only adds
    vectors to FAISS and writes back vector_id. No filesystem access, no watch_dirs."""

    def __init__(
        self,
        db_path: Path,
        faiss_dir: Path,
        vector_dim: int,
        svo_client_manager: Optional["SVOClientManager"] = None,
        batch_size: int = 10,
        retry_attempts: int = 3,
        retry_delay: float = 10.0,
        min_chunk_length: int = 30,
        max_empty_iterations: int = 3,
        empty_delay: float = 5.0,
        max_files_per_pass: int = 30,
        socket_path: Optional[str] = None,
        status_file_path: Optional[Path] = None,
        log_timing: bool = False,
    ):
        """
        Initialize universal vectorization worker.

        Worker operates in universal mode - processes all projects from database.
        Worker works only with database - no filesystem access, no watch_dirs.
        FAISS managers are created dynamically for each project during processing.

        Args:
            db_path: Path to database file
            faiss_dir: Base directory for FAISS index files (project-scoped indexes: {faiss_dir}/{project_id}.bin)
            vector_dim: Vector dimension
            svo_client_manager: SVO client manager for embeddings
            batch_size: Number of chunks to process in one batch
            retry_attempts: Number of retry attempts for vectorization (default: 3)
            retry_delay: Delay in seconds between retry attempts (default: 10.0)
            min_chunk_length: Minimum text length for chunking (default: 30)
            max_empty_iterations: Max consecutive empty iterations before adding delay (default: 3)
            empty_delay: Delay in seconds when no chunks available (default: 5.0)
            max_files_per_pass: Max files to process in one pass (from config; includes re-embed and new files)
            socket_path: Path to database driver socket (for DatabaseClient)
            status_file_path: Optional path to write current_operation/current_file for monitoring
            log_timing: When True, log every operation with duration for bottleneck analysis
        """
        self.db_path = db_path
        self.faiss_dir = Path(faiss_dir)
        self.vector_dim = vector_dim
        self.svo_client_manager = svo_client_manager
        self.batch_size = batch_size
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.min_chunk_length = min_chunk_length
        self.max_empty_iterations = max_empty_iterations
        self.empty_delay = empty_delay
        self.max_files_per_pass = max_files_per_pass
        self.socket_path = socket_path
        self.status_file_path = Path(status_file_path) if status_file_path else None
        self.log_timing = log_timing
        self._stop_event = multiprocessing.Event()

    def stop(self) -> None:
        """Stop the worker."""
        self._stop_event.set()
