"""Tests for ``docs_markdown`` vectorization policy (docs_indexing.vectorize)."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from code_analysis.core.docs_markdown_vector_gate import (
    DOCS_MARKDOWN_SOURCE_TYPE,
    docs_markdown_embeddings_disabled_by_policy,
    docs_markdown_embeddings_enabled_from_server_config_mapping,
    is_docs_markdown_chunk,
)


def test_policy_disabled_only_when_enabled_and_vectorize_false() -> None:
    """Verify test policy disabled only when enabled and vectorize false."""
    assert docs_markdown_embeddings_disabled_by_policy(None) is False
    assert docs_markdown_embeddings_disabled_by_policy({"enabled": False}) is False
    assert docs_markdown_embeddings_disabled_by_policy({"enabled": True}) is True
    assert (
        docs_markdown_embeddings_disabled_by_policy(
            {"enabled": True, "vectorize": False}
        )
        is True
    )
    assert (
        docs_markdown_embeddings_disabled_by_policy(
            {"enabled": True, "vectorize": True}
        )
        is False
    )


def test_embeddings_enabled_from_top_level_json() -> None:
    """Verify test embeddings enabled from top level json."""
    raw = {"code_analysis": {"docs_indexing": {"enabled": True, "vectorize": True}}}
    assert docs_markdown_embeddings_enabled_from_server_config_mapping(raw) is True
    raw2 = {"code_analysis": {"docs_indexing": {"enabled": True, "vectorize": False}}}
    assert docs_markdown_embeddings_enabled_from_server_config_mapping(raw2) is False


def test_is_docs_markdown_chunk() -> None:
    """Verify test is docs markdown chunk."""
    assert is_docs_markdown_chunk(
        chunk={"source_type": DOCS_MARKDOWN_SOURCE_TYPE},
    )
    assert not is_docs_markdown_chunk(chunk={"source_type": "docstring"})
    assert not is_docs_markdown_chunk(source_type="")


@pytest.mark.asyncio
async def test_process_markdown_skips_rpc_when_embeddings_disabled() -> None:
    """Verify test process markdown skips rpc when embeddings disabled."""
    from code_analysis.core.docstring_chunker_pkg.docstring_chunker import (
        DocstringChunker,
    )

    db = MagicMock()

    mgr = AsyncMock()
    mgr.get_chunks_batch = AsyncMock()
    mgr.get_chunks = AsyncMock()

    chunker = DocstringChunker(
        database=db,
        svo_client_manager=mgr,
        docs_markdown_embeddings_enabled=False,
    )

    mock_mark = AsyncMock()
    chunker._mark_docs_markdown_vectorization_skipped = mock_mark  # type: ignore[method-assign]
    mock_write = AsyncMock(return_value=1)
    chunker._write_docblock_chunk_rows = mock_write  # type: ignore[method-assign]

    wrote = await chunker.process_markdown_document(
        file_id="f1",
        project_id="p1",
        file_path="/x/README.md",
        text="# Hello\n",
    )

    mgr.get_chunks_batch.assert_not_called()
    mgr.get_chunks.assert_not_called()

    mock_write.assert_awaited_once()
    assert wrote == 1
    aa = mock_write.await_args
    assert aa is not None
    kwargs = aa.kwargs
    persist_rows = kwargs["rows_to_persist"]
    assert len(persist_rows) == 1
    item, _j, text, emb, _model, _tc = persist_rows[0]
    assert item.source_type == DOCS_MARKDOWN_SOURCE_TYPE
    assert emb is None
    assert text == "# Hello\n"
    mock_mark.assert_awaited_once()


def test_batch_processor_embedding_ready_uses_exclude_helper() -> None:
    """Verify test batch processor embedding ready uses exclude helper."""
    from code_analysis.core.vectorization_worker_pkg import batch_processor

    src_embed = inspect.getsource(batch_processor.process_embedding_ready_chunks)
    assert "_sql_exclude_docs_markdown_if_gated" in src_embed
    fake = MagicMock(
        project_id="pid", batch_size=5, docs_markdown_embeddings_enabled=False
    )

    exclude = batch_processor._sql_exclude_docs_markdown_if_gated(fake)
    assert "docs_markdown" in exclude
    exclude_on = batch_processor._sql_exclude_docs_markdown_if_gated(
        MagicMock(docs_markdown_embeddings_enabled=True)
    )
    assert exclude_on == ""
