"""Unit tests for vector_search_backend resolution."""

from code_analysis.core.vector_search_backend import (
    driver_requires_faiss,
    effective_vector_search_backend,
)


def test_sqlite_always_faiss_effective() -> None:
    assert effective_vector_search_backend("sqlite", "pgvector") == "faiss"
    assert effective_vector_search_backend("sqlite_proxy", "auto") == "faiss"
    assert effective_vector_search_backend("SQLITE_PROXY", None) == "faiss"


def test_driver_requires_faiss_sqlite_only() -> None:
    assert driver_requires_faiss("sqlite") is True
    assert driver_requires_faiss("sqlite_proxy") is True
    assert driver_requires_faiss("postgres") is False


def test_postgres_respects_config() -> None:
    assert effective_vector_search_backend("postgres", "faiss") == "faiss"
    assert effective_vector_search_backend("postgres", "auto") == "pgvector"
    assert effective_vector_search_backend("postgres", "pgvector") == "pgvector"
    assert effective_vector_search_backend("postgres", None) == "pgvector"
