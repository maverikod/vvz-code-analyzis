"""
Real-PostgreSQL test for keyset-paged ``_invalidate_stale_embedding_json_caches``
(1.6.113 hardening pass).

The original implementation pulled every non-NULL ``embedding_vector`` row into
memory with a single ``fetchall()`` before filtering/UPDATE-ing. This rewrites it
as a keyset (``id > last_seen ORDER BY id LIMIT page_size``) page walk so memory
stays bounded on a large table. This is a behavior-preserving refactor -- there is
no user-visible bug to reproduce RED-first, so this test instead proves
non-regression: seed more rows than one page holds (``page_size`` overridden to 3
via the new injectable parameter, well below the 10 seeded rows so at least 4 pages
are walked), then assert every stale row across every page was invalidated and
dead-lettered rows cleared, while valid (already-``new_dim``) rows survive
untouched.

Requires ``CODE_ANALYSIS_POSTGRES_TEST_DSN`` (e.g. ``postgresql://...``). Skipped
when unset -- same optional-live-PostgreSQL pattern as
``test_postgres_schema_bootstrap_real_pg.py`` / ``test_pgvector_integration.py``.
Runs in its own throwaway PostgreSQL schema (dropped ``CASCADE`` on teardown), so it
never touches pre-existing tables/data on the target database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Iterator

import pytest

_PG_ENV = "CODE_ANALYSIS_POSTGRES_TEST_DSN"


def _live_dsn() -> str:
    dsn = (os.environ.get(_PG_ENV) or "").strip()
    if not dsn:
        pytest.skip(
            f"Live PostgreSQL test skipped: set {_PG_ENV} to run (optional CI)."
        )
    return dsn


@pytest.fixture()
def fresh_pg_schema_conn() -> Iterator[Any]:
    """Open connection with an isolated, empty PostgreSQL schema as the head of
    ``search_path``, with ``public`` appended behind it.

    Own copy of the fixture in ``test_postgres_schema_bootstrap_real_pg.py`` (kept
    duplicated rather than imported so this throwaway-schema test file has no
    cross-file coupling). See that file's fixture docstring for why ``public`` is
    appended rather than omitted (pgvector's ``vector`` type visibility).
    """
    pytest.importorskip("psycopg")
    import psycopg

    dsn = _live_dsn()
    schema_name = f"catest_{uuid.uuid4().hex[:16]}"
    conn = psycopg.connect(dsn)
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {schema_name}")
        cur.execute(f"SET search_path TO {schema_name}, public")
    conn.commit()
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
            conn.commit()
        finally:
            conn.close()


def _seed_project_and_file(conn: Any) -> tuple[str, str]:
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    server_instance_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO projects (id, server_instance_id, root_path) "
            "VALUES (%s, %s, %s)",
            (project_id, server_instance_id, "/tmp/catest_invalidate_paging"),
        )
        cur.execute(
            "INSERT INTO files (id, project_id, path, relative_path) "
            "VALUES (%s, %s, %s, %s)",
            (
                file_id,
                project_id,
                "/tmp/catest_invalidate_paging/a.py",
                "a.py",
            ),
        )
    conn.commit()
    return project_id, file_id


def _insert_chunk(
    conn: Any,
    *,
    file_id: str,
    project_id: str,
    embedding_vector_json: str,
    vectorization_skipped: int,
) -> str:
    chunk_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO code_chunks "
            "(id, file_id, project_id, chunk_uuid, chunk_type, chunk_text, "
            "embedding_vector, embedding_model, vectorization_skipped) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                chunk_id,
                file_id,
                project_id,
                chunk_id,
                "function",
                "def f(): pass",
                embedding_vector_json,
                "test-model",
                vectorization_skipped,
            ),
        )
    return chunk_id


@pytest.mark.postgres
@pytest.mark.integration
def test_invalidate_stale_embedding_json_caches_pages_across_multiple_pages(
    fresh_pg_schema_conn: Any,
) -> None:
    """Keyset paging must invalidate every stale row across many pages, clear the
    dead-letter flag on rows it invalidates, and leave already-correct rows alone.

    Seeds 10 ``code_chunks`` rows directly (bypassing ``_ensure_pgvector_embedding_
    column`` -- this targets ``_invalidate_stale_embedding_json_caches`` in
    isolation, not the full dimension-retype path already covered by
    ``test_postgres_schema_bootstrap_real_pg.py``):
    - 4 rows with an 8-dim ``embedding_vector`` (stale relative to new_dim=16),
      2 of them dead-lettered (``vectorization_skipped`` = the dead-letter sentinel).
    - 3 rows with malformed (non-JSON) ``embedding_vector`` (must also be treated
      as stale -- matches the "cannot be positively confirmed" contract).
    - 3 rows already at the 16-dim target (must survive untouched).

    ``page_size=3`` (override via the new injectable parameter) against 10 seeded
    rows forces at least 4 pages, proving the walk does not stop after the first
    page and does not skip/duplicate rows at page boundaries.
    """
    from code_analysis.core.database.schema_definition import get_schema_definition
    from code_analysis.core.database_driver_pkg.drivers.postgres_migrations import (
        _ensure_postgres_schema_once,
        _invalidate_stale_embedding_json_caches,
    )
    from code_analysis.core.vectorization_worker_pkg.batch_processor import (
        VECTORIZATION_DEAD_LETTER_SKIPPED_VALUE,
    )

    conn = fresh_pg_schema_conn
    schema = get_schema_definition()
    # vector_dim=1 keeps _ensure_pgvector_embedding_column's own ADD/ALTER path
    # out of the way (no pgvector requirement); this test drives
    # _invalidate_stale_embedding_json_caches directly, not through a retype.
    _ensure_postgres_schema_once(conn, schema, vector_dim=1)

    project_id, file_id = _seed_project_and_file(conn)

    stale_8dim_ids = [
        _insert_chunk(
            conn,
            file_id=file_id,
            project_id=project_id,
            embedding_vector_json=json.dumps([0.1] * 8),
            vectorization_skipped=(
                VECTORIZATION_DEAD_LETTER_SKIPPED_VALUE if i < 2 else 0
            ),
        )
        for i in range(4)
    ]
    stale_malformed_ids = [
        _insert_chunk(
            conn,
            file_id=file_id,
            project_id=project_id,
            embedding_vector_json="{not valid json",
            vectorization_skipped=0,
        )
        for _ in range(3)
    ]
    valid_16dim_ids = [
        _insert_chunk(
            conn,
            file_id=file_id,
            project_id=project_id,
            embedding_vector_json=json.dumps([0.2] * 16),
            vectorization_skipped=0,
        )
        for _ in range(3)
    ]
    conn.commit()

    _invalidate_stale_embedding_json_caches(conn, 16, page_size=3)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, embedding_vector, embedding_model, vectorization_skipped "
            "FROM code_chunks WHERE id = ANY(%s)",
            (stale_8dim_ids + stale_malformed_ids + valid_16dim_ids,),
        )
        rows_by_id = {str(row[0]): row for row in cur.fetchall()}

    assert len(rows_by_id) == 10

    for chunk_id in stale_8dim_ids + stale_malformed_ids:
        row = rows_by_id[chunk_id]
        assert row[1] is None, f"{chunk_id} embedding_vector must be invalidated"
        assert row[2] is None, f"{chunk_id} embedding_model must be cleared"
        assert row[3] == 0, f"{chunk_id} dead-letter flag must be cleared"

    for chunk_id in valid_16dim_ids:
        row = rows_by_id[chunk_id]
        assert row[1] is not None, f"{chunk_id} valid cache must survive"
        assert row[2] == "test-model", f"{chunk_id} embedding_model must survive"
        assert row[3] == 0
