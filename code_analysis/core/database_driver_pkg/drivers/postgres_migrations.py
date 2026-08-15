"""
Connection-time schema ensure for PostgreSQL (idempotent CREATE TABLE / INDEX).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, cast

from code_analysis.core.database.schema_sync_models import IndexDef
from code_analysis.core.database_driver_pkg.drivers.postgres_run import (
    _sqlite_qmarks_to_psycopg,
)
from code_analysis.core.database.schema_sync_sql_postgres import (
    generate_create_index_sql_postgres,
    generate_create_table_sql_postgres,
)
from code_analysis.core.database.postgres_schema_ddl import (
    create_postgresql_indexes,
    create_postgresql_tables,
)
from code_analysis.core.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)

# Session advisory lock: prevents concurrent CREATE TABLE IF NOT EXISTS on a cold DB
# from racing on pg_type_typname_nsp_index (duplicate typname for the same table).
# See PostgreSQL concurrent DDL on identical new relation names.
_SCHEMA_ENSURE_LOCK_KEY1 = 425_001_707
_SCHEMA_ENSURE_LOCK_KEY2 = 91_735

# Bug c5e8fb49 (boot race): concurrent cold-boot schema-ensure attempts can still
# collide with a PostgreSQL deadlock (40P01) or serialization failure (40001) even
# with the advisory lock, when a competing session is mid-DDL on an overlapping
# catalog row before it reaches the lock acquisition itself. The DDL body is
# idempotent (IF NOT EXISTS + guarded column adds), so a clean re-run is safe.
_SCHEMA_ENSURE_RETRY_POLICY = RetryPolicy(
    attempts=3,
    delay_seconds=0.5,
    backoff_multiplier=2.0,
    jitter_seconds=0.1,
)


def _rollback_conn(conn: Any) -> None:
    """Return rollback conn."""
    try:
        conn.rollback()
    except Exception:
        pass


def _postgres_table_exists(conn: Any, table_name: str) -> bool:
    """Return postgres table exists."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = %s
                LIMIT 1
                """,
                (table_name,),
            )
            return cur.fetchone() is not None
    except Exception:
        _rollback_conn(conn)
        return False


def _postgres_primary_key_column_names(conn: Any, table_name: str) -> List[str]:
    """Return ordered PK column names for a PostgreSQL table, or [] if none."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.attname
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                JOIN pg_namespace n ON t.relnamespace = n.oid
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
                WHERE c.contype = 'p'
                  AND t.relname = %s
                  AND n.nspname = current_schema()
                ORDER BY array_position(c.conkey, a.attnum)
                """,
                (table_name,),
            )
            return [str(row[0]) for row in cur.fetchall()]
    except Exception:
        _rollback_conn(conn)
        return []


def _watch_dirs_has_composite_pk(conn: Any) -> bool:
    """Return watch dirs has composite pk."""
    return _postgres_primary_key_column_names(conn, "watch_dirs") == [
        "server_instance_id",
        "id",
    ]


def _drop_empty_broken_watch_dirs_if_needed(conn: Any) -> None:
    """
    Drop empty legacy ``watch_dirs`` when PK does not match current schema.

    Handles a failed in-place PK migration (DROP committed, ADD not). Safe only
    when ``watch_dirs`` has no rows.
    """
    if not _postgres_table_exists(conn, "watch_dirs"):
        return
    if _watch_dirs_has_composite_pk(conn):
        return
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*)::bigint FROM watch_dirs")
            row_count = int(cur.fetchone()[0])
        if row_count != 0:
            return
        logger.warning(
            "watch_dirs PK=%s with 0 rows; dropping for schema recreate",
            _postgres_primary_key_column_names(conn, "watch_dirs") or None,
        )
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS watch_dir_paths CASCADE")
            cur.execute("DROP TABLE IF EXISTS watch_dirs CASCADE")
        conn.commit()
    except Exception as exc:
        _rollback_conn(conn)
        logger.warning("watch_dirs cleanup skipped: %s", exc)


def _ensure_missing_column(
    conn: Any,
    *,
    table_name: str,
    column_name: str,
    add_sql: str,
) -> None:
    """ALTER TABLE ADD COLUMN when missing (CREATE TABLE IF NOT EXISTS does not upgrade)."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                  AND column_name = %s
                LIMIT 1
                """,
                (table_name, column_name),
            )
            if cur.fetchone() is not None:
                return
            logger.info(
                "PostgreSQL migrate: adding column %s.%s", table_name, column_name
            )
            cur.execute(add_sql)
        conn.commit()
    except Exception as exc:
        _rollback_conn(conn)
        logger.warning(
            "PostgreSQL migrate: could not add column %s.%s: %s",
            table_name,
            column_name,
            exc,
        )


def idempotent_ensure_runtime_lock_tables(
    conn: Any, schema_definition: Dict[str, Any]
) -> None:
    """
    Create runtime/project lock tables and indexes if missing.

    Uses the same DDL as create_postgresql_schema for these tables (CREATE IF NOT EXISTS).
    Safe to run repeatedly; no SQLite-only syntax.
    """
    with conn.cursor() as cur:
        for table_name in (
            "project_activity_locks",
            "runtime_lock_sessions",
            "file_advisory_lock_leases",
        ):
            if table_name not in schema_definition.get("tables", {}):
                continue
            cur.execute(
                generate_create_table_sql_postgres(schema_definition, table_name)
            )
        for idx in schema_definition.get("indexes", []):
            if idx.get("table") not in {
                "project_activity_locks",
                "runtime_lock_sessions",
                "file_advisory_lock_leases",
            }:
                continue
            idef = IndexDef(
                name=idx["name"],
                table=idx["table"],
                columns=list(idx["columns"]),
                unique=bool(idx.get("unique")),
                where_clause=idx.get("where_clause"),
            )
            cur.execute(generate_create_index_sql_postgres(idef, schema_definition))
    conn.commit()


def idempotent_ensure_project_activity_locks_table(
    conn: Any, schema_definition: Dict[str, Any]
) -> None:
    """Backward-compatible wrapper for project/runtime lock table ensures."""
    idempotent_ensure_runtime_lock_tables(conn, schema_definition)


_CLIENT_SESSION_TABLES = (
    "client_sessions",
    "session_file_locks",
    "roles",
    "role_permissions",
    "session_roles",
    "subordinate_sessions",
)


def _migrate_legacy_subordinate_sessions_table(conn: Any) -> None:
    """Drop pre-1.0.7 subordinate_sessions shape that included subordinate_session_id."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'subordinate_sessions'
              AND column_name = 'subordinate_session_id'
            LIMIT 1
            """)
        if cur.fetchone() is None:
            return
        logger.info(
            "PostgreSQL migrate: dropping legacy subordinate_sessions with "
            "subordinate_session_id"
        )
        cur.execute("DROP TABLE subordinate_sessions CASCADE")
    # The caller owns the enclosing schema-ensure transaction and final commit.


def idempotent_ensure_client_session_tables(
    conn: Any, schema_definition: Dict[str, Any]
) -> None:
    """
    Create client-session tables and indexes if missing.

    Uses the same DDL as create_postgresql_schema for these tables (CREATE IF NOT EXISTS).
    Safe to run repeatedly; no SQLite-only syntax.
    """
    _migrate_legacy_subordinate_sessions_table(conn)
    with conn.cursor() as cur:
        for table_name in _CLIENT_SESSION_TABLES:
            if table_name not in schema_definition.get("tables", {}):
                continue
            cur.execute(
                generate_create_table_sql_postgres(schema_definition, table_name)
            )
        for idx in schema_definition.get("indexes", []):
            if idx.get("table") not in _CLIENT_SESSION_TABLES:
                continue
            idef = IndexDef(
                name=idx["name"],
                table=idx["table"],
                columns=list(idx["columns"]),
                unique=bool(idx.get("unique")),
                where_clause=idx.get("where_clause"),
            )
            cur.execute(generate_create_index_sql_postgres(idef, schema_definition))
    conn.commit()


class _PostgresConnMigrateAdapter:
    """Minimal db-like surface for schema_creation_migrate (PostgreSQL connect path)."""

    _driver_type = "postgres"

    def __init__(self, conn: Any, schema_manager: Any) -> None:
        """Initialize the instance."""
        self._conn = conn
        self._schema_manager = schema_manager

    def _get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Return get table info."""
        return cast(
            List[Dict[str, Any]], self._schema_manager.get_table_info(table_name)
        )

    def _execute(self, sql: str, params: Any = None) -> None:
        """Return execute."""
        pg_sql, pg_params = _sqlite_qmarks_to_psycopg(sql, params)
        try:
            with self._conn.cursor() as cur:
                cur.execute(pg_sql, pg_params)
            self._conn.commit()
        except Exception:
            _rollback_conn(self._conn)
            raise

    def _fetchone(self, sql: str, params: Any = None) -> Optional[Dict[str, Any]]:
        """Return fetchone."""
        pg_sql, pg_params = _sqlite_qmarks_to_psycopg(sql, params)
        try:
            with self._conn.cursor() as cur:
                cur.execute(pg_sql, pg_params)
                row = cur.fetchone()
                if row is None:
                    return None
                cols = [d[0] for d in cur.description or []]
                return dict(zip(cols, row))
        except Exception:
            _rollback_conn(self._conn)
            raise

    def _fetchall(self, sql: str, params: Any = None) -> List[Dict[str, Any]]:
        """Return fetchall."""
        pg_sql, pg_params = _sqlite_qmarks_to_psycopg(sql, params)
        try:
            with self._conn.cursor() as cur:
                cur.execute(pg_sql, pg_params)
                rows = cur.fetchall()
                if not rows:
                    return []
                cols = [d[0] for d in cur.description or []]
                return [dict(zip(cols, row)) for row in rows]
        except Exception:
            _rollback_conn(self._conn)
            raise

    def _commit(self) -> None:
        """Return commit."""
        self._conn.commit()


