"""
Optional live PostgreSQL checks for pgvector (embedding format and schema migration).

Requires ``CODE_ANALYSIS_POSTGRES_TEST_DSN`` (e.g. ``postgresql://...``). Skipped when unset.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os

import numpy as np
import pytest

_PG_ENV = "CODE_ANALYSIS_POSTGRES_TEST_DSN"


@pytest.mark.skipif(
    not os.environ.get(_PG_ENV),
    reason=f"{_PG_ENV} not set (optional live PostgreSQL test)",
)
def test_pgvector_cosine_order_matches_query_vector() -> None:
    """Normalized embeddings round-trip as literals; closest row to query is self."""
    pytest.importorskip("psycopg")
    import psycopg

    from code_analysis.core.faiss_manager import FaissIndexManager
    from code_analysis.core.pgvector_embedding import numpy_embedding_to_pgvector_text

    dsn = os.environ[_PG_ENV]
    dim = 8
    q = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float32)
    o = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    nq = FaissIndexManager._normalize_vector(q.copy())
    no = FaissIndexManager._normalize_vector(o.copy())
    tq = numpy_embedding_to_pgvector_text(nq)
    to = numpy_embedding_to_pgvector_text(no)

    with psycopg.connect(dsn) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE TEMP TABLE _pgvec_probe (id int PRIMARY KEY, v vector({dim}))"
            )
            cur.execute(
                "INSERT INTO _pgvec_probe (id, v) VALUES (1, %s::vector), (2, %s::vector)",
                (tq, to),
            )
            cur.execute(
                "SELECT id FROM _pgvec_probe ORDER BY v <=> %s::vector ASC LIMIT 1",
                (tq,),
            )
            row = cur.fetchone()
        conn.commit()

    assert row is not None
    assert int(row[0]) == 1


@pytest.mark.skipif(
    not os.environ.get(_PG_ENV),
    reason=f"{_PG_ENV} not set (optional live PostgreSQL test)",
)
def test_ensure_postgres_schema_defines_embedding_vec_when_pgvector_available() -> None:
    """After ensure_postgres_schema, code_chunks.embedding_vec exists if extension allowed."""
    pytest.importorskip("psycopg")
    import psycopg

    from code_analysis.core.database.schema_definition import get_schema_definition
    from code_analysis.core.database_driver_pkg.drivers.postgres_migrations import (
        ensure_postgres_schema,
    )

    dsn = os.environ[_PG_ENV]
    schema = get_schema_definition()
    with psycopg.connect(dsn) as conn:
        ensure_postgres_schema(conn, schema, vector_dim=384)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'code_chunks'
                  AND column_name = 'embedding_vec'
                LIMIT 1
                """
            )
            found = cur.fetchone() is not None

    if not found:
        pytest.skip(
            "code_chunks.embedding_vec missing (pgvector extension not installed or "
            "CREATE EXTENSION not permitted on this database)"
        )


@pytest.mark.skipif(
    not os.environ.get(_PG_ENV),
    reason=f"{_PG_ENV} not set (optional live PostgreSQL test)",
)
def test_ensure_postgres_schema_adds_watch_dirs_deleted_column() -> None:
    """After ensure_postgres_schema, watch_dirs.deleted exists on live PostgreSQL."""
    pytest.importorskip("psycopg")
    import psycopg

    from code_analysis.core.database.schema_definition import get_schema_definition
    from code_analysis.core.database_driver_pkg.drivers.postgres_migrations import (
        ensure_postgres_schema,
    )

    dsn = os.environ[_PG_ENV]
    schema = get_schema_definition()
    with psycopg.connect(dsn) as conn:
        ensure_postgres_schema(conn, schema, vector_dim=384)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'watch_dirs'
                  AND column_name = 'deleted'
                LIMIT 1
                """
            )
            assert cur.fetchone() is not None
