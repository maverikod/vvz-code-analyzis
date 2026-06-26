"""Test chunk-only vectorization neighbor merge recovery."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from code_analysis.core.vectorization_worker_pkg.batch_processor import (
    _EmbeddingTextChunk,
    process_chunk_only_files,
    recover_unvectorized_by_neighbor_merge,
)


@pytest.mark.asyncio
async def test_neighbor_merge_middle_failure_merges_with_previous() -> None:
    """Verify test neighbor merge middle failure merges with previous."""
    chunks = [
        _EmbeddingTextChunk("a", "A"),
        _EmbeddingTextChunk("b", "B"),
        _EmbeddingTextChunk("c", "C"),
    ]
    chunks[0].embedding = [1.0]
    chunks[0].embedding_model = "m"
    chunks[2].embedding = [3.0]
    chunks[2].embedding_model = "m"
    calls: list[str] = []

    async def embed_one(text: str) -> tuple[Optional[list], Optional[str]]:
        """Return embed one."""
        calls.append(text)
        return [9.0], "merged"

    out = await recover_unvectorized_by_neighbor_merge(chunks, embed_one)

    assert calls == ["AB"]
    assert out == {"a": ([9.0], "merged"), "b": ([9.0], "merged")}
    assert chunks[0].text == "A"
    assert chunks[1].text == "B"


@pytest.mark.asyncio
async def test_neighbor_merge_first_failure_merges_with_next() -> None:
    """Verify test neighbor merge first failure merges with next."""
    chunks = [
        _EmbeddingTextChunk("a", "A"),
        _EmbeddingTextChunk("b", "B"),
        _EmbeddingTextChunk("c", "C"),
    ]
    chunks[1].embedding = [2.0]
    chunks[1].embedding_model = "m"
    chunks[2].embedding = [3.0]
    chunks[2].embedding_model = "m"
    calls: list[str] = []

    async def embed_one(text: str) -> tuple[Optional[list], Optional[str]]:
        """Return embed one."""
        calls.append(text)
        return [8.0], "merged"

    out = await recover_unvectorized_by_neighbor_merge(chunks, embed_one)

    assert calls == ["AB"]
    assert out == {"a": ([8.0], "merged"), "b": ([8.0], "merged")}


@pytest.mark.asyncio
async def test_neighbor_merge_grows_to_whole_file_and_assigns_shared_vector() -> None:
    """Verify test neighbor merge grows to whole file and assigns shared vector."""
    chunks = [
        _EmbeddingTextChunk("a", "A"),
        _EmbeddingTextChunk("b", "B"),
        _EmbeddingTextChunk("c", "C"),
        _EmbeddingTextChunk("d", "D"),
    ]
    chunks[0].embedding = [1.0]
    chunks[0].embedding_model = "m"
    chunks[1].embedding = [2.0]
    chunks[1].embedding_model = "m"
    chunks[3].embedding = [4.0]
    chunks[3].embedding_model = "m"
    calls: list[str] = []

    async def embed_one(text: str) -> tuple[Optional[list], Optional[str]]:
        """Return embed one."""
        calls.append(text)
        if text == "ABCD":
            return [7.0], "whole"
        return None, None

    out = await recover_unvectorized_by_neighbor_merge(chunks, embed_one)

    assert calls == ["BC", "ABC", "ABCD"]
    assert out == {
        "a": ([7.0], "whole"),
        "b": ([7.0], "whole"),
        "c": ([7.0], "whole"),
        "d": ([7.0], "whole"),
    }


@pytest.mark.asyncio
async def test_neighbor_merge_unembeddable_whole_file_returns_no_assignments() -> None:
    """Verify test neighbor merge unembeddable whole file returns no assignments."""
    chunks = [
        _EmbeddingTextChunk("a", "A"),
        _EmbeddingTextChunk("b", "B"),
    ]
    calls: list[str] = []

    async def embed_one(text: str) -> tuple[Optional[list], Optional[str]]:
        """Return embed one."""
        calls.append(text)
        return None, None

    out = await recover_unvectorized_by_neighbor_merge(chunks, embed_one)

    assert calls == ["AB"]
    assert out == {}


class _FakeDatabase:
    """Represent FakeDatabase."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        """Initialize the instance."""
        self.chunks = chunks
        self.logical_writes: list[dict[str, Any]] = []
        self.batch_writes: list[list[tuple[str, Optional[tuple]]]] = []

    def execute(self, sql: str, params: tuple, **_kwargs: Any) -> dict[str, Any]:
        """Execute the command."""
        if "GROUP BY cc.file_id" in sql:
            return {
                "data": [
                    {
                        "file_id": "file-1",
                        "file_path": "file.py",
                        "cnt": len(self.chunks),
                    }
                ]
            }
        return {"data": self.chunks}

    def execute_logical_write_operation(self, payload: dict[str, Any]) -> None:
        """Return execute logical write operation."""
        self.logical_writes.append(payload)

    def execute_batch(
        self, ops: list[tuple[str, Optional[tuple]]], **_kwargs: Any
    ) -> None:
        """Return execute batch."""
        self.batch_writes.append(ops)


class _FakeSvoManager:
    """Represent FakeSvoManager."""

    def __init__(self, vectors_by_text: dict[str, Optional[list]]) -> None:
        """Initialize the instance."""
        self.vectors_by_text = vectors_by_text
        self._embedding_available = True
        self.calls: list[str] = []

    async def get_embeddings(self, chunks: list[Any]) -> list[Any]:
        """Return get embeddings."""
        for chunk in chunks:
            text = getattr(chunk, "text")
            self.calls.append(text)
            vector = self.vectors_by_text.get(text)
            if vector:
                chunk.embedding = vector
                chunk.embedding_model = "fake-model"
        return chunks


def _worker(manager: Any) -> SimpleNamespace:
    """Return worker."""
    return SimpleNamespace(
        chunk_only=True,
        svo_client_manager=manager,
        project_id="project-1",
        max_files_per_pass=30,
        docs_markdown_embeddings_enabled=True,
        _stop_event=MagicMock(is_set=MagicMock(return_value=False)),
    )


def _write_ops(db: _FakeDatabase) -> list[tuple[str, Optional[tuple]]]:
    """Return write ops."""
    if db.logical_writes:
        return db.logical_writes[0]["batches"][0]
    return db.batch_writes[0]


@pytest.mark.asyncio
async def test_process_chunk_only_fully_embeddable_commits_update_ops() -> None:
    """Verify test process chunk only fully embeddable commits update ops."""
    db = _FakeDatabase(
        [
            {"id": "a", "chunk_text": "A"},
            {"id": "b", "chunk_text": "B"},
        ]
    )
    manager = _FakeSvoManager({"A": [1.0], "B": [2.0]})

    updated, errors = await process_chunk_only_files(_worker(manager), db)

    assert (updated, errors) == (2, 0)
    ops = _write_ops(db)
    assert len(ops) == 2
    assert all(
        op[0].startswith("UPDATE code_chunks SET embedding_vector") for op in ops
    )
    assert all("DELETE FROM code_chunks" not in op[0] for op in ops)
    assert json.loads(ops[0][1][0]) == [1.0]


@pytest.mark.asyncio
async def test_process_chunk_only_neighbor_recovery_writes_shared_vector() -> None:
    """Verify test process chunk only neighbor recovery writes shared vector."""
    db = _FakeDatabase(
        [
            {"id": "a", "chunk_text": "A"},
            {"id": "b", "chunk_text": "B"},
        ]
    )
    manager = _FakeSvoManager({"A": [1.0], "B": None, "AB": [9.0]})

    updated, errors = await process_chunk_only_files(_worker(manager), db)

    assert (updated, errors) == (2, 0)
    ops = _write_ops(db)
    assert [json.loads(op[1][0]) for op in ops] == [[9.0], [9.0]]
    assert "AB" in manager.calls


@pytest.mark.asyncio
async def test_process_chunk_only_unavailable_skips_file_without_writes() -> None:
    """Verify test process chunk only unavailable skips file without writes."""

    class UnavailableManager(_FakeSvoManager):
        """Represent UnavailableManager."""

        async def get_embeddings(self, chunks: list[Any]) -> list[Any]:
            """Return get embeddings."""
            self._embedding_available = False
            raise TimeoutError("connection timeout")

    db = _FakeDatabase([{"id": "a", "chunk_text": "A"}])
    manager = UnavailableManager({})

    updated, errors = await process_chunk_only_files(_worker(manager), db)

    assert (updated, errors) == (0, 0)
    assert db.logical_writes == []
    assert db.batch_writes == []


@pytest.mark.asyncio
async def test_process_chunk_only_unembeddable_leaves_rows_for_retry() -> None:
    """Verify test process chunk only unembeddable leaves rows for retry."""
    db = _FakeDatabase(
        [
            {"id": "a", "chunk_text": "A"},
            {"id": "b", "chunk_text": "B"},
        ]
    )
    manager = _FakeSvoManager({"A": None, "B": None, "AB": None})

    updated, errors = await process_chunk_only_files(_worker(manager), db)

    assert (updated, errors) == (0, 2)
    assert db.logical_writes == []
    assert db.batch_writes == []