def _ensure_watch_dirs_server_instance_partition(
    conn: Any, schema_manager: Any
) -> None:
    """Add server_instance_id columns and indexes (shared PG; not in CREATE IF NOT EXISTS)."""
    from code_analysis.core.database.migrations.watch_dirs_server_instance import (
        migrate_watch_dirs_server_instance,
    )

    _rollback_conn(conn)
    try:
        migrate_watch_dirs_server_instance(
            _PostgresConnMigrateAdapter(conn, schema_manager)
        )
    except Exception as exc:
        _rollback_conn(conn)
        logger.warning(
            "PostgreSQL watch_dirs server_instance partition migration failed: %s",
            exc,
            exc_info=True,
        )


def _ensure_files_content_stale_columns(conn: Any, schema_manager: Any) -> None:
    """Add ``files.content_stale`` / ``files.content_stale_since`` (1.6.75 deploy incident).

    Unlike the other ``_ensure_*`` migrations in this module, this one MUST run
    before :func:`create_postgresql_indexes` in :func:`_ensure_postgres_schema_once`,
    not after: the schema definition's generic index list includes
    ``idx_files_content_stale``, a partial index on ``files.content_stale``
    (``schema_definition_indexes.py``). ``CREATE TABLE IF NOT EXISTS`` (the tables
    phase) is a no-op on a pre-existing ``files`` table — it never adds the new
    column — so creating that index before this migration raises
    ``psycopg.errors.UndefinedColumn`` deterministically on any database with a
    pre-existing ``files`` table (fresh databases are unaffected: the column ships
    with ``CREATE TABLE`` on a brand-new table, which is why the fresh-project
    pipeline never caught this).
    """
    from code_analysis.core.database.migrations.files_content_stale_column import (
        migrate_files_content_stale_column,
    )

    _rollback_conn(conn)
    try:
        migrate_files_content_stale_column(
            _PostgresConnMigrateAdapter(conn, schema_manager)
        )
    except Exception as exc:
        _rollback_conn(conn)
        logger.warning(
            "PostgreSQL files content_stale column migration failed: %s",
            exc,
            exc_info=True,
        )


