"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ..faiss_manager import FaissIndexManager
    from ..svo_client_manager import SVOClientManager


class VectorizationWorker:
    """Worker for vectorizing code chunks in background process.

    Processes chunks that don't have vector_id yet, gets embeddings,
    adds them to FAISS index, and updates database."""

    def __init__(
        self,
        db_path: Path,
        project_id: str,
        svo_client_manager: Optional["SVOClientManager"] = None,
        faiss_manager: Optional["FaissIndexManager"] = None,
        batch_size: int = 10,
        retry_attempts: int = 3,
        retry_delay: float = 10.0,
        min_chunk_length: int = 30,
        watch_dirs: Optional[List[Path]] = None,
        config_path: Optional[Path] = None,
        dynamic_watch_file: Optional[Path] = None,
    ):
        """
        Initialize vectorization worker.

        Args:
            db_path: Path to database file
            project_id: Project ID to process
            svo_client_manager: SVO client manager for embeddings
            faiss_manager: FAISS index manager
            batch_size: Number of chunks to process in one batch
            retry_attempts: Number of retry attempts for vectorization (default: 3)
            retry_delay: Delay in seconds between retry attempts (default: 10.0)
            min_chunk_length: Minimum text length for chunking (default: 30)
        """
        self.db_path = db_path
        self.project_id = project_id
        self.svo_client_manager = svo_client_manager
        self.faiss_manager = faiss_manager
        self.batch_size = batch_size
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.min_chunk_length = min_chunk_length
        # watch_dirs is stored as list of Path; each entry may have attribute is_dynamic
        self.watch_dirs: List[Path] = []
        for p in watch_dirs or []:
            self.watch_dirs.append(Path(p))
        self.config_path = config_path
        self.dynamic_watch_file = dynamic_watch_file
        self._config_mtime: Optional[float] = None
        self._stop_event = multiprocessing.Event()

    def stop(self) -> None:
        """Stop the worker."""
        self._stop_event.set()
