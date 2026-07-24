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
    """Open connection with an isolated, empty PostgreSQL schema as sole search_path.

    Creates ``catest_<random>``, points the session's ``search_path`` at it (so every
    unqualified DDL/query the bootstrap code issues -- including its
    ``current_schema()``-scoped ``information_schema`` lookups -- resolves inside the
    throwaway schema), yields the open connection, then drops the schema ``CASCADE``
    and closes the connection.
    """
    pytest.importorskip("psycopg")
    import psycopg

    dsn = _live_dsn()
    schema_name = f"catest_{uuid.uuid4().hex[:16]}"
    conn = psycopg.connect(dsn)
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {schema_name}")
        cur.execute(f"SET search_path TO {schema_name}")
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