def _ensure_watch_dirs_deleted_column(conn: Any, schema_manager: Any) -> None:
    """Add ``watch_dirs.deleted`` (shared PG; not applied by CREATE TABLE IF NOT EXISTS)."""
    from code_analysis.core.database.migrations.watch_dirs_deleted_column import (
        migrate_watch_dirs_deleted_column,
    )

    _rollback_conn(conn)
    try:
        migrate_watch_dirs_deleted_column(
            _PostgresConnMigrateAdapter(conn, schema_manager)
        )
    except Exception as exc:
        _rollback_conn(conn)
        logger.warning(
            "PostgreSQL watch_dirs deleted column migration failed: %s",
            exc,
            exc_info=True,
        )


def _ensure_project_exclusive_locks_table(conn: Any, schema_manager: Any) -> None:
    """Create ``project_exclusive_locks`` (new whole-project admin lock table, no TTL).

    Unlike ``_ensure_files_content_stale_columns`` above, this is a brand-new
    table (``CREATE TABLE IF NOT EXISTS``), not a new column on a pre-existing
    table, so there is no index-before-column-exists ordering hazard (see the
    1.6.75 deploy-incident comment in ``_ensure_postgres_schema_once``): no
    schema-definition index references ``project_exclusive_locks``, so this
    call is safe regardless of where it runs relative to
    ``create_postgresql_indexes()``.
    """
    from code_analysis.core.database.migrations.project_exclusive_locks_table import (
        migrate_project_exclusive_locks_table,
    )

    _rollback_conn(conn)
    try:
        migrate_project_exclusive_locks_table(
            _PostgresConnMigrateAdapter(conn, schema_manager)
        )
    except Exception as exc:
        _rollback_conn(conn)
        logger.warning(
            "PostgreSQL project_exclusive_locks table migration failed: %s",
            exc,
            exc_info=True,
        )


