"""
Test for bug 16b1abbe: process_chunk_only_files must sub-batch a file's
un-vectorized chunks so no single get_embeddings() call exceeds the embed
service's per-request text cap.

Before the fix, process_chunk_only_files sent ALL of a file's un-vectorized
chunks in one get_embeddings() call. The real embed service rejects batches
over 20 texts ("Job command failed: Batch size N exceeds the maximum allowed
(20)"), and that whole-batch exception landed in the outer except BEFORE any
per-chunk assignment/dead-letter accounting ran, so a file with more than the
cap's worth of chunks got error_count += len(chunks) and zero embeddings,
every cycle, forever (infinite retry, never dead-lettered).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from embed_client.exceptions import EmbedClientError

from code_analysis.core.vectorization_worker_pkg.batch_processor import (
    process_chunk_only_files,
)

_CAP = 20
_TOTAL_CHUNKS = 25


class _FakeDatabase:
    """Fake database with one file that has _TOTAL_CHUNKS un-vectorized chunks."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        """Initialize the instance."""
        self.chunks = chunks
        self.logical_writes: list[dict[str, Any]] = []
        self.batch_writes: list[list[Any]] = []

    def execute(self, sql: str, params: tuple, **_kwargs: Any) -> dict[str, Any]:
        """Execute the command."""
        if "GROUP BY cc.file_id" in sql:
            return {
                "data": [
                    {
                        "file_id": "file-1",
                        "file_path": "big_file.py",
                        "cnt": len(self.chunks),
                    }
                ]
            }
        return {"data": self.chunks}

    def execute_logical_write_operation(self, payload: dict[str, Any]) -> None:
        """Return execute logical write operation."""
        self.logical_writes.append(payload)

    def execute_batch(self, ops: list[Any], **_kwargs: Any) -> None:
        """Return execute batch."""
        self.batch_writes.append(ops)


class _CapEnforcingSvoManager:
    """SVO manager double that mimics the real embed service's request cap.

    Raises EmbedClientError for any get_embeddings() call with more than
    _CAP texts (matching the real service's rejection message); succeeds
    (assigns .embedding/.embedding_model) for calls at or under the cap.
    """

    def __init__(self, cap: int = _CAP) -> None:
        """Initialize the instance."""
        self.cap = cap
        self._embedding_available = True
        self._embedding_max_batch_size = cap
        self.call_sizes: list[int] = []

    async def get_embeddings(self, chunks: list[Any]) -> list[Any]:
        """Return get embeddings, rejecting batches over the configured cap."""
        self.call_sizes.append(len(chunks))
        if len(chunks) > self.cap:
            raise EmbedClientError(
                f"Job command failed: Batch size {len(chunks)} exceeds the "
                f"maximum allowed ({self.cap})"
            )
        for chunk in chunks:
            chunk.embedding = [1.0]
            chunk.embedding_model = "fake-model"
        return chunks


def _worker(manager: Any) -> SimpleNamespace:
    """Return a minimal worker double for process_chunk_only_files."""
    return SimpleNamespace(
        chunk_only=True,
        svo_client_manager=manager,
        project_id="project-1",
        max_files_per_pass=30,
        docs_markdown_embeddings_enabled=True,
        _stop_event=MagicMock(is_set=MagicMock(return_value=False)),
    )


@pytest.mark.asyncio
async def test_oversized_file_is_fully_embedded_via_capped_subbatches() -> None:
    """A 25-chunk file is fully embedded via >=2 calls, each <= the 20-text cap.

    FIXED behavior (bug 16b1abbe): before the fix this asserted the opposite
    of what actually happened (error_count == 25, zero embeddings, one
    oversized 25-text call) and failed RED against the unfixed code.
    """
    chunks = [
        {"id": f"c{i}", "chunk_text": f"chunk text {i}"} for i in range(_TOTAL_CHUNKS)
    ]
    db = _FakeDatabase(chunks)
    manager = _CapEnforcingSvoManager(cap=_CAP)

    updated, errors = await process_chunk_only_files(_worker(manager), db)

    assert (updated, errors) == (_TOTAL_CHUNKS, 0)
    assert len(manager.call_sizes) >= 2, (
        f"expected >= 2 embed calls to stay under cap={_CAP}, got "
        f"{manager.call_sizes!r}"
    )
    assert all(size <= _CAP for size in manager.call_sizes), (
        f"a sub-batch exceeded the cap={_CAP}: {manager.call_sizes!r}"
    )
    assert sum(manager.call_sizes) == _TOTAL_CHUNKS

    # All 25 chunks committed in one atomic UPDATE batch for the file.
    assert len(db.logical_writes) == 1
    ops = db.logical_writes[0]["batches"][0]
    assert len(ops) == _TOTAL_CHUNKS
