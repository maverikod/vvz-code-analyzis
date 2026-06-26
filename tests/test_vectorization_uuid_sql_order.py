"""
Regression: vectorization / FAISS paths order chunks by created_at, not UUID id.

Block G — UUID migration: lexical UUID order is not creation order.
"""

from __future__ import annotations

import inspect


def test_faiss_rebuild_row_number_sorts_by_created_at_then_id() -> None:
    """Verify test faiss rebuild row number sorts by created at then id."""
    from code_analysis.core import faiss_manager_rebuild

    src = inspect.getsource(faiss_manager_rebuild.rebuild_from_database_impl)
    assert (
        src.count("ROW_NUMBER() OVER (ORDER BY created_at, id)") >= 2
    ), "expected ROW_NUMBER … ORDER BY created_at, id in project + global rebuild branches"


def test_faiss_fetch_chunks_orders_by_created_at() -> None:
    """Verify test faiss fetch chunks orders by created at."""
    from code_analysis.core import faiss_manager_rebuild

    src = inspect.getsource(faiss_manager_rebuild._fetch_chunks_for_rebuild)
    assert "ORDER BY cc.created_at, cc.id" in src


def test_base_chunks_queries_use_created_at_order() -> None:
    """Verify test base chunks queries use created at order."""
    from code_analysis.core.database import base_chunks

    src = inspect.getsource(base_chunks.get_all_chunks_for_faiss_rebuild)
    assert "ORDER BY cc.created_at, cc.id" in src
    src2 = inspect.getsource(base_chunks.get_non_vectorized_chunks)
    assert "ORDER BY cc.created_at, cc.id" in src2


def test_batch_processor_chunk_only_select_orders_chunks_by_file_position() -> None:
    """Chunk-only vectorization processes each file in ordinal order."""
    from code_analysis.core.vectorization_worker_pkg import batch_processor

    src = inspect.getsource(batch_processor.process_chunk_only_files)
    assert "ORDER BY cc.ordinal ASC, cc.id ASC" in src


def test_batch_processor_embedding_ready_orders_chunks_newest_first() -> None:
    """Worker hot-path: embedding-ready batch uses DESC created_at."""
    from code_analysis.core.vectorization_worker_pkg import batch_processor

    src = inspect.getsource(batch_processor.process_embedding_ready_chunks)
    assert "ORDER BY cc.created_at DESC, cc.id DESC" in src
