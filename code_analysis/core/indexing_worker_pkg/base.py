"""
Indexing worker base class.

Worker that processes files with needs_chunking=1 via driver index_file RPC.
No SVO/FAISS; uses DatabaseClient only.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import multiprocessing
import uuid
from pathlib import Path
from typing import Optional


class IndexingWorker:
    """Worker for indexing files (AST, CST, entities, code_content) in background.

    Queries DB for projects with files where needs_chunking=1; for each project
    takes a batch of files and calls index_file_via_driver(database, path, project_id).
    Driver clears needs_chunking after success. No root_dir; paths from DB.
    """

    def __init__(
        self,
        db_path: Path,
        config_path: str,
        batch_size: int = 5,
        poll_interval: int = 30,
        status_file_path: Optional[Path] = None,
        log_timing: bool = False,
    ):
        """Initialize indexing worker.

        Args:
            db_path: Path to database file
            batch_size: Max files per project per cycle (default 5)
            poll_interval: Seconds between cycles (default 30)
            status_file_path: Optional path to write current_operation/current_file for monitoring
            config_path: Absolute path to server ``config.json`` (required for DB client factory).
            log_timing: When True, log [TIMING] lines for bottleneck analysis (log_all_operations_timing).
        """
        self.db_path = db_path
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.status_file_path = Path(status_file_path) if status_file_path else None
        self.config_path = config_path
        self.log_timing = log_timing
        self._stop_event = multiprocessing.Event()
        # Stable for process lifetime: project activity lease (Step 16).
        self._project_activity_owner_id = f"indexing-worker-{uuid.uuid4()}"

    def stop(self) -> None:
        """Stop the worker."""
        self._stop_event.set()
