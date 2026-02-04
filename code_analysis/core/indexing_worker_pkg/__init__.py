"""
Indexing worker package.

Background worker that indexes files (AST, CST, entities, code_content) for fulltext search.
Uses needs_chunking flag; driver clears flag after successful index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .base import IndexingWorker
from .processing import process_cycle
from .runner import run_indexing_worker

IndexingWorker.process_cycle = process_cycle

__all__ = ["IndexingWorker", "run_indexing_worker"]
