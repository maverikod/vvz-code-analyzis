"""
Real-PostgreSQL regression test for the watcher bulk-sync soft-delete-collision
defect (bug 6d5ad353).

``build_watcher_bulk_sync_program``'s disk-driven ``LEFT JOIN`` only matched
ACTIVE ``files`` rows (``{active_f}`` in the join's ``ON`` clause). A file that
was soft-deleted (``files.deleted = TRUE``) and then reappears on disk at the
same ``(project_id, path)`` -- e.g. it was purged by the watcher's ignore
policy and the ignore pattern was later relaxed, or a legitimate delete/restore
race -- gets ``action = 'insert'`` (since the join found no ACTIVE match), and
``INSERT ... ON CONFLICT (project_id, path) DO NOTHING`` then silently no-ops
against the existing soft-deleted row (the unique index has no ``deleted``
qualifier, so there can only ever be one row per ``(project_id, path)``). The
file is never resurrected and stays unindexed forever, even though it is
present and unchanged on disk.

Requires ``CODE_ANALYSIS_POSTGRES_TEST_DSN``; skipped when unset -- same
optional live-PostgreSQL convention as ``test_postgres_schema_bootstrap_real_pg.py``
/ ``test_postgres_file_sync_dml_real_pg.py``. Runs in its own throwaway
PostgreSQL schema (dropped ``CASCADE`` on teardown).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Iterator, List, Optional, Tuple

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


class _ExecuteBatchShim:
    """Minimal ``database`` stand-in: routes ``execute``/``execute_batch`` through
    the real driver's ``postgres_run`` helpers on a raw psycopg connection, so
    ``submit_watcher_bulk_sync`` runs its exact production SQL (and, after the
    fix, its trailing stats SELECT) against a real server without standing up a
    full ``PostgreSQLDriver`` connection pool."""

    _driver_type = "postgres"

    def __init__(self, conn: Any, schema_tables: dict) -> None:
        self._conn = conn
        self._schema_tables = schema_tables

    def execute(self, sql: str, params: Optional[tuple]) -> dict:
        """Execute."""
        from code_analysis.core.database_driver_pkg.drivers import postgres_run

        result = postgres_run.run_execute(
            self._conn, sql, params, None, None, self._schema_tables
        )
        self._conn.commit()
        return result

    def execute_batch(
        self, operations: List[Tuple[str, Optional[tuple]]]
    ) -> List[dict]:
        """Execute batch."""
        from code_analysis.core.database_driver_pkg.drivers import postgres_run

        result = postgres_run.run_execute_batch(
            self._conn, operations, None, None, self._schema_tables
        )
        self._conn.commit()
        return result


def _bootstrap_and_seed_soft_deleted_file(conn: Any) -> Tuple[str, str, str, dict]:
    """Bootstrap the real schema and insert one project + one soft-deleted
    ``files`` row. Returns ``(project_id, file_id, relative_path, schema_definition)``."""
    from code_analysis.core.database.schema_definition import get_schema_definition
    from code_analysis.core.database_driver_pkg.drivers.postgres_migrations import (
        _ensure_postgres_schema_once,
    )

    schema = get_schema_definition()
    _ensure_postgres_schema_once(conn, schema, vector_dim=8)

    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    server_instance_id = str(uuid.uuid4())
    relative_path = "a.py"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO projects (id, server_instance_id, root_path) "
            "VALUES (%s, %s, %s)",
            (project_id, server_instance_id, "/tmp/catest"),
        )
        cur.execute(
            "INSERT INTO files (id, project_id, path, relative_path, deleted, "
            "tree_checksum, last_modified, lines, has_docstring) "
            "VALUES (%s, %s, %s, %s, TRUE, %s, %s, %s, %s)",
            (file_id, project_id, relative_path, relative_path, "abc123", 100.0, 10, False),
        )
    conn.commit()
    return project_id, file_id, relative_path, schema


@pytest.mark.postgres
@pytest.mark.integration
def test_resurrect_soft_deleted_file_seen_again_on_disk(
    fresh_pg_schema_conn: Any,
) -> None:
    """A file soft-deleted in the DB, then present again on disk with the SAME
    checksum (the worst case: no content-based change to trigger the 'update'
    action on its own) must be resurrected (``deleted = FALSE``) by the bulk
    sync, not silently dropped by ``ON CONFLICT ... DO NOTHING`` against the
    pre-existing soft-deleted row. Also asserts the resurrected file is
    reflected in the returned QUEUE stats (counted as ``changed_files`` -- see
    ``watcher_bulk_sync.submit_watcher_bulk_sync`` docstring)."""
    from code_analysis.core.file_watcher_pkg.watcher_bulk_sync import (
        submit_watcher_bulk_sync,
    )
    from code_analysis.core.file_watcher_pkg.watcher_disk_manifest import (
        WatcherDiskFileRow,
    )

    conn = fresh_pg_schema_conn
    project_id, file_id, relative_path, schema = _bootstrap_and_seed_soft_deleted_file(
        conn
    )
    shim = _ExecuteBatchShim(conn, schema["tables"])

    # Same tree_checksum/last_modified as the seeded (soft-deleted) row: on disk
    # the file's content never changed while it was marked deleted -- proves the
    # resurrect path does not depend on a coincidental content difference.
    disk_rows = [
        WatcherDiskFileRow(
            relative_path=relative_path,
            last_modified=100.0,
            lines=10,
            has_docstring=False,
            tree_checksum="abc123",
        )
    ]

    stats = submit_watcher_bulk_sync(shim, project_id, None, disk_rows)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT deleted, needs_chunking FROM files WHERE id = %s", (file_id,)
        )
        row = cur.fetchone()
    assert row is not None, "resurrected row must still exist (not purged)"
    deleted, needs_chunking = row
    assert deleted is False, (
        "soft-deleted file seen again on disk must be resurrected "
        "(deleted=FALSE), not left deleted by ON CONFLICT DO NOTHING"
    )
    assert needs_chunking == 1, "resurrected file must be queued for re-chunking"

    # QUEUE stats: resurrected files are counted as changed_files (they go
    # through the same 'update' SQL action as any other on-disk change).
    assert stats.get("changed_files", 0) == 1
    assert stats.get("new_files", 0) == 0
    assert stats.get("deleted_files", 0) == 0


@pytest.mark.postgres
@pytest.mark.integration
def test_normal_insert_update_delete_and_stats_unaffected_by_resurrect_fix(
    fresh_pg_schema_conn: Any,
) -> None:
    """Regression guard for the LEFT JOIN widening: an ordinary ACTIVE row still
    gets 'skip' when unchanged, 'update' when its content changed, a brand-new
    disk path still gets 'insert', and a row missing from the disk manifest
    still gets purged (bulk sync's 'delete' action runs the full FK-safe
    cascade delete, not a soft-delete -- see
    ``build_file_purge_sql_deletes_for_temp_table``) -- all in one sync call,
    with matching stats."""
    from code_analysis.core.database.schema_definition import get_schema_definition
    from code_analysis.core.database_driver_pkg.drivers.postgres_migrations import (
        _ensure_postgres_schema_once,
    )
    from code_analysis.core.file_watcher_pkg.watcher_bulk_sync import (
        submit_watcher_bulk_sync,
    )
    from code_analysis.core.file_watcher_pkg.watcher_disk_manifest import (
        WatcherDiskFileRow,
    )

    conn = fresh_pg_schema_conn
    schema = get_schema_definition()
    _ensure_postgres_schema_once(conn, schema, vector_dim=8)

    project_id = str(uuid.uuid4())
    server_instance_id = str(uuid.uuid4())
    unchanged_id = str(uuid.uuid4())
    changed_id = str(uuid.uuid4())
    to_delete_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO projects (id, server_instance_id, root_path) "
            "VALUES (%s, %s, %s)",
            (project_id, server_instance_id, "/tmp/catest2"),
        )
        cur.execute(
            "INSERT INTO files (id, project_id, path, relative_path, deleted, "
            "tree_checksum, last_modified, lines, has_docstring) VALUES "
            "(%s, %s, 'unchanged.py', 'unchanged.py', FALSE, 'same', 100.0, 5, FALSE), "
            "(%s, %s, 'changed.py', 'changed.py', FALSE, 'old', 100.0, 5, FALSE), "
            "(%s, %s, 'gone.py', 'gone.py', FALSE, 'x', 100.0, 5, FALSE)",
            (
                unchanged_id,
                project_id,
                changed_id,
                project_id,
                to_delete_id,
                project_id,
            ),
        )
    conn.commit()

    shim = _ExecuteBatchShim(conn, schema["tables"])
    disk_rows = [
        WatcherDiskFileRow(
            relative_path="unchanged.py",
            last_modified=100.0,
            lines=5,
            has_docstring=False,
            tree_checksum="same",
        ),
        WatcherDiskFileRow(
            relative_path="changed.py",
            last_modified=200.0,
            lines=6,
            has_docstring=False,
            tree_checksum="new",
        ),
        WatcherDiskFileRow(
            relative_path="brand_new.py",
            last_modified=300.0,
            lines=1,
            has_docstring=False,
            tree_checksum="fresh",
        ),
        # "gone.py" intentionally absent -> must be soft-deleted.
    ]

    stats = submit_watcher_bulk_sync(shim, project_id, None, disk_rows)

    assert stats.get("new_files", 0) == 1
    assert stats.get("changed_files", 0) == 1
    assert stats.get("deleted_files", 0) == 1

    with conn.cursor() as cur:
        cur.execute(
            "SELECT relative_path, deleted, needs_chunking, tree_checksum "
            "FROM files WHERE project_id = %s ORDER BY relative_path",
            (project_id,),
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["unchanged.py"] == (False, 0, "same")
    assert rows["changed.py"] == (False, 1, "new")
    assert "gone.py" not in rows, "row missing on disk must be purged, not left behind"
    assert rows["brand_new.py"][0] is False
    assert rows["brand_new.py"][1] == 1
