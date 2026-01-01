"""
Package initialization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .base import VectorizationWorker
from .processing import process_chunks
from .chunking import (
    _request_chunking_for_files,
    _log_missing_docstring_files,
)
from .runner import run_vectorization_worker
from .watch_dirs import _enqueue_watch_dirs, _refresh_config


VectorizationWorker._refresh_config = _refresh_config
VectorizationWorker._enqueue_watch_dirs = _enqueue_watch_dirs
VectorizationWorker.process_chunks = process_chunks

VectorizationWorker._request_chunking_for_files = _request_chunking_for_files
VectorizationWorker._log_missing_docstring_files = _log_missing_docstring_files

__all__ = ["VectorizationWorker", "run_vectorization_worker"]
