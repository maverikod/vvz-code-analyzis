"""
Vector ANN backend resolution (FAISS vs pgvector).

PostgreSQL is the only supported driver. pgvector is used unless the
``vector_search_backend`` config explicitly requests ``faiss``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Literal, Optional

VectorSearchBackend = Literal["faiss", "pgvector"]


def driver_requires_faiss(driver_type: str) -> bool:
    """
    Return True when the stack must use file-based FAISS for vector search.

    PostgreSQL never forces FAISS by driver type; the choice is config-driven
    (see :func:`effective_vector_search_backend`). Kept for call-site compatibility.
    """
    _ = driver_type
    return False


def effective_vector_search_backend(
    driver_type: str,
    configured: Optional[str],
) -> VectorSearchBackend:
    """
    Resolve the effective ANN backend from driver type and config.

    Rules (fixed):
    - ``postgres`` → ``pgvector`` when ``configured`` is omitted, ``auto``, or ``pgvector``; ``faiss`` when ``configured`` is ``faiss``.
    - Any other driver → ``faiss`` (should not occur; SQLite support was removed).
    """
    dt = (driver_type or "").strip().lower()

    raw = configured if configured is not None else "auto"
    cfg = str(raw).strip().lower()
    if cfg not in ("auto", "faiss", "pgvector"):
        cfg = "auto"

    if dt == "postgres":
        if cfg == "faiss":
            return "faiss"
        return "pgvector"

    return "faiss"


def ann_ready_sql_fragment(cc_alias: str, backend: VectorSearchBackend) -> str:
    """
    SQL predicate: chunk is indexed for ANN search (FAISS slot or pgvector column).
    """
    if backend == "pgvector":
        return f"{cc_alias}.embedding_vec IS NOT NULL"
    return f"{cc_alias}.vector_id IS NOT NULL"


def ann_pending_sql_fragment(cc_alias: str, backend: VectorSearchBackend) -> str:
    """SQL predicate: chunk is not yet ANN-indexed (same notion as the vectorization worker)."""
    if backend == "pgvector":
        return f"{cc_alias}.embedding_vec IS NULL"
    return f"{cc_alias}.vector_id IS NULL"


def uses_pgvector_ann_for_database(db: Any) -> bool:
    """
    True when this :class:`~code_analysis.core.database.base.CodeDatabase` (or RPC
    client with matching attributes) should use pgvector for ANN storage/search.
    """
    dt = str(getattr(db, "_driver_type", "") or "")
    cfg = (getattr(db, "driver_config", None) or {}).get("config") or {}
    vsb = cfg.get("vector_search_backend")
    return effective_vector_search_backend(dt, vsb) == "pgvector"
