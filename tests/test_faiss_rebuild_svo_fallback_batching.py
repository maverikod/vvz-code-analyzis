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
from typing import Any, Dict, List, Optional, Tuple, cast

import numpy as np
import pytest

from code_analysis.core import faiss_manager_rebuild
from code_analysis.core.database_client.client import DatabaseClient


def _embedding_for_text(text: str) -> List[float]:
    """Deterministic, content-derived fake embedding - distinct per distinct text.

    Encoding by the input's own text (not just its position within a batch)
    means a positional ``zip`` misalignment inside
    ``_fetch_embeddings_from_svo_batch`` produces an embedding that decodes
    back to the WRONG chunk's text - detectable by comparing the embedding
    landed at a given ``vector_id`` against ``_embedding_for_text`` of THAT
    chunk's own text, rather than any embedding at all.
    """
    digest = sum(ord(c) for c in text)
    return [float(digest % 97), float(digest % 131), float(len(text))]


def _added_embedding(manager: "_FakeManager", vector_id: int) -> List[float]:
    """Return the embedding ``manager.add_vector`` recorded for ``vector_id``."""
    matches = [emb for emb, vid in manager.added if vid == vector_id]
    assert (
        len(matches) == 1
    ), f"expected exactly one add_vector call for vector_id={vector_id}"
    emb = matches[0]
    if isinstance(emb, np.ndarray):
        return [float(x) for x in emb.tolist()]
    return [float(x) for x in emb]


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
    """Records every ``get_embeddings`` call; returns a DISTINCT embedding per input.

    Embeddings are derived from each input's own text (``_embedding_for_text``),
    not from call position, so a positional zip misalignment inside the caller
    is detectable rather than masked by every input getting the same vector.
    """

    def __init__(self) -> None:
        """Initialize the instance."""
        self.calls: List[List[Any]] = []

    async def get_embeddings(self, chunks: Any, **kwargs: Any) -> List[Any]:
        """Return get embeddings."""
        chunks_list = list(chunks)
        self.calls.append(chunks_list)
        for ch in chunks_list:
            ch.embedding = _embedding_for_text(ch.text)
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
        manager, cast(DatabaseClient, database), svo, project_id=None
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
    # Each vector_id received ITS OWN chunk's embedding, not a neighbor's
    # (catches a positional zip misalignment in _fetch_embeddings_from_svo_batch).
    for i in range(5):
        assert _added_embedding(manager, i) == _embedding_for_text(
            f"text for chunk-{i}"
        )


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
        manager, cast(DatabaseClient, database), svo, project_id=None
    )

    assert loaded == 3
    assert svo.calls == []
    assert database.update_calls == []


@pytest.mark.asyncio
async def test_mixed_db_and_svo_fallback_batches_only_the_fallback_subset() -> None:
    """Mix of DB-resolved and SVO-fallback chunks -> one batched call for the fallback subset only."""
    # 0.5 / 0.25 are exact in float32 - avoids round-trip drift (e.g. 0.6 ->
    # 0.6000000238418579) breaking the exact-value assertions below.
    embedding_json = json.dumps([0.5, 0.25])
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
        manager, cast(DatabaseClient, database), svo, project_id=None
    )

    assert loaded == 4
    assert len(svo.calls) == 1
    assert len(svo.calls[0]) == 2  # only svo-1 and svo-2
    assert len(manager.added) == 4
    # Each vector_id landed with the embedding of ITS OWN source chunk - DB-resolved
    # chunks keep their stored vector, SVO-fallback chunks get their own SVO result
    # (not a neighbor's - this is what a positional zip misalignment would break).
    assert _added_embedding(manager, 0) == [0.5, 0.25]  # db-1
    assert _added_embedding(manager, 1) == _embedding_for_text("text for svo-1")
    assert _added_embedding(manager, 2) == [0.5, 0.25]  # db-2
    assert _added_embedding(manager, 3) == _embedding_for_text("text for svo-2")


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
        manager, cast(DatabaseClient, database), _FailingSvo(), project_id=None
    )

    assert loaded == 0
    assert manager.added == []
    assert manager.saved is True


