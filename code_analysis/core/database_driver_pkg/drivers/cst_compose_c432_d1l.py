"""
Connection-time schema ensure for PostgreSQL (idempotent CREATE TABLE / INDEX).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from code_analysis.core.database.schema_sync_models import IndexDef
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


def _ensure_missing_column(
    conn: Any,
    *,
    table_name: str,
    column_name: str,
    add_sql: str,
) -> None:
    """ALTER TABLE ADD COLUMN when missing (CREATE TABLE IF NOT EXISTS does not upgrade)."""
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
        logger.info("PostgreSQL migrate: adding column %s.%s", table_name, column_name)
        cur.execute(add_sql)
    conn.commit()


def idempotent_ensure_project_activity_locks_table(
    conn: Any, schema_definition: Dict[str, Any]
) -> None:
    """
    Create project_activity_locks and idx_project_activity_locks_lease_until if missing.

    Uses the same DDL as create_postgresql_schema for this table (CREATE IF NOT EXISTS).
    Safe to run repeatedly; no SQLite-only syntax.
    """
    if "project_activity_locks" not in schema_definition.get("tables", {}):
        return
    with conn.cursor() as cur:
        cur.execute(
            generate_create_table_sql_postgres(
                schema_definition, "project_activity_locks"
            )
        )
        for idx in schema_definition.get("indexes", []):
            if idx.get("name") != "idx_project_activity_locks_lease_until":
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


def ensure_postgres_schema(conn: Any, schema_definition: Dict[str, Any]) -> None:
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
        # Step 12: explicit idempotent pass (CREATE IF NOT EXISTS) for the lease table and index.
        idempotent_ensure_project_activity_locks_table(conn, schema_definition)
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
