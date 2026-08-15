"""
Real-PostgreSQL end-to-end bootstrap tests (1.6.76 deploy incident #2).

``test_postgres_schema_bootstrap_upgrade_path.py`` (the 1.6.75 incident's regression
test) uses an in-memory fake connection/cursor that tracks column EXISTENCE only. It
is structurally blind to Postgres TYPE errors: a partial index's
``content_stale = 1`` WHERE clause parses as valid SQL against that fake (the column
exists, its declared type is irrelevant to the fixture) and never raises -- so it did
not, and could not, catch the 1.6.76 incident
(``psycopg.errors.UndefinedFunction: operator does not exist: boolean = integer``).

These tests run the ACTUAL production DDL-generation and bootstrap code
(``create_postgresql_tables``, ``create_postgresql_indexes``,
``_ensure_postgres_schema_once``) against a REAL PostgreSQL server, so real Postgres
type-checking is in the loop. They would have caught BOTH the 1.6.75
(``UndefinedColumn``) and 1.6.76 (``UndefinedFunction``) deploy incidents.

Also covers bug f4dd4039: ``_ensure_pgvector_embedding_column`` used to only ADD
``embedding_vec`` when missing, so a changed configured ``vector_dim`` never reached
an EXISTING column -- this bricked embedding writes on the live server
(``psycopg.errors.DataException: expected 384 dimensions, not 1024``) until the DB
was fixed by hand. See ``test_ensure_schema_reconciles_embedding_vec_dimension_change``
below.

Requires ``CODE_ANALYSIS_POSTGRES_TEST_DSN`` (e.g. ``postgresql://user:pass@host/db``).
Skipped when unset -- same optional-live-PostgreSQL pattern as
``test_pgvector_integration.py`` / ``test_postgres_connect_idempotency.py``. Each test
runs in its own throwaway PostgreSQL schema (dropped ``CASCADE`` on teardown), so it
never touches pre-existing tables/data on the target database and is safe to point at
a shared disposable test database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import re
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

    Creates ``catest_<random>``, points the session's ``search_path`` at
    ``{schema_name}, public`` (so every unqualified DDL/query the bootstrap code
    issues -- including its ``current_schema()``-scoped ``information_schema``
    lookups -- resolves inside the throwaway schema, since it is first in path and
    ``current_schema()`` returns it), yields the open connection, then drops the
    schema ``CASCADE`` and closes the connection.

    ``public`` is appended (not omitted) because ``CREATE EXTENSION IF NOT EXISTS
    vector`` is a database-wide no-op when the ``vector`` extension already exists
    in ``public`` from an earlier test/deploy on this shared disposable database --
    a schema-only search_path then makes the ``vector`` type itself invisible
    (``UndefinedObject: type "vector" does not exist``) even though the extension
    is "installed". Verified empirically against the probe DB: with ``public``
    appended, unqualified ``CREATE TABLE`` still lands in the throwaway schema
    (it is first in path), matching a normal production connection's default
    search_path (``"$user", public``), which always includes ``public``.
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


@pytest.mark.postgres
@pytest.mark.integration
def test_create_postgresql_indexes_succeeds_on_fresh_schema(
    fresh_pg_schema_conn: Any,
) -> None:
    """The tables-then-indexes bootstrap phase pair succeeds end-to-end against real
    PostgreSQL on a completely fresh schema.

    Proves the incident was NOT upgrade-only: on a brand-new schema, CREATE TABLE
    already ships ``files.content_stale`` (no additive migration needed), so
    ``idx_files_content_stale`` is created in the very same pass that first creates
    the table -- exactly the sequence a fresh-project bootstrap runs, and exactly
    where the ``boolean = integer`` crash was reproduced against real prod Postgres.
    """
    from code_analysis.core.database.postgres_schema_ddl import (
        create_postgresql_indexes,
        create_postgresql_tables,
    )
    from code_analysis.core.database.schema_definition import get_schema_definition

    conn = fresh_pg_schema_conn
    schema = get_schema_definition()

    create_postgresql_tables(conn, schema)
    created = create_postgresql_indexes(conn, schema)  # must not raise

    assert any("idx_files_content_stale" in stmt for stmt in created)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = current_schema() "
            "AND indexname = 'idx_files_content_stale'"
        )
        row = cur.fetchone()
    assert row is not None, "idx_files_content_stale was not created"
    assert "content_stale = 1" not in row[0]


@pytest.mark.postgres
@pytest.mark.integration
def test_ensure_postgres_schema_once_end_to_end_on_fresh_schema(
    fresh_pg_schema_conn: Any,
) -> None:
    """The full connection-time bootstrap (``_ensure_postgres_schema_once``) succeeds
    end-to-end against real PostgreSQL -- the exact call that crash-looped
    ``_ensure_postgres_schema_once -> create_postgresql_indexes`` in the 1.6.76
    deploy. Also exercises the 1.6.75 ordering fix (tables -> content_stale
    migration -> indexes) on the same real server, so both deploy incidents are
    covered by one live run.
    """
    from code_analysis.core.database.schema_definition import get_schema_definition
    from code_analysis.core.database_driver_pkg.drivers.postgres_migrations import (
        _ensure_postgres_schema_once,
    )

    conn = fresh_pg_schema_conn
    schema = get_schema_definition()

    _ensure_postgres_schema_once(conn, schema, vector_dim=8)  # must not raise

    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'files' AND column_name = 'content_stale'"
        )
        assert cur.fetchone() is not None
        cur.execute(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = current_schema() "
            "AND indexname = 'idx_files_content_stale'"
        )
        assert cur.fetchone() is not None


def _declared_embedding_vec_dim(conn: Any) -> int:
    """Parse the declared ``vector(N)`` dimension of ``code_chunks.embedding_vec``."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a "
            "WHERE a.attrelid = 'code_chunks'::regclass "
            "AND a.attname = 'embedding_vec' "
            "AND NOT a.attisdropped"
        )
        row = cur.fetchone()
    assert row is not None, "embedding_vec column not found"
    match = re.fullmatch(r"vector\((\d+)\)", row[0])
    assert match is not None, f"unexpected format_type: {row[0]!r}"
    return int(match.group(1))


