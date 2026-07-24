"""
Real-PostgreSQL regression tests for the incident #3 DML boolean-literal defect
class (1.6.77 deploy GREEN sweep against real prod PostgreSQL):

    ClientValidationError('Failed to sync file to DB: execute_batch failed:
    column "content_stale" is of type boolean but expression is of type integer
    LINE 1: UPDATE files SET content_stale = 0, content_stale_since = NULL, ...')

This fired on ordinary file-sync (the reindex-success ``content_stale`` clear in
``code_analysis/core/database_client/file_data_batch.py``), breaking virtually
every file-upload-dependent command on PostgreSQL. It is the DML-side sibling of
the 1.6.76 index-DDL incident (#2; see ``test_postgres_index_boolean_where_rewrite.py``
/ ``test_postgres_schema_bootstrap_real_pg.py``), and of the 999cf82e incident (#1).

Root cause: ``code_analysis/core/database_driver_pkg/drivers/postgres_run.py``'s
``_adapt_sqlite_bool_int_assignments_for_postgres`` is the single chokepoint every
``driver.execute()`` / ``driver.execute_batch()`` statement passes through (via
``run_execute`` / ``run_execute_batch``) before reaching PostgreSQL. It rewrites
SQLite-style ``<col> = 0/1`` assignments to ``FALSE``/``TRUE`` for a column
allowlist, ``_BOOL_COL_INT_ASSIGN``. Pre-fix, that allowlist only contained
``deleted``, ``has_docstring``, ``processing_paused`` -- ``content_stale`` (added
later for bug 56c23bd9) is BOOLEAN in the schema but was never added to the
allowlist, so its raw ``= 0`` / ``= 1`` DML sailed through unrewritten.

The first test below proves the reproduction is genuine (not hypothetical): it
replays the exact pre-fix allowlist against a REAL disposable PostgreSQL and
captures the incident's exact error class. The second and third tests prove the
shipped fix -- both at the adapter level and through the actual production
``build_file_data_atomic_batches`` file-sync path -- execute cleanly and the
boolean value round-trips as a genuine Postgres boolean.

Requires ``CODE_ANALYSIS_POSTGRES_TEST_DSN`` (e.g.
``postgresql://user:pass@host/db``); skipped when unset -- same optional
live-PostgreSQL convention as ``test_postgres_schema_bootstrap_real_pg.py``. Each
test runs in its own throwaway PostgreSQL schema (dropped ``CASCADE`` on
teardown), so it is safe to point at a shared disposable test database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Iterator
from unittest.mock import patch

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

    Same pattern as ``test_postgres_schema_bootstrap_real_pg.py``'s fixture
    (duplicated rather than shared, matching this test suite's existing
    one-fixture-per-file convention for the real-PG test modules).
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


def _bootstrap_and_seed_file(conn: Any) -> tuple[str, str, dict]:
    """Bootstrap the real schema and insert one project + one (content_stale=TRUE)
    files row. Returns ``(project_id, file_id, schema_definition)``."""
    from code_analysis.core.database.schema_definition import get_schema_definition
    from code_analysis.core.database_driver_pkg.drivers.postgres_migrations import (
        _ensure_postgres_schema_once,
    )

    schema = get_schema_definition()
    _ensure_postgres_schema_once(conn, schema, vector_dim=8)

    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    server_instance_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO projects (id, server_instance_id, root_path) "
            "VALUES (%s, %s, %s)",
            (project_id, server_instance_id, "/tmp/catest"),
        )
        cur.execute(
            "INSERT INTO files (id, project_id, path, relative_path, content_stale) "
            "VALUES (%s, %s, %s, %s, TRUE)",
            (file_id, project_id, "/tmp/catest/a.py", "a.py"),
        )
    conn.commit()
    return project_id, file_id, schema


_PRE_FIX_BOOL_COL_INT_ASSIGN = ("deleted", "has_docstring", "processing_paused")

# Byte-identical shape to code_analysis/core/database_client/file_data_batch.py's
# reindex-success content_stale clear (the exact statement that fired incident #3).
_INCIDENT_SQL = (
    "UPDATE files SET content_stale = 0, content_stale_since = NULL, "
    "updated_at = (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)) WHERE id = ?"
)


@pytest.mark.postgres
@pytest.mark.integration
def test_prefix_allowlist_reproduces_incident_on_real_postgres(
    fresh_pg_schema_conn: Any,
) -> None:
    """Non-vacuous proof: replaying the incident's exact SQL through the PRE-FIX
    ``_BOOL_COL_INT_ASSIGN`` allowlist (content_stale absent) reproduces the exact
    "boolean ... integer" error against a real PostgreSQL server."""
    conn = fresh_pg_schema_conn
    _project_id, file_id, schema = _bootstrap_and_seed_file(conn)

    from code_analysis.core.database_driver_pkg.drivers import postgres_run

    with patch.object(
        postgres_run, "_BOOL_COL_INT_ASSIGN", _PRE_FIX_BOOL_COL_INT_ASSIGN
    ):
        with pytest.raises(Exception) as exc_info:
            postgres_run.run_execute(
                conn, _INCIDENT_SQL, (file_id,), None, None, schema["tables"]
            )
    conn.rollback()

    msg = str(exc_info.value)
    assert "content_stale" in msg
    assert "boolean" in msg.lower()
    assert "integer" in msg.lower()


@pytest.mark.postgres
@pytest.mark.integration
def test_fixed_allowlist_executes_and_round_trips_on_real_postgres(
    fresh_pg_schema_conn: Any,
) -> None:
    """The FIXED (shipped) ``_BOOL_COL_INT_ASSIGN`` executes the identical
    incident SQL cleanly against real PostgreSQL, and the boolean round-trips as
    a genuine Postgres boolean (``False``, not ``0``)."""
    conn = fresh_pg_schema_conn
    _project_id, file_id, schema = _bootstrap_and_seed_file(conn)

    from code_analysis.core.database_driver_pkg.drivers import postgres_run

    # Sanity: the shipped allowlist really does include content_stale (guards
    # against this test silently passing because someone reverted the fix).
    assert "content_stale" in postgres_run._BOOL_COL_INT_ASSIGN

    result = postgres_run.run_execute(
        conn, _INCIDENT_SQL, (file_id,), None, None, schema["tables"]
    )
    conn.commit()
    assert result["affected_rows"] == 1

    with conn.cursor() as cur:
        cur.execute("SELECT content_stale, content_stale_since FROM files WHERE id = %s", (file_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0] is False
    assert row[1] is None


@pytest.mark.postgres
@pytest.mark.integration
def test_build_file_data_atomic_batches_reindex_clear_round_trips_real_postgres(
    fresh_pg_schema_conn: Any,
) -> None:
    """True end-to-end: the REAL ``build_file_data_atomic_batches`` output (the
    actual production file-sync path that fired incident #3) executes cleanly
    against real PostgreSQL through the real ``execute_batch`` path, and its
    last batch (the reindex-success ``content_stale`` clear) round-trips
    correctly."""
    conn = fresh_pg_schema_conn
    project_id, file_id, schema = _bootstrap_and_seed_file(conn)

    from code_analysis.core.database_client.file_data_batch import (
        build_file_data_atomic_batches,
    )
    from code_analysis.core.database_driver_pkg.drivers import postgres_run

    source_code = "def f():\n    return 1\n"
    batches, meta = build_file_data_atomic_batches(
        file_id,
        project_id,
        source_code,
        "/tmp/catest/a.py",
        123456.0,
        driver_type="postgres",
    )
    assert meta.get("success") is True, meta

    for batch in batches:
        postgres_run.run_execute_batch(conn, batch, None, None, schema["tables"])
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT content_stale, content_stale_since FROM files WHERE id = %s",
            (file_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] is False, "content_stale must round-trip as a real Postgres boolean"
    assert row[1] is None
