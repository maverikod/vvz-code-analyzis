"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..faiss_manager import FaissIndexManager
    from ..svo_client_manager import SVOClientManager


class DocstringChunker:
    """Extracts docstrings and comments with AST node binding, chunks them, and saves to database."""

    def __init__(
        self,
        database,
        svo_client_manager: Optional["SVOClientManager"] = None,
        faiss_manager: Optional["FaissIndexManager"] = None,
        min_chunk_length: int = 30,
    ):
        """
        Initialize docstring chunker.

        Args:
            database: CodeDatabase instance
            svo_client_manager: SVO client manager for chunking and embedding
            faiss_manager: FAISS index manager for vector storage
            min_chunk_length: Minimum text length for chunking (default: 30)
        """
        self.database = database
        self.svo_client_manager = svo_client_manager
        self.faiss_manager = faiss_manager
        self.min_chunk_length = min_chunk_length
        # Binding levels: 0 ok, 1 file, 2 class, 3 method/function, 4 node, 5 line
        self.binding_levels = {
            "file": 1,
            "class": 2,
            "method": 3,
            "function": 3,
            "node": 4,
            "line": 5,
        }
