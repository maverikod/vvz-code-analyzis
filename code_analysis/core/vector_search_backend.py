"""
Vector ANN backend resolution (FAISS vs pgvector).

Hard invariant: any SQLite-class database driver **always** uses FAISS
(JSON ``embedding_vector`` + per-project ``.bin`` index). pgvector is only
considered for PostgreSQL.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Literal, Optional

VectorSearchBackend = Literal["faiss", "pgvector"]

# Drivers that cannot use pgvector (no ``vector`` type / extension in this stack).
_SQLITE_CLASS_DRIVERS = frozenset({"sqlite", "sqlite_proxy"})


def driver_requires_faiss(driver_type: str) -> bool:
    """
    Return True when the stack must use file-based FAISS for vector search.

    SQLite and sqlite_proxy always use FAISS; this is not configurable.
    """
    dt = (driver_type or "").strip().lower()
    return dt in _SQLITE_CLASS_DRIVERS


def effective_vector_search_backend(
    driver_type: str,
    configured: Optional[str],
) -> VectorSearchBackend:
    """
    Resolve the effective ANN backend from driver type and config.

    Rules (fixed):
    - ``sqlite`` / ``sqlite_proxy`` → always ``faiss`` (``pgvector`` in config is invalid; rejected at config validation).
    - ``postgres`` → ``pgvector`` when ``configured`` is omitted, ``auto``, or ``pgvector``; ``faiss`` when ``configured`` is ``faiss``.
    - Any other driver → ``faiss``.
    """
    dt = (driver_type or "").strip().lower()
    if dt in _SQLITE_CLASS_DRIVERS:
        return "faiss"

    raw = configured if configured is not None else "auto"
    cfg = str(raw).strip().lower()
    if cfg not in ("auto", "faiss", "pgvector"):
        cfg = "auto"

    if dt == "postgres":
        if cfg == "faiss":
            return "faiss"
        return "pgvector"

    return "faiss"


def uses_pgvector_ann_for_database(db: Any) -> bool:
    """
    True when this :class:`~code_analysis.core.database.base.CodeDatabase` (or RPC
    client with matching attributes) should use pgvector for ANN storage/search.
    """
    dt = str(getattr(db, "_driver_type", "") or "")
    cfg = (getattr(db, "driver_config", None) or {}).get("config") or {}
    vsb = cfg.get("vector_search_backend")
    return effective_vector_search_backend(dt, vsb) == "pgvector"