def _ensure_projects_root_path_migrations(conn: Any, schema_manager: Any) -> None:
    """Drop legacy global root_path UNIQUE; scope to server_instance_id (shared PG)."""
    from code_analysis.core.database.migrations.projects_root_segment_postgres import (
        migrate_projects_root_segment_postgres,
    )

    _rollback_conn(conn)
    try:
        migrate_projects_root_segment_postgres(
            _PostgresConnMigrateAdapter(conn, schema_manager)
        )
    except Exception as exc:
        _rollback_conn(conn)
        logger.warning(
            "PostgreSQL projects root_path migration failed: %s",
            exc,
            exc_info=True,
        )


_EMBEDDING_VEC_DIM_RE = re.compile(r"vector\((\d+)\)")


def _declared_pgvector_dim(conn: Any) -> Optional[int]:
    """Return the declared ``vector(N)`` dimension of ``code_chunks.embedding_vec``.

    Returns ``None`` if the column does not exist (nothing to reconcile) or its type
    cannot be parsed as ``vector(N)``.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                WHERE a.attrelid = 'code_chunks'::regclass
                  AND a.attname = 'embedding_vec'
                  AND NOT a.attisdropped
                """
            )
            row = cur.fetchone()
    except Exception as exc:
        _rollback_conn(conn)
        logger.warning(
            "PostgreSQL: could not read declared embedding_vec type: %s", exc
        )
        return None
    if row is None or row[0] is None:
        return None
    match = _EMBEDDING_VEC_DIM_RE.fullmatch(row[0])
    return int(match.group(1)) if match else None


def _invalidate_stale_embedding_json_caches(conn: Any, new_dim: int) -> None:
    """Clear ``embedding_vector``/``embedding_model`` cache entries that are not
    ``new_dim``-length, and un-dead-letter the rows this invalidates.

    Runs in Python (fetch + filter + batched UPDATE ... WHERE id = ANY(%s)) rather
    than a single ``embedding_vector::jsonb`` SQL cast: verified empirically against
    the probe DB that casting a garbage (non-JSON) ``embedding_vector`` value raises
    ``invalid input syntax for type json`` from the cast itself, before a
    ``jsonb_typeof`` WHERE guard ever runs -- so a single malformed row would abort
    the whole migration. Any row whose cache cannot be positively confirmed as
    ``new_dim``-length (malformed JSON included) is invalidated, matching the
    reconciliation's goal: no wrong-dimension cache may survive.
    """
    from code_analysis.core.vectorization_worker_pkg.batch_processor import (
        VECTORIZATION_DEAD_LETTER_SKIPPED_VALUE,
    )

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, embedding_vector FROM code_chunks "
            "WHERE embedding_vector IS NOT NULL"
        )
        rows = cur.fetchall()

    stale_ids: List[Any] = []
    for chunk_id, embedding_vector_json in rows:
        try:
            parsed = json.loads(embedding_vector_json)
            keep = isinstance(parsed, list) and len(parsed) == new_dim
        except (TypeError, ValueError):
            keep = False
        if not keep:
            stale_ids.append(chunk_id)

    if not stale_ids:
        return

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE code_chunks SET embedding_vector = NULL, embedding_model = NULL "
            "WHERE id = ANY(%s)",
            (stale_ids,),
        )
        cur.execute(
            "UPDATE code_chunks SET vectorization_skipped = 0 "
            "WHERE id = ANY(%s) AND vectorization_skipped = %s",
            (stale_ids, VECTORIZATION_DEAD_LETTER_SKIPPED_VALUE),
        )


