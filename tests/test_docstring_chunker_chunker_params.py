"""
Unit tests for SVO chunker preset kwargs (chunk_set, use_sv, language, type).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
from unittest.mock import AsyncMock, Mock

import pytest

from code_analysis.core.docs_markdown_vector_gate import DOCS_MARKDOWN_SOURCE_TYPE
from code_analysis.core.docstring_chunker_pkg.docstring_chunker import (
    DOCSTRING_CHUNK_BATCH_MAX_TEXTS,
    DocstringChunker,
    PreparedDocstringFile,
    _DocItem,
)


def _doc_item(
    *,
    source_type: str = "docstring",
    ast_node_type: str = "Module",
    text: str = "Some docstring text long enough.",
) -> _DocItem:
    return _DocItem(
        source_type=source_type,
        chunk_type="DocBlock",
        text=text,
        line=1,
        ast_node_type=ast_node_type,
        binding_level=0,
    )


def test_chunker_params_docstring_items() -> None:
    chunker = DocstringChunker(database=Mock(), svo_client_manager=None)
    p = chunker._chunker_params_for_items([_doc_item()])
    assert p == {
        "chunk_set": "docstring",
        "use_sv": False,
        "language": "en",
        "type": "DocBlock",
    }


@pytest.mark.parametrize(
    "item",
    [
        _doc_item(source_type=DOCS_MARKDOWN_SOURCE_TYPE),
        _doc_item(source_type="docstring", ast_node_type="MarkdownDoc"),
    ],
)
def test_chunker_params_markdown_technical_text(item: _DocItem) -> None:
    chunker = DocstringChunker(database=Mock(), svo_client_manager=None)
    p = chunker._chunker_params_for_items([item])
    assert p == {
        "chunk_set": "technical_text",
        "use_sv": False,
        "language": "en",
        "type": "DocBlock",
    }


@pytest.mark.asyncio
async def test_fetch_rows_passes_kwargs_to_get_chunks() -> None:
    item = _doc_item()
    mgr = Mock()
    mgr.get_chunks = AsyncMock(return_value=[])

    chunker = DocstringChunker(database=Mock(), svo_client_manager=mgr)
    await chunker._fetch_rows_for_item_with_get_chunks(item)

    mgr.get_chunks.assert_awaited_once()
    ca = mgr.get_chunks.await_args
    assert ca.kwargs["text"] == item.text
    assert ca.kwargs["chunk_set"] == "docstring"
    assert ca.kwargs["use_sv"] is False
    assert ca.kwargs["language"] == "en"
    assert ca.kwargs["type"] == "DocBlock"


class _FakeChunk:
    def __init__(self, body: str) -> None:
        self.body = body
        self.embedding = None
        self.embedding_model = None
        self.token_count = 1


@pytest.mark.asyncio
async def test_process_prepared_files_passes_kwargs_to_get_chunks_batch(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        DocstringChunker,
        "_file_still_exists_and_not_deleted",
        lambda self, file_id, project_id: True,
    )
    monkeypatch.setattr(
        "code_analysis.core.docstring_chunker_pkg.docstring_chunker.DOCSTRING_CHUNK_BATCH_MAX_TEXTS",
        max(DOCSTRING_CHUNK_BATCH_MAX_TEXTS, 10),
    )

    src = '"""Module doc with enough characters for batch kwargs test."""\n'
    tree = ast.parse(src)
    chunker = DocstringChunker(database=Mock(), svo_client_manager=Mock())
    py_items = list(chunker._extract_docstrings(tree, src))
    assert len(py_items) == 1

    md_item = _doc_item(
        source_type=DOCS_MARKDOWN_SOURCE_TYPE,
        text="# Title\n\nBody text here for length.",
    )
    prepared = [
        PreparedDocstringFile(
            file_id="10000000-0000-4000-8000-000000000099",
            project_id="p1",
            file_path="a.py",
            tree=tree,
            file_content=src,
            items=py_items,
        ),
        PreparedDocstringFile(
            file_id="10000000-0000-4000-8000-000000000098",
            project_id="p1",
            file_path="b.md",
            tree=tree,
            file_content=src,
            items=[md_item],
        ),
    ]

    mgr = chunker.svo_client_manager
    mgr.get_chunks_batch = AsyncMock(
        return_value=[[_FakeChunk("a")], [_FakeChunk("b")]]
    )
    db = Mock()

    async def lw(program):
        return {"success": True}

    db.execute_logical_write_operation = lw
    chunker.database = db

    await chunker.process_prepared_files(prepared)

    mgr.get_chunks_batch.assert_awaited_once()
    ca = mgr.get_chunks_batch.await_args
    texts = ca.args[0]
    assert len(texts) == 2
    kw = ca.kwargs
    assert kw["chunk_set"] == "technical_text"
    assert kw["use_sv"] is False
    assert kw["language"] == "en"
    assert kw["type"] == "DocBlock"


@pytest.mark.asyncio
async def test_gather_rows_batch_passes_kwargs_to_get_chunks_batch() -> None:
    item = _doc_item()
    mgr = Mock()
    mgr.get_chunks_batch = AsyncMock(return_value=[[_FakeChunk("x")]])

    chunker = DocstringChunker(database=Mock(), svo_client_manager=mgr)
    await chunker._gather_rows_for_docblock_items([item], log_file_id="fid")

    mgr.get_chunks_batch.assert_awaited_once()
    ca = mgr.get_chunks_batch.await_args
    assert ca.args[0] == [item.text]
    assert ca.kwargs["chunk_set"] == "docstring"
    assert ca.kwargs["use_sv"] is False
    assert ca.kwargs["language"] == "en"
    assert ca.kwargs["type"] == "DocBlock"


@pytest.mark.asyncio
async def test_gather_rows_single_fallback_passes_kwargs_to_get_chunks() -> None:
    item = _doc_item()
    mgr = Mock()
    mgr.get_chunks = AsyncMock(return_value=[])
    # No batch API → per-item get_chunks
    mgr.get_chunks_batch = None

    chunker = DocstringChunker(database=Mock(), svo_client_manager=mgr)
    await chunker._gather_rows_for_docblock_items([item], log_file_id="fid")

    mgr.get_chunks.assert_awaited_once()
    ca = mgr.get_chunks.await_args
    assert ca.kwargs["text"] == item.text
    assert ca.kwargs["chunk_set"] == "docstring"
    assert ca.kwargs["use_sv"] is False
    assert ca.kwargs["language"] == "en"
    assert ca.kwargs["type"] == "DocBlock"
