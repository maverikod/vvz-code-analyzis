"""
Bug 673ba07a phase 2: process_chunk_only_files must run in EVERY worker mode.

Chunks persisted without embeddings (SVO circuit-breaker fallback) previously
stayed stuck forever because the fill step returned early unless the worker was
configured with chunk_only=True. These tests pin the new contract: the step
embeds and commits such chunks with chunk_only=False and with the attribute
absent entirely.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from code_analysis.core.vectorization_worker_pkg.batch_processor import \
    process_chunk_only_files


class _CommitRecordingDatabase:
    """Fake database recording logical-write commits of embedding updates."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        """Initialize the instance."""
        self.chunks = chunks
        self.committed_batches: list[Any] = []

    def execute(self, sql: str, params: Any = None, **_kwargs: Any) -> dict[str, Any]:
        """Execute the command."""
        if "GROUP BY cc.file_id" in sql:
            return {
                "data": [
                    {
                        "file_id": "file-1",
                        "file_path": "pkg/mod.py",
                        "cnt": len(self.chunks),
                    }
                ]
            }
        return {"data": self.chunks}

    def execute_logical_write_operation(self, payload: dict[str, Any]) -> None:
        """Record the committed batches."""
        self.committed_batches.extend(payload.get("batches", []))


class _ResolvingSvoManager:
    """SVO manager double that assigns a usable embedding to every chunk."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self._embedding_available = True
        self.calls = 0

    async def get_embeddings(self, chunks: list[Any]) -> list[Any]:
        """Assign embedding and model to every chunk in place."""
        self.calls += 1
        for chunk in chunks:
            chunk.embedding = [0.1, 0.2, 0.3]
            chunk.embedding_model = "test-model"
        return chunks


def _worker(**overrides: Any) -> SimpleNamespace:
    """Build a minimal worker namespace for the fill step."""
    base: dict[str, Any] = {
        "svo_client_manager": _ResolvingSvoManager(),
        "project_id": "project-1",
        "max_files_per_pass": 30,
        "docs_markdown_embeddings_enabled": True,
        "retry_attempts": 3,
        "_stop_event": MagicMock(is_set=MagicMock(return_value=False)),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_fill_runs_with_chunk_only_false() -> None:
    """chunk_only=False no longer gates the step; embeddings are committed."""
    worker = _worker(chunk_only=False)
    db = _CommitRecordingDatabase([{"id": "c1", "chunk_text": "docstring text"}])

    updated, errors = await process_chunk_only_files(worker, db)

    assert updated == 1
    assert errors == 0
    assert worker.svo_client_manager.calls == 1
    assert len(db.committed_batches) == 1
    sql, params = db.committed_batches[0][0]
    assert "SET embedding_vector = ?" in sql
    assert params[1] == "test-model"
    assert params[2] == "c1"


@pytest.mark.asyncio
async def test_fill_runs_without_chunk_only_attribute() -> None:
    """A worker with no chunk_only attribute at all still drains the backlog."""
    worker = _worker()
    db = _CommitRecordingDatabase([{"id": "c2", "chunk_text": "another text"}])

    updated, errors = await process_chunk_only_files(worker, db)

    assert updated == 1
    assert errors == 0
    assert len(db.committed_batches) == 1


@pytest.mark.asyncio
async def test_fill_still_noop_without_svo_manager() -> None:
    """No embed client configured -> step stays a safe no-op."""
    worker = _worker(chunk_only=False, svo_client_manager=None)
    db = _CommitRecordingDatabase([{"id": "c3", "chunk_text": "text"}])

    updated, errors = await process_chunk_only_files(worker, db)

    assert (updated, errors) == (0, 0)
    assert db.committed_batches == []


def test_chunk_select_sql_uses_real_ordinal_column() -> None:
    """The per-file chunk select must order by code_chunks.chunk_ordinal.

    The column is ``chunk_ordinal`` (schema_definition_tables_mid.py); the
    pre-1.6.56 SQL said ``cc.ordinal`` and died with UndefinedColumn on
    PostgreSQL, killing the whole fill step on the first file.
    """
    import inspect as _inspect

    from code_analysis.core.vectorization_worker_pkg import batch_processor

    src = _inspect.getsource(batch_processor.process_chunk_only_files)
    assert "cc.chunk_ordinal" in src
    assert " cc.ordinal " not in src