def _reconcile_pgvector_embedding_dimension(conn: Any, dim: int) -> None:
    """Retype an EXISTING ``embedding_vec`` column when the configured dimension
    changed (bug f4dd4039).

    ``_ensure_missing_column`` above is purely additive -- it ADDs the column when
    absent but returns immediately when it already exists, so a changed configured
    ``vector_dim`` (e.g. 384 -> 1024) never reached an existing column. On the live
    server this bricked all embedding writes with ``psycopg.errors.DataException:
    expected 384 dimensions, not 1024`` until the DB was fixed by hand.

    Idempotent fast path: if the declared dimension already matches, do nothing.
    On a mismatch, retypes the column (``USING NULL`` -- values cannot be
    reinterpreted across dimensions, verified empirically that a ``::vector`` cast
    fails on mismatched data while ``USING NULL`` succeeds and the HNSW index
    survives under its existing name), invalidates now-wrong-dimension JSON caches,
    and un-dead-letters the rows it invalidates so they re-enter the vectorization
    queue.
    """
    declared_dim = _declared_pgvector_dim(conn)
    if declared_dim is None or declared_dim == dim:
        return

    logger.warning(
        "PostgreSQL: code_chunks.embedding_vec dimension changed %s -> %s; "
        "existing embeddings will be DISCARDED and re-vectorization will be "
        "required for all affected chunks",
        declared_dim,
        dim,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"ALTER TABLE code_chunks ALTER COLUMN embedding_vec "
                f"TYPE vector({dim}) USING NULL"
            )
        _invalidate_stale_embedding_json_caches(conn, dim)
        conn.commit()
    except Exception as exc:
        _rollback_conn(conn)
        logger.error(
            "PostgreSQL: embedding_vec dimension retype %s -> %s FAILED, column "
            "left at the OLD dimension: %s",
            declared_dim,
            dim,
            exc,
            exc_info=True,
        )