@pytest.mark.asyncio
async def test_svo_partial_none_embedding_counts_as_missing() -> None:
    """One item in the batch response has embedding=None -> only it is missing.

    Simulates SVO returning a full-length response (no zip truncation) where a
    single item nonetheless carries no embedding (e.g. per-item content
    rejection). The other chunk in the same batch must still land at its own,
    correct vector_id - proving results are matched per-item, not just
    all-or-nothing for the whole batch.
    """

    class _PartialNoneSvo:
        """Returns one real embedding and one ``embedding=None`` per call."""

        async def get_embeddings(self, chunks: Any, **kwargs: Any) -> List[Any]:
            """Return get embeddings."""
            chunks_list = list(chunks)
            assert len(chunks_list) == 2
            chunks_list[0].embedding = _embedding_for_text(chunks_list[0].text)
            chunks_list[0].embedding_model = "test-model"
            chunks_list[1].embedding = None  # e.g. rejected by the service
            return chunks_list

    chunks = [
        _chunk_row("svo-ok", 0, embedding_vector_json=None),
        _chunk_row("svo-none", 1, embedding_vector_json=None),
    ]
    manager = _FakeManager()
    database = _FakeDatabase(chunks)

    loaded = await faiss_manager_rebuild.rebuild_from_database_impl(
        manager, cast(DatabaseClient, database), _PartialNoneSvo(), project_id=None
    )

    assert loaded == 1
    assert len(manager.added) == 1
    assert _added_embedding(manager, 0) == _embedding_for_text("text for svo-ok")
    assert all(vid != 1 for _emb, vid in manager.added)  # svo-none never added
    # Only the successful chunk's embedding is persisted back to the DB.
    assert len(database.update_calls) == 1
    assert database.update_calls[0][1][-1] == "svo-ok"


@pytest.mark.asyncio
async def test_svo_fewer_results_than_requested_truncates_safely() -> None:
    """SVO response shorter than the request (zip truncation) drops the tail safely.

    If ``_fetch_embeddings_from_svo_batch`` ever regresses to relying on
    ``zip(items, chunks_with_emb)`` silently truncating to the shorter
    sequence, the LAST requested chunk(s) would be dropped without error.
    This pins that: 3 chunks requested, only 2 embeddings returned -> exactly
    the first 2 (matched pairwise, each with ITS OWN embedding) succeed, the
    3rd is reported missing, and nothing crashes or misattributes an
    embedding to the wrong vector_id.
    """

    class _TruncatingSvo:
        """Returns fewer items than requested (drops the tail)."""

        async def get_embeddings(self, chunks: Any, **kwargs: Any) -> List[Any]:
            """Return get embeddings."""
            chunks_list = list(chunks)
            assert len(chunks_list) == 3
            for ch in chunks_list:
                ch.embedding = _embedding_for_text(ch.text)
                ch.embedding_model = "test-model"
            return chunks_list[:2]  # drop the 3rd - shorter than requested

    chunks = [
        _chunk_row("svo-1st", 0, embedding_vector_json=None),
        _chunk_row("svo-2nd", 1, embedding_vector_json=None),
        _chunk_row("svo-3rd", 2, embedding_vector_json=None),
    ]
    manager = _FakeManager()
    database = _FakeDatabase(chunks)

    loaded = await faiss_manager_rebuild.rebuild_from_database_impl(
        manager, cast(DatabaseClient, database), _TruncatingSvo(), project_id=None
    )

    assert loaded == 2
    assert len(manager.added) == 2
    assert _added_embedding(manager, 0) == _embedding_for_text("text for svo-1st")
    assert _added_embedding(manager, 1) == _embedding_for_text("text for svo-2nd")
    assert all(vid != 2 for _emb, vid in manager.added)  # svo-3rd never added
    assert len(database.update_calls) == 2


def test_embedding_input_still_the_shared_adapter() -> None:
    """faiss_manager_rebuild still uses the shared EmbeddingInput, not a private adapter."""
    import inspect

    src = inspect.getsource(faiss_manager_rebuild)
    assert "EmbeddingInput" in src
    assert "class _TmpChunk" not in src
