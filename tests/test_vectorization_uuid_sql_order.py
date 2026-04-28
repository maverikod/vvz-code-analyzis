"""
Regression: vectorization / FAISS paths order chunks by created_at, not UUID id.

Block G — UUID migration: lexical UUID order is not creation order.
"""

from __future__ import annotations

import inspect


def test_faiss_rebuild_row_number_sorts_by_created_at_then_id() -> None:
    from code_analysis.core import faiss_manager_rebuild

    src = inspect.getsource(faiss_manager_rebuild.rebuild_from_database_impl)
    assert (
        src.count("ROW_NUMBER() OVER (ORDER BY created_at, id)") >= 4
    ), "expected ROW_NUMBER ... ORDER BY created_at, id in each rebuild branch"


def test_faiss_fetch_chunks_orders_by_created_at() -> None:
    from code_analysis.core import faiss_manager_rebuild

    src = inspect.getsource(faiss_manager_rebuild._fetch_chunks_for_rebuild)
    assert "ORDER BY cc.created_at, cc.id" in src


def test_base_chunks_queries_use_created_at_order() -> None:
    from code_analysis.core.database import base_chunks

    src = inspect.getsource(base_chunks.get_all_chunks_for_faiss_rebuild)
    assert "ORDER BY cc.created_at, cc.id" in src
    src2 = inspect.getsource(base_chunks.get_non_vectorized_chunks)
    assert "ORDER BY cc.created_at, cc.id" in src2