def _ensure_pgvector_embedding_column(conn: Any, vector_dim: int) -> None:
    """Create pgvector extension (if permitted), ``embedding_vec``, and HNSW index."""
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.commit()
    except Exception as exc:
        logger.warning(
            "PostgreSQL: CREATE EXTENSION vector failed (pgvector optional): %s",
            exc,
        )
        try:
            conn.rollback()
        except Exception:
            pass
        return

    dim = max(1, int(vector_dim))
    _ensure_missing_column(
        conn,
        table_name="code_chunks",
        column_name="embedding_vec",
        add_sql=f"ALTER TABLE code_chunks ADD COLUMN embedding_vec vector({dim})",
    )
    _reconcile_pgvector_embedding_dimension(conn, dim)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding_vec_hnsw
                ON code_chunks
                USING hnsw (embedding_vec vector_cosine_ops)
                """)
        conn.commit()
    except Exception as exc:
        logger.warning(
            "PostgreSQL: HNSW index on embedding_vec skipped (may retry later): %s",
            exc,
        )
        try:
            conn.rollback()
        except Exception:
            pass


def ensure_postgres_schema(
    conn: Any,
    schema_definition: Dict[str, Any],
    *,
    vector_dim: int = 384,
) -> None:
    """Create tables and indexes if missing (FTS5 virtual tables are not created).

    Retries the whole locked attempt (``_ensure_postgres_schema_once``) up to
    ``_SCHEMA_ENSURE_RETRY_POLICY.attempts`` times on PostgreSQL deadlock (40P01) or
    serialization failure (40001) — SQLSTATE class 40, transient errors that can still
    occur at cold-boot even with the advisory lock (see module docstring above the
    policy). The retry loop wraps the *whole* try/except/finally of a single attempt,
    not just its body: each attempt must re-acquire the advisory lock from a clean
    state, and the previous attempt's own ``finally`` has already rolled back and
    released that lock before the next attempt starts. Do not add a second lock here.
    """
    try:
        from psycopg import errors as pg_errors
    except ImportError:  # pragma: no cover - psycopg always available in production
        pg_errors = None  # type: ignore[assignment]

    retryable_excs: tuple = ()
    if pg_errors is not None:
        retryable_excs = (pg_errors.DeadlockDetected, pg_errors.SerializationFailure)

    max_attempts = _SCHEMA_ENSURE_RETRY_POLICY.attempts
    for attempt in range(1, max_attempts + 1):
        try:
            _ensure_postgres_schema_once(conn, schema_definition, vector_dim=vector_dim)
            return
        except retryable_excs as exc:
            if attempt >= max_attempts:
                logger.error(
                    "[DB_RETRY] backend=postgres layer=migrations "
                    "operation=ensure_postgres_schema attempt=%s/%s exhausted "
                    "sqlstate=%s error=%s",
                    attempt,
                    max_attempts,
                    getattr(exc, "sqlstate", None),
                    exc,
                )
                raise
            delay = _SCHEMA_ENSURE_RETRY_POLICY.delay_for_attempt(attempt)
            logger.warning(
                "[DB_RETRY] backend=postgres layer=migrations "
                "operation=ensure_postgres_schema attempt=%s/%s sqlstate=%s "
                "error=%s; retrying in %.2fs",
                attempt,
                max_attempts,
                getattr(exc, "sqlstate", None),
                exc,
                delay,
            )
            time.sleep(delay)
    raise RuntimeError(
        "ensure_postgres_schema: retry loop exited without result or exception"
    )


def _ensure_postgres_schema_once(
    conn: Any,
    schema_definition: Dict[str, Any],
    *,
    vector_dim: int = 384,
) -> None:
    """Single attempt: acquire advisory lock, run migrations, release lock."""
    locked = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_lock(%s, %s)",
                (_SCHEMA_ENSURE_LOCK_KEY1, _SCHEMA_ENSURE_LOCK_KEY2),
            )
        locked = True
        _rollback_conn(conn)
        _drop_empty_broken_watch_dirs_if_needed(conn)
        from .postgres_schema import PostgreSQLSchemaManager

        # ORDERING IS LOAD-BEARING (1.6.75 deploy incident): tables -> additive
        # column migrations that a schema-definition index depends on -> indexes.
        # create_postgresql_tables() is CREATE TABLE IF NOT EXISTS, a no-op on a
        # pre-existing table (does not add new columns). create_postgresql_indexes()
        # includes idx_files_content_stale, a partial index on files.content_stale.
        # Running indexes before the additive migration below raised
        # psycopg.errors.UndefinedColumn deterministically on any DB with a
        # pre-existing `files` table. Do NOT collapse this back into the combined
        # create_postgresql_schema() convenience wrapper.
        create_postgresql_tables(conn, schema_definition)
        _ensure_files_content_stale_columns(conn, PostgreSQLSchemaManager(conn))
        create_postgresql_indexes(conn, schema_definition)
        # Explicit idempotent pass for runtime lock tables and indexes.
        idempotent_ensure_runtime_lock_tables(conn, schema_definition)
        _ensure_project_exclusive_locks_table(conn, PostgreSQLSchemaManager(conn))
        idempotent_ensure_client_session_tables(conn, schema_definition)
        _ensure_missing_column(
            conn,
            table_name="code_chunks",
            column_name="vectorization_skipped",
            add_sql=(
                "ALTER TABLE code_chunks ADD COLUMN vectorization_skipped "
                "INTEGER DEFAULT 0"
            ),
        )
        # CREATE TABLE IF NOT EXISTS does not add columns to existing tables (same as SQLite
        # run_migrate_schema / sqlite_migrations editing_pid). No schema-definition index
        # references editing_pid, so (unlike content_stale above) running this after the
        # indexes phase is safe.
        _ensure_missing_column(
            conn,
            table_name="files",
            column_name="editing_pid",
            add_sql="ALTER TABLE files ADD COLUMN editing_pid INTEGER DEFAULT NULL",
        )
        _ensure_pgvector_embedding_column(conn, vector_dim)
        _ensure_watch_dirs_server_instance_partition(
            conn, PostgreSQLSchemaManager(conn)
        )
        _ensure_watch_dirs_deleted_column(conn, PostgreSQLSchemaManager(conn))
        _ensure_projects_root_path_migrations(conn, PostgreSQLSchemaManager(conn))
        conn.commit()
    except Exception as exc:
        _rollback_conn(conn)
        logger.warning("PostgreSQL schema ensure failed: %s", exc, exc_info=True)
        raise
    finally:
        if locked:
            try:
                _rollback_conn(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT pg_advisory_unlock(%s, %s)",
                        (_SCHEMA_ENSURE_LOCK_KEY1, _SCHEMA_ENSURE_LOCK_KEY2),
                    )
                conn.commit()
            except Exception as exc:
                _rollback_conn(conn)
                logger.warning("pg_advisory_unlock failed (non-fatal): %s", exc)
