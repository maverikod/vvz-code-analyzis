"""
Package initialization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .base import DocstringChunker

from .extract import _find_node_context, extract_docstrings_and_comments
from .processing import (
    _chunk_grouped_items,
    _process_short_items_grouped,
    _process_single_item,
    process_file,
)
from .storage import _save_chunks, close

DocstringChunker._find_node_context = _find_node_context
DocstringChunker.extract_docstrings_and_comments = extract_docstrings_and_comments

DocstringChunker.process_file = process_file
DocstringChunker._process_single_item = _process_single_item
DocstringChunker._process_short_items_grouped = _process_short_items_grouped
DocstringChunker._chunk_grouped_items = _chunk_grouped_items

DocstringChunker._save_chunks = _save_chunks
DocstringChunker.close = close

__all__ = ["DocstringChunker"]
