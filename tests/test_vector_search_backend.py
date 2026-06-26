"""Unit tests for vector_search_backend resolution."""

from code_analysis.core.vector_search_backend import (
    ann_pending_sql_fragment,
    ann_ready_sql_fragment,
    driver_requires_faiss,
    effective_vector_search_backend,
)


def test_sqlite_always_faiss_effective() -> None:
    """Verify test sqlite always faiss effective."""
    assert effective_vector_search_backend("sqlite", "pgvector") == "faiss"
    assert effective_vector_search_backend("sqlite_proxy", "auto") == "faiss"
    assert effective_vector_search_backend("SQLITE_PROXY", None) == "faiss"


def test_driver_requires_faiss_sqlite_only() -> None:
    """Verify test driver requires faiss sqlite only."""
    assert driver_requires_faiss("sqlite") is True
    assert driver_requires_faiss("sqlite_proxy") is True
    assert driver_requires_faiss("postgres") is False


def test_postgres_respects_config() -> None:
    """Verify test postgres respects config."""
    assert effective_vector_search_backend("postgres", "faiss") == "faiss"
    assert effective_vector_search_backend("postgres", "auto") == "pgvector"
    assert effective_vector_search_backend("postgres", "pgvector") == "pgvector"
    assert effective_vector_search_backend("postgres", None) == "pgvector"


def test_ann_sql_fragments() -> None:
    """Verify test ann sql fragments."""
    assert ann_ready_sql_fragment("cc", "faiss") == "cc.vector_id IS NOT NULL"
    assert ann_pending_sql_fragment("cc", "faiss") == "cc.vector_id IS NULL"
    assert ann_ready_sql_fragment("cc", "pgvector") == "cc.embedding_vec IS NOT NULL"
    assert ann_pending_sql_fragment("cc", "pgvector") == "cc.embedding_vec IS NULL"
