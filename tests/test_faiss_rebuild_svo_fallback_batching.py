"""faiss_manager_rebuild's SVO fallback fetch must batch, not go per-chunk.

Regression for planner card b3fced06 (vectorizer clients audit tail). The
2026-07-08 refactor (commit 4b91f5f1) unified the throwaway per-call chunk
adapters into a shared ``EmbeddingInput`` and batched
``duplicate_detector_semantic``'s embedding calls, but left
``faiss_manager_rebuild.py``'s SVO fallback path (used when a chunk's
DB-stored ``embedding_vector`` is missing or fails to parse as JSON) issuing
one ``svo_client_manager.get_embeddings([...])`` call per chunk from inside
``rebuild_from_database_impl``'s main loop - a genuine per-item embed pattern
matching the original audit finding.

The fix collects every chunk needing the SVO fallback across the whole
rebuild pass and fetches them with a single batched
``svo_client_manager.get_embeddings(...)`` call
(``_fetch_embeddings_from_svo_batch``), then scatters the results back before
adding vectors to the FAISS index - mirroring the pattern
``duplicate_detector_semantic.find_semantic_duplicates_impl`` already uses
for its primary (non-fallback) path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import pytest

from code_analysis.core import faiss_manager_rebuild


class _FakeManager:
    """Minimal FaissIndexManager stand-in."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self.index = None
        self.added: List[Tuple[Any, int]] = []
        self.created = False
        self.saved = False

    def _create_index(self) -> None:
        """Return create index."""
        self.created = True

    def add_vector(self, embedding: Any, vector_id: int) -> None:
        """Return add vector."""
        self.added.append((embedding, vector_id))

    def save_index(self) -> None:
        """Return save index."""
        self.saved = True


class _FakeDatabase:
    """Minimal DatabaseClient stand-in: serves one page of chunks, then none."""

    def __init__(self, chunks: List[Dict[str, Any]]) -> None:
        """Initialize the instance."""
        self._chunks = chunks
        self._served = False
        self.update_calls: List[Tuple[str, Tuple[Any, ...]]] = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        """Return execute."""
        s = sql.strip().upper()
        if s.startswith("WITH RANKED") or s.startswith(
            "UPDATE CODE_CHUNKS SET EMBEDDING_VECTOR"
        ):
            if s.startswith("UPDATE CODE_CHUNKS SET EMBEDDING_VECTOR"):
                self.update_calls.append((sql, tuple(params or ())))
            return {"data": []}
        if s.startswith("SELECT"):
            if self._served:
                return {"data": []}
            self._served = True
            return {"data": list(self._chunks)}
        return {"data": []}


class _FakeSvoManager:
    """Records every ``get_embeddings`` call; returns a fixed embedding per input."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self.calls: List[List[Any]] = []

    async def get_embeddings(self, chunks: Any, **kwargs: Any) -> List[Any]:
        """Return get embeddings."""
        chunks_list = list(chunks)
        self.calls.append(chunks_list)
        for ch in chunks_list:
            ch.embedding = [0.1, 0.2, 0.3]
            ch.embedding_model = "test-model"
        return chunks_list


def _chunk_row(
    chunk_id: str,
    vector_id: int,
    *,
    embedding_vector_json: Optional[str] = "not-json{{{",
) -> Dict[str, Any]:
    """Return a code_chunks row dict shaped like ``_fetch_chunks_for_rebuild``'s SELECT."""
    return {
        "id": chunk_id,
        "chunk_text": f"text for {chunk_id}",
        "vector_id": vector_id,
        "embedding_model": None,
        "embedding_vector": embedding_vector_json,
    }


@pytest.mark.asyncio
async def test_svo_fallback_uses_single_batched_call_for_multiple_chunks() -> None:
    """N chunks needing SVO fallback -> exactly one get_embeddings call for all N."""
    chunks = [_chunk_row(f"chunk-{i}", i) for i in range(5)]
    manager = _FakeManager()
    database = _FakeDatabase(chunks)
    svo = _FakeSvoManager()

    loaded = await faiss_manager_rebuild.rebuild_from_database_impl(
        manager, database, svo, project_id=None
    )

    assert loaded == 5
    assert (
        len(svo.calls) == 1
    ), f"expected exactly one batched call; got {len(svo.calls)}"
    assert len(svo.calls[0]) == 5
    assert len(manager.added) == 5
    assert manager.saved is True
    # Every recovered embedding is saved back to the DB (one UPDATE per chunk).
    assert len(database.update_calls) == 5


@pytest.mark.asyncio
async def test_db_resolved_chunks_skip_svo_entirely() -> None:
    """Chunks with a valid stored embedding_vector never touch SVO."""
    embedding_json = json.dumps([0.5, 0.6])
    chunks = [
        _chunk_row(f"chunk-{i}", i, embedding_vector_json=embedding_json)
        for i in range(3)
    ]
    manager = _FakeManager()
    database = _FakeDatabase(chunks)
    svo = _FakeSvoManager()

    loaded = await faiss_manager_rebuild.rebuild_from_database_impl(
        manager, database, svo, project_id=None
    )

    assert loaded == 3
    assert svo.calls == []
    assert database.update_calls == []


@pytest.mark.asyncio
async def test_mixed_db_and_svo_fallback_batches_only_the_fallback_subset() -> None:
    """Mix of DB-resolved and SVO-fallback chunks -> one batched call for the fallback subset only."""
    embedding_json = json.dumps([0.5, 0.6])
    chunks = [
        _chunk_row("db-1", 0, embedding_vector_json=embedding_json),
        _chunk_row("svo-1", 1, embedding_vector_json=None),
        _chunk_row("db-2", 2, embedding_vector_json=embedding_json),
        _chunk_row("svo-2", 3, embedding_vector_json="corrupt{{"),
    ]
    manager = _FakeManager()
    database = _FakeDatabase(chunks)
    svo = _FakeSvoManager()

    loaded = await faiss_manager_rebuild.rebuild_from_database_impl(
        manager, database, svo, project_id=None
    )

    assert loaded == 4
    assert len(svo.calls) == 1
    assert len(svo.calls[0]) == 2  # only svo-1 and svo-2
    assert len(manager.added) == 4


@pytest.mark.asyncio
async def test_svo_batch_failure_reports_missing_without_raising() -> None:
    """The whole-batch SVO call failing -> those chunks are reported missing, no crash."""

    class _FailingSvo:
        """Represent FailingSvo."""

        async def get_embeddings(self, chunks: Any, **kwargs: Any) -> List[Any]:
            """Return get embeddings."""
            raise RuntimeError("service unavailable")

    chunks = [_chunk_row("chunk-a", 0), _chunk_row("chunk-b", 1)]
    manager = _FakeManager()
    database = _FakeDatabase(chunks)

    loaded = await faiss_manager_rebuild.rebuild_from_database_impl(
        manager, database, _FailingSvo(), project_id=None
    )

    assert loaded == 0
    assert manager.added == []
    assert manager.saved is True


def test_embedding_input_still_the_shared_adapter() -> None:
    """faiss_manager_rebuild still uses the shared EmbeddingInput, not a private adapter."""
    import inspect

    src = inspect.getsource(faiss_manager_rebuild)
    assert "EmbeddingInput" in src
    assert "class _TmpChunk" not in src
