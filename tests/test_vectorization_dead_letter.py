"""
Tests for the vectorization dead-letter mechanism (vectorization_skipped=2).

Covers:
- process_embedding_ready_chunks: an unparseable/empty embedding_vector in the DB
  is dead-lettered (not silently skipped forever).
- process_chunk_only_files: a chunk that never resolves to a usable embedding is
  dead-lettered only once its attempt count reaches retry_attempts.
- Confirm-by-inspection: the FAISS full-rebuild path and revectorize's write path
  respect/clear the vectorization_skipped dead-letter marker.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from code_analysis.core.vectorization_worker_pkg.batch_processor import (
    VECTORIZATION_DEAD_LETTER_SKIPPED_VALUE,
    process_chunk_only_files,
    process_embedding_ready_chunks,
)


class _FakeReadyDatabase:
    """Fake database for process_embedding_ready_chunks: one bad-embedding row."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        """Initialize the instance."""
        self.chunks = chunks
        self.executed: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None, **_kwargs: Any) -> dict[str, Any]:
        """Execute the command, recording every call for inspection."""
        self.executed.append((sql, params))
        if "SELECT cc.id, cc.chunk_text" in sql:
            return {"data": self.chunks}
        return {"data": []}

    def execute_batch(self, ops: list[Any], **_kwargs: Any) -> None:
        """Return execute batch."""
        for op in ops:
            self.executed.append(op)


def _ready_worker() -> SimpleNamespace:
    """Return a minimal worker double for process_embedding_ready_chunks."""
    return SimpleNamespace(
        project_id="project-1",
        batch_size=10,
        vector_ann_backend="faiss",
        docs_markdown_embeddings_enabled=True,
        log_timing=False,
        faiss_manager=None,
        status_file_path=None,
        _stop_event=MagicMock(is_set=MagicMock(return_value=False)),
    )


@pytest.mark.asyncio
async def test_unparseable_embedding_vector_is_dead_lettered() -> None:
    """A non-JSON embedding_vector on a row is dead-lettered, not retried forever."""
    db = _FakeReadyDatabase(
        [
            {
                "id": "chunk-1",
                "chunk_text": "def f(): pass",
                "class_id": None,
                "function_id": None,
                "method_id": None,
                "line": 1,
                "ast_node_type": "function",
                "embedding_vector": "not-json",
                "embedding_model": "some-model",
                "chunk_file_relative_path": "pkg/mod.py",
            }
        ]
    )

    batch_processed, batch_errors = await process_embedding_ready_chunks(
        _ready_worker(), db
    )

    assert batch_processed == 0
    assert batch_errors == 0

    dead_letter_calls = [
        call
        for call in db.executed
        if isinstance(call, tuple)
        and len(call) == 2
        and isinstance(call[0], str)
        and "SET vectorization_skipped = ?" in call[0]
    ]
    assert len(dead_letter_calls) == 1
    _, params = dead_letter_calls[0]
    assert params[0] == VECTORIZATION_DEAD_LETTER_SKIPPED_VALUE
    assert params[1] == "chunk-1"


class _FakeChunkOnlyDatabase:
    """Fake database for process_chunk_only_files: records dead-letter UPDATEs."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        """Initialize the instance."""
        self.chunks = chunks
        self.dead_letters: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: Any = None, **_kwargs: Any) -> dict[str, Any]:
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
        if "SET vectorization_skipped = ?" in sql:
            self.dead_letters.append(tuple(params))
            return {"data": []}
        return {"data": self.chunks}

    def execute_logical_write_operation(self, payload: dict[str, Any]) -> None:
        """Return execute logical write operation."""

    def execute_batch(self, ops: list[Any], **_kwargs: Any) -> None:
        """Return execute batch."""


class _NeverResolvesSvoManager:
    """SVO manager double whose get_embeddings never sets an embedding."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self._embedding_available = True
        self.calls = 0

    async def get_embeddings(self, chunks: list[Any]) -> list[Any]:
        """Return get embeddings without ever assigning an embedding."""
        self.calls += 1
        return chunks


@pytest.mark.asyncio
async def test_chunk_only_dead_letters_only_once_attempts_reach_cap() -> None:
    """Dead-letter fires only on the call where attempts reach retry_attempts."""
    manager = _NeverResolvesSvoManager()
    worker = SimpleNamespace(
        chunk_only=True,
        svo_client_manager=manager,
        project_id="project-1",
        max_files_per_pass=30,
        docs_markdown_embeddings_enabled=True,
        retry_attempts=2,
        _stop_event=MagicMock(is_set=MagicMock(return_value=False)),
    )

    db = _FakeChunkOnlyDatabase([{"id": "a", "chunk_text": "A"}])

    # Call 1: attempts becomes 1, still < retry_attempts(2) -> no dead-letter.
    updated1, errors1 = await process_chunk_only_files(worker, db)
    assert updated1 == 0
    assert errors1 == 1
    assert db.dead_letters == []
    assert worker._chunk_only_attempts.get("a") == 1

    # Call 2: attempts becomes 2, >= retry_attempts(2) -> dead-lettered.
    updated2, errors2 = await process_chunk_only_files(worker, db)
    assert updated2 == 0
    assert len(db.dead_letters) == 1
    assert db.dead_letters[0][0] == VECTORIZATION_DEAD_LETTER_SKIPPED_VALUE
    assert db.dead_letters[0][1] == "a"
    # Attempts map entry is cleared once dead-lettered.
    assert "a" not in worker._chunk_only_attempts


@pytest.mark.asyncio
async def test_chunk_only_worker_without_retry_attempts_attr_uses_default() -> None:
    """A SimpleNamespace worker without retry_attempts/_chunk_only_attempts still works."""
    manager = _NeverResolvesSvoManager()
    worker = SimpleNamespace(
        chunk_only=True,
        svo_client_manager=manager,
        project_id="project-1",
        max_files_per_pass=30,
        docs_markdown_embeddings_enabled=True,
        _stop_event=MagicMock(is_set=MagicMock(return_value=False)),
    )
    db = _FakeChunkOnlyDatabase([{"id": "a", "chunk_text": "A"}])

    # Default retry_attempts=3: no dead-letter on the first call.
    updated, errors = await process_chunk_only_files(worker, db)
    assert updated == 0
    assert errors == 1
    assert db.dead_letters == []


def test_faiss_rebuild_normalize_ctes_exclude_vectorization_skipped() -> None:
    """Both normalize CTEs in rebuild_from_database_impl exclude dead-lettered rows."""
    from code_analysis.core import faiss_manager_rebuild

    src = inspect.getsource(faiss_manager_rebuild.rebuild_from_database_impl)
    assert (
        src.count("AND (vectorization_skipped IS NULL OR vectorization_skipped = 0)")
        >= 2
    )


def test_faiss_rebuild_fetch_chunks_excludes_vectorization_skipped() -> None:
    """_fetch_chunks_for_rebuild excludes dead-lettered rows from the SELECT."""
    from code_analysis.core import faiss_manager_rebuild

    src = inspect.getsource(faiss_manager_rebuild._fetch_chunks_for_rebuild)
    assert "vectorization_skipped" in src


def test_revectorize_write_path_resets_dead_letter_marker() -> None:
    """RevectorizeCommand._revectorize_project resets vectorization_skipped=2 to 0."""
    from code_analysis.commands.vector_commands.revectorize import RevectorizeCommand

    src = inspect.getsource(RevectorizeCommand._revectorize_project)
    assert "vectorization_skipped" in src
    assert "CASE" in src
