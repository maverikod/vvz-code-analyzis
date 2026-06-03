"""
Connection-time schema ensure for PostgreSQL (idempotent CREATE TABLE / INDEX).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, cast

from code_analysis.core.database.schema_sync_models import IndexDef
from code_analysis.core.database_driver_pkg.drivers.postgres_run import (
    _sqlite_qmarks_to_psycopg,
)
from code_analysis.core.database.schema_sync_sql_postgres import (
    generate_create_index_sql_postgres,
    generate_create_table_sql_postgres,
)
from code_analysis.core.database.sqlite_to_postgres import create_postgresql_schema

logger = logging.getLogger(__name__)

# Session advisory lock: prevents concurrent CREATE TABLE IF NOT EXISTS on a cold DB
# from racing on pg_type_typname_nsp_index (duplicate typname for the same table).
# See PostgreSQL concurrent DDL on identical new relation names.
_SCHEMA_ENSURE_LOCK_KEY1 = 425_001_707
_SCHEMA_ENSURE_LOCK_KEY2 = 91_735


def _rollback_conn(conn: Any) -> None:
    try:
        conn.rollback()
    except Exception:
        pass


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
            cur.execute(generate_create_index_sql_postgres(idef))
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


def idempotent_ensure_client_session_tables(
    conn: Any, schema_definition: Dict[str, Any]
) -> None:
    """
    Create client-session tables and indexes if missing.

    Uses the same DDL as create_postgresql_schema for these tables (CREATE IF NOT EXISTS).
    Safe to run repeatedly; no SQLite-only syntax.
    """
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
            cur.execute(generate_create_index_sql_postgres(idef))
    conn.commit()


class _PostgresConnMigrateAdapter:
    """Minimal db-like surface for schema_creation_migrate (PostgreSQL connect path)."""

    _driver_type = "postgres"

    def __init__(self, conn: Any, schema_manager: Any) -> None:
        self._conn = conn
        self._schema_manager = schema_manager

    def _get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        return cast(
            List[Dict[str, Any]], self._schema_manager.get_table_info(table_name)
        )

    def _execute(self, sql: str, params: Any = None) -> None:
        pg_sql, pg_params = _sqlite_qmarks_to_psycopg(sql, params)
        try:
            with self._conn.cursor() as cur:
                cur.execute(pg_sql, pg_params)
            self._conn.commit()
        except Exception:
            _rollback_conn(self._conn)
            raise

    def _fetchone(self, sql: str, params: Any = None) -> Optional[Dict[str, Any]]:
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
    """Create tables and indexes if missing (FTS5 virtual tables are not created)."""
    locked = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_lock(%s, %s)",
                (_SCHEMA_ENSURE_LOCK_KEY1, _SCHEMA_ENSURE_LOCK_KEY2),
            )
        locked = True
        create_postgresql_schema(conn, schema_definition)
        # Explicit idempotent pass for runtime lock tables and indexes.
        idempotent_ensure_runtime_lock_tables(conn, schema_definition)
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
        # run_migrate_schema / sqlite_migrations editing_pid).
        _ensure_missing_column(
            conn,
            table_name="files",
            column_name="editing_pid",
            add_sql="ALTER TABLE files ADD COLUMN editing_pid INTEGER DEFAULT NULL",
        )
        _ensure_pgvector_embedding_column(conn, vector_dim)
        from .postgres_schema import PostgreSQLSchemaManager

        _ensure_watch_dirs_server_instance_partition(
            conn, PostgreSQLSchemaManager(conn)
        )
    finally:
        if locked:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT pg_advisory_unlock(%s, %s)",
                        (_SCHEMA_ENSURE_LOCK_KEY1, _SCHEMA_ENSURE_LOCK_KEY2),
                    )
            except Exception as exc:
                logger.warning("pg_advisory_unlock failed (non-fatal): %s", exc)