def _seed_project_file_and_chunk(
    conn: Any, *, dim: int, vectorization_skipped: int
) -> tuple[str, str, str]:
    """Insert one project + file + code_chunks row with a ``dim``-length embedding.

    Returns ``(project_id, file_id, chunk_id)``. Follows the same seeding idiom as
    ``test_postgres_file_sync_dml_real_pg.py``'s ``_bootstrap_and_seed_file``.
    """
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    server_instance_id = str(uuid.uuid4())
    vec_literal = "[" + ",".join(["1"] * dim) + "]"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO projects (id, server_instance_id, root_path) "
            "VALUES (%s, %s, %s)",
            (project_id, server_instance_id, "/tmp/catest_pgvector_retype"),
        )
        cur.execute(
            "INSERT INTO files (id, project_id, path, relative_path) "
            "VALUES (%s, %s, %s, %s)",
            (file_id, project_id, "/tmp/catest_pgvector_retype/a.py", "a.py"),
        )
        cur.execute(
            "INSERT INTO code_chunks "
            "(id, file_id, project_id, chunk_uuid, chunk_type, chunk_text, "
            "embedding_vec, embedding_vector, embedding_model, "
            "vectorization_skipped) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                chunk_id,
                file_id,
                project_id,
                chunk_id,
                "function",
                "def f(): pass",
                vec_literal,
                vec_literal,
                "test-model",
                vectorization_skipped,
            ),
        )
    conn.commit()
    return project_id, file_id, chunk_id


