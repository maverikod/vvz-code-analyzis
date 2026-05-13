"""
Tests for multi-file get_chunks_batch in DocstringChunker.process_prepared_files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
from unittest.mock import AsyncMock, Mock

import pytest

from code_analysis.core.docstring_chunker_pkg.docstring_chunker import (
    DOCSTRING_CHUNK_BATCH_MAX_TEXTS,
    DocstringChunker,
    PreparedDocstringFile,
)

FID_A = "10000000-0000-4000-8000-000000000001"
FID_B = "10000000-0000-4000-8000-000000000002"
FID_X = "10000000-0000-4000-8000-000000000010"
FID_MANY = "10000000-0000-4000-8000-000000000003"


class _FakeChunk:
    def __init__(self, body: str) -> None:
        self.body = body
        self.embedding = [0.1, 0.2]
        self.embedding_model = "test-model"
        self.token_count = 2


@pytest.fixture
def mock_db_execute_batch():
    mock = Mock()
    mock.execute_batch_calls = []
    mock.logical_write_calls = []

    def execute_batch(operations):
        mock.execute_batch_calls.append(operations)
        return [{"affected_rows": 1} for _ in operations]

    def execute_logical_write_operation(program):
        mock.logical_write_calls.append(program)
        return {"success": True, "data": {"batch_results": []}}

    mock.execute_batch = execute_batch
    mock.execute_logical_write_operation = execute_logical_write_operation
    mock.execute = Mock(
        return_value={"data": [{}], "affected_rows": 0, "lastrowid": None}
    )
    return mock


def _minimal_tree(src: str) -> ast.Module:
    t = ast.parse(src)
    assert isinstance(t, ast.Module)
    return t


@pytest.mark.asyncio
async def test_process_prepared_files_single_ws_batch_two_files(
    mock_db_execute_batch,
) -> None:
    """Two files' docstrings are sent in one get_chunks_batch call (positional alignment)."""
    src_a = '"""Doc A."""\n'
    src_b = '"""Doc B is longer for min length."""\n'
    tree_a = _minimal_tree(src_a)
    tree_b = _minimal_tree(src_b)
    chunker = DocstringChunker(
        database=mock_db_execute_batch,
        svo_client_manager=Mock(),
        embedding_model="test-model",
    )
    items_a = list(chunker._extract_docstrings(tree_a, src_a))
    items_b = list(chunker._extract_docstrings(tree_b, src_b))
    assert len(items_a) == 1 and len(items_b) == 1

    mgr = chunker.svo_client_manager
    mgr.get_chunks_batch = AsyncMock(
        return_value=[[_FakeChunk("ca")], [_FakeChunk("cb")]]
    )

    prepared = [
        PreparedDocstringFile(
            file_id=FID_A,
            project_id="p1",
            file_path="a.py",
            tree=tree_a,
            file_content=src_a,
            items=items_a,
        ),
        PreparedDocstringFile(
            file_id=FID_B,
            project_id="p1",
            file_path="b.py",
            tree=tree_b,
            file_content=src_b,
            items=items_b,
        ),
    ]
    out = await chunker.process_prepared_files(prepared)
    assert out[FID_A] == 1 and out[FID_B] == 1
    assert len(mock_db_execute_batch.logical_write_calls) == 1
    prog = mock_db_execute_batch.logical_write_calls[0]
    assert len(prog["batches"]) == 1
    assert len(prog["batches"][0]) == 2
    assert not mock_db_execute_batch.execute_batch_calls
    mgr.get_chunks_batch.assert_awaited_once()
    call_kw = mgr.get_chunks_batch.await_args
    texts = call_kw.args[0]
    assert texts == [items_a[0].text, items_b[0].text]
    assert call_kw.kwargs.get("type") == "DocBlock"
    assert call_kw.kwargs.get("chunk_set") == "docstring"
    assert call_kw.kwargs.get("use_sv") is False
    assert call_kw.kwargs.get("language") == "en"


@pytest.mark.asyncio
async def test_process_prepared_files_fallback_per_file_on_batch_failure(
    mock_db_execute_batch,
) -> None:
    """When multi-file batch fails, per-file process_file still persists rows."""
    src = '"""Module doc."""\nclass X:\n    """Class docstring long enough."""\n    pass\n'
    tree = _minimal_tree(src)
    chunker = DocstringChunker(
        database=mock_db_execute_batch,
        svo_client_manager=Mock(),
        embedding_model="test-model",
    )
    items = list(chunker._extract_docstrings(tree, src))
    assert len(items) >= 1

    mgr = chunker.svo_client_manager

    async def fail_batch(*_a, **_k):
        raise RuntimeError("ws batch failed")

    async def ok_one(**kwargs):
        t = kwargs.get("text", "")
        return [_FakeChunk(t[:20])] if t else []

    mgr.get_chunks_batch = AsyncMock(side_effect=fail_batch)
    mgr.get_chunks = AsyncMock(side_effect=ok_one)

    prepared = [
        PreparedDocstringFile(
            file_id=FID_X,
            project_id="p1",
            file_path="x.py",
            tree=tree,
            file_content=src,
            items=items,
        ),
    ]
    out = await chunker.process_prepared_files(prepared)
    assert out[FID_X] >= 1
    mgr.get_chunks_batch.assert_awaited()
    assert mgr.get_chunks.await_count >= 1


@pytest.mark.asyncio
async def test_process_prepared_files_segments_when_over_max_texts(
    mock_db_execute_batch, monkeypatch
) -> None:
    """Large docstring counts are split into multiple get_chunks_batch segments."""
    monkeypatch.setattr(
        "code_analysis.core.docstring_chunker_pkg.docstring_chunker.DOCSTRING_CHUNK_BATCH_MAX_TEXTS",
        2,
    )
    src = "\n".join(
        f'def f{i}():\n    """Doc number {i} with padding."""\n    pass'
        for i in range(5)
    )
    tree = _minimal_tree(src)
    chunker = DocstringChunker(
        database=mock_db_execute_batch,
        svo_client_manager=Mock(),
        embedding_model="test-model",
    )
    items = list(chunker._extract_docstrings(tree, src))
    assert len(items) == 5

    async def batch(texts, **_k):
        return [[_FakeChunk(t[:10])] for t in texts]

    mgr = chunker.svo_client_manager
    mgr.get_chunks_batch = AsyncMock(side_effect=batch)

    prepared = [
        PreparedDocstringFile(
            file_id=FID_MANY,
            project_id="p1",
            file_path="many.py",
            tree=tree,
            file_content=src,
            items=items,
        ),
    ]
    out = await chunker.process_prepared_files(prepared)
    assert out[FID_MANY] == 5
    assert mgr.get_chunks_batch.await_count == 3
    assert len(mock_db_execute_batch.logical_write_calls) == 1
    assert len(mock_db_execute_batch.logical_write_calls[0]["batches"][0]) == 5


def test_docstring_chunk_batch_max_constant() -> None:
    assert isinstance(DOCSTRING_CHUNK_BATCH_MAX_TEXTS, int)
    assert DOCSTRING_CHUNK_BATCH_MAX_TEXTS >= 64
