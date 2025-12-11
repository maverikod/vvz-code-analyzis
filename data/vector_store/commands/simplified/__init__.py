"""
Simplified API commands for vector store.

This module contains commands that use the new simplified VectorStoreService API.
All commands accept ChunkQuery and SemanticChunk data in serialized form.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .upsert_chunk import UpsertChunkCommand
from .search_chunks import SearchChunksCommand
from .count_chunks import CountChunksCommand
from .delete_chunks import DeleteChunksCommand

__all__ = [
    "UpsertChunkCommand",
    "SearchChunksCommand", 
    "CountChunksCommand",
    "DeleteChunksCommand"
]