@pytest.mark.postgres
@pytest.mark.integration
def test_ensure_schema_reconciles_embedding_vec_dimension_change(
    fresh_pg_schema_conn: Any,
) -> None:
    """Bug f4dd4039: a changed configured ``vector_dim`` must retype an EXISTING
    ``embedding_vec`` column, not just add-if-missing.

    Pre-fix, ``_ensure_pgvector_embedding_column`` only ever ADDs the column when
    absent (``_ensure_missing_column`` returns immediately when it already exists),
    so a configured ``vector_dim`` change (e.g. 8 -> 16, prod incident was 384 ->
    1024) never reached an existing column -- writes then failed with
    ``psycopg.errors.DataException: expected <old> dimensions, not <new>`` until the
    DB was fixed by hand.

    This seeds a chunk at ``vector_dim=8``, re-runs the bootstrap at
    ``vector_dim=16``, and asserts: the column is retyped to ``vector(16)``; the
    HNSW index survives under the same name and stays valid; the old row's
    ``embedding_vec`` was discarded (``USING NULL`` -- values cannot be
    reinterpreted across dimensions); its stale JSON cache
    (``embedding_vector`` / ``embedding_model``) was invalidated so re-embedding
    goes through the full path instead of replaying a wrong-dimension cache; a
    16-dim insert now succeeds and an 8-dim insert now fails.
    """
    from code_analysis.core.database.schema_definition import get_schema_definition
    from code_analysis.core.database_driver_pkg.drivers.postgres_migrations import (
        _ensure_postgres_schema_once,
    )
    from code_analysis.core.vectorization_worker_pkg.batch_processor import (
        VECTORIZATION_DEAD_LETTER_SKIPPED_VALUE,
    )

    conn = fresh_pg_schema_conn
    schema = get_schema_definition()

    _ensure_postgres_schema_once(conn, schema, vector_dim=8)
    assert _declared_embedding_vec_dim(conn) == 8

    _project_id, _file_id, chunk_id = _seed_project_file_and_chunk(
        conn, dim=8, vectorization_skipped=VECTORIZATION_DEAD_LETTER_SKIPPED_VALUE
    )

    _ensure_postgres_schema_once(conn, schema, vector_dim=16)

    assert _declared_embedding_vec_dim(conn) == 16

    with conn.cursor() as cur:
        cur.execute(
            "SELECT indexrelid::regclass::text, indisvalid FROM pg_index "
            "WHERE indrelid = 'code_chunks'::regclass "
            "AND indexrelid::regclass::text = 'idx_code_chunks_embedding_vec_hnsw'"
        )
        idx_row = cur.fetchone()
    assert idx_row is not None, "HNSW index must survive the retype under its name"
    assert idx_row[1] is True, "HNSW index must remain valid after the retype"

    with conn.cursor() as cur:
        cur.execute(
            "SELECT embedding_vec, embedding_vector, embedding_model, "
            "vectorization_skipped FROM code_chunks WHERE id = %s",
            (chunk_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] is None, "old-dimension embedding_vec must be discarded"
    assert row[1] is None, "stale embedding_vector JSON cache must be invalidated"
    assert row[2] is None, "stale embedding_model must be cleared with the cache"
    assert row[3] == 0, (
        "dead-letter flag must be cleared for a row invalidated by the retype "
        "so it re-enters the vectorization queue"
    )

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO code_chunks "
            "(id, file_id, project_id, chunk_uuid, chunk_type, chunk_text, "
            "embedding_vec) "
            "SELECT gen_random_uuid(), file_id, project_id, "
            "gen_random_uuid()::text, chunk_type, chunk_text, "
            "%s FROM code_chunks WHERE id = %s",
            ("[" + ",".join(["1"] * 16) + "]", chunk_id),
        )
    conn.commit()

    with pytest.raises(Exception):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO code_chunks "
                "(id, file_id, project_id, chunk_uuid, chunk_type, chunk_text, "
                "embedding_vec) "
                "SELECT gen_random_uuid(), file_id, project_id, "
                "gen_random_uuid()::text, chunk_type, chunk_text, "
                "%s FROM code_chunks WHERE id = %s",
                ("[" + ",".join(["1"] * 8) + "]", chunk_id),
            )
        conn.commit()
    conn.rollback()


@pytest.mark.postgres
@pytest.mark.integration
def test_ensure_schema_embedding_vec_dimension_reconcile_is_idempotent(
    fresh_pg_schema_conn: Any,
) -> None:
    """Running the bootstrap twice at the SAME ``vector_dim`` must be a no-op fast
    path: the column's ``atttypmod`` and existing data must be unchanged (no
    spurious retype / no data loss when nothing actually changed)."""
    from code_analysis.core.database.schema_definition import get_schema_definition
    from code_analysis.core.database_driver_pkg.drivers.postgres_migrations import (
        _ensure_postgres_schema_once,
    )

    conn = fresh_pg_schema_conn
    schema = get_schema_definition()

    _ensure_postgres_schema_once(conn, schema, vector_dim=8)
    _project_id, _file_id, chunk_id = _seed_project_file_and_chunk(
        conn, dim=8, vectorization_skipped=0
    )

    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.atttypmod FROM pg_attribute a "
            "WHERE a.attrelid = 'code_chunks'::regclass "
            "AND a.attname = 'embedding_vec' AND NOT a.attisdropped"
        )
        typmod_before = cur.fetchone()[0]

    _ensure_postgres_schema_once(conn, schema, vector_dim=8)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.atttypmod FROM pg_attribute a "
            "WHERE a.attrelid = 'code_chunks'::regclass "
            "AND a.attname = 'embedding_vec' AND NOT a.attisdropped"
        )
        typmod_after = cur.fetchone()[0]
        cur.execute(
            "SELECT embedding_vec, embedding_vector, embedding_model "
            "FROM code_chunks WHERE id = %s",
            (chunk_id,),
        )
        row = cur.fetchone()

    assert typmod_after == typmod_before
    assert row is not None
    assert row[0] is not None, "idempotent same-dim run must not wipe data"
    assert row[1] is not None, "idempotent same-dim run must not touch the JSON cache"
    assert row[2] == "test-model"
