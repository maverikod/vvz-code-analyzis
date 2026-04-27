"""
Portable ``code_chunks`` upsert statement (SQLite ``INSERT OR REPLACE``).

Layer ownership:

- **Portable SQL** (this module): ``CODE_CHUNK_UPSERT_SQL``, parameter layout
  (:data:`CODE_CHUNK_UPSERT_PARAM_ORDER` / :data:`CODE_CHUNK_UPSERT_PARAM_COUNT`),
  and :func:`build_code_chunk_upsert_batch`.
- **PostgreSQL adaptation**:
  ``database_driver_pkg.drivers.postgres_run._adapt_sqlite_dml_for_postgres``,
  keyed by :func:`code_chunk_upsert_norm_for_postgres_adapter` (must not duplicate
  the normalized lookup string elsewhere).
- **Callers** pass bound-parameter tuples only; workers/chunkers must not emit
  PostgreSQL-specific ``ON CONFLICT`` SQL.

:class:`~code_analysis.core.database_client.client.DatabaseClient` /
:class:`~code_analysis.core.database.base.CodeDatabase` expose
``upsert_code_chunk`` / ``upsert_code_chunks_batch`` for intent without raw SQL.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple

# Stable bound-parameter layout (placeholders only; ``updated_at`` is SQL-side).
CODE_CHUNK_UPSERT_PARAM_COUNT = 18
CODE_CHUNK_UPSERT_PARAM_ORDER = (
    "file_id",
    "project_id",
    "chunk_uuid",
    "chunk_type",
    "chunk_text",
    "chunk_ordinal",
    "vector_id",
    "embedding_model",
    "bm25_score",
    "embedding_vector",
    "token_count",
    "class_id",
    "function_id",
    "method_id",
    "line",
    "ast_node_type",
    "source_type",
    "binding_level",
)

# Single source of truth: UNIQUE(chunk_uuid) in schema; driver maps for PostgreSQL.
CODE_CHUNK_UPSERT_SQL = """
    INSERT OR REPLACE INTO code_chunks
    (
        file_id, project_id, chunk_uuid, chunk_type, chunk_text,
        chunk_ordinal, vector_id, embedding_model, bm25_score,
        embedding_vector, token_count, class_id, function_id, method_id,
        line, ast_node_type, source_type, binding_level,
        updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, julianday('now'))
"""


def _norm_sql_one_line(sql: str) -> str:
    return " ".join(sql.strip().rstrip(";").split())


def code_chunk_upsert_norm_for_postgres_adapter() -> str:
    """
    Normalized SQL string used as the lookup key in the PostgreSQL DML adapter.

    Must match ``CODE_CHUNK_UPSERT_SQL`` after ``julianday('now')`` →
    ``(EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))`` and one-line normalization.
    """
    s = CODE_CHUNK_UPSERT_SQL.replace(
        "julianday('now')", "(EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))"
    )
    return _norm_sql_one_line(s)


def build_code_chunk_upsert_batch(
    param_rows: Sequence[Tuple[Any, ...]],
) -> List[Tuple[str, Tuple[Any, ...]]]:
    """
    Build ``execute_batch`` / driver operations for portable chunk upserts.

    Each param row must be a :data:`CODE_CHUNK_UPSERT_PARAM_COUNT`-value tuple in
    :data:`CODE_CHUNK_UPSERT_PARAM_ORDER` (``updated_at`` is set by SQL, not bound).
    """
    sql = CODE_CHUNK_UPSERT_SQL.strip()
    expected = CODE_CHUNK_UPSERT_PARAM_COUNT
    order_hint = ", ".join(CODE_CHUNK_UPSERT_PARAM_ORDER)
    out: List[Tuple[str, Tuple[Any, ...]]] = []
    for i, t in enumerate(param_rows):
        row = tuple(t)
        n = len(row)
        if n != expected:
            raise ValueError(
                "code_chunk upsert param row "
                f"{i}: expected {expected} values in order ({order_hint}); "
                f"got {n}. "
                "Portable SQL binds only those columns; "
                "updated_at is supplied by julianday/EXTRACT in the statement."
            )
        out.append((sql, row))
    return out
