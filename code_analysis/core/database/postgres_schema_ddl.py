"""
Create PostgreSQL schema (CREATE TABLE / CREATE INDEX) from get_schema_definition().

Split out of the former ``sqlite_to_postgres.py`` (SQLite removed): this module
has no SQLite dependency — it only generates and runs PostgreSQL DDL on an open
psycopg connection. Used by the connection-time schema-ensure driver modules.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from .schema_sync_models import IndexDef
from .schema_sync_sql import tables_recreate_order
from .schema_sync_sql_postgres import (
    generate_create_index_sql_postgres,
    generate_create_table_sql_postgres,
)


def create_postgresql_tables(
    pg_conn: Any,
    schema_definition: Dict[str, Any],
    *,
    if_not_exists: bool = True,  # reserved: all DDL uses IF NOT EXISTS
) -> List[str]:
    """
    Run CREATE TABLE on an open psycopg connection (tables phase only).

    Split out of ``create_postgresql_schema`` (1.6.75 deploy incident,
    ``UndefinedColumn`` on ``idx_files_content_stale``): callers that need to run
    additive column migrations against a pre-existing table shape (``CREATE TABLE IF
    NOT EXISTS`` is a no-op on an existing table — it never adds new columns) MUST do
    so between this call and :func:`create_postgresql_indexes`, never call the
    combined :func:`create_postgresql_schema` when a schema-definition index may
    reference a column that only an additive migration provides.

    Returns:
        List of CREATE TABLE DDL statements executed (for logging).
    """
    executed: List[str] = []
    tables = schema_definition.get("tables", {})
    names: Set[str] = set(tables.keys())
    ordered = tables_recreate_order(schema_definition, names)

    with pg_conn.cursor() as cur:
        for tname in ordered:
            ddl = generate_create_table_sql_postgres(schema_definition, tname)
            cur.execute(ddl)
            executed.append(ddl[:200] + ("..." if len(ddl) > 200 else ""))

    pg_conn.commit()
    _ = if_not_exists
    return executed


def create_postgresql_indexes(
    pg_conn: Any,
    schema_definition: Dict[str, Any],
) -> List[str]:
    """
    Run CREATE INDEX on an open psycopg connection (indexes phase only).

    Must run AFTER both :func:`create_postgresql_tables` and any additive column
    migrations the schema's indexes depend on (see that function's docstring) —
    otherwise a partial/expression index referencing a not-yet-added column raises
    ``psycopg.errors.UndefinedColumn`` deterministically.

    Returns:
        List of CREATE INDEX DDL statements executed (for logging).
    """
    executed: List[str] = []
    with pg_conn.cursor() as cur:
        for idx in schema_definition.get("indexes", []):
            idef = IndexDef(
                name=idx["name"],
                table=idx["table"],
                columns=list(idx["columns"]),
                unique=bool(idx.get("unique")),
                where_clause=idx.get("where_clause"),
            )
            idx_sql = generate_create_index_sql_postgres(idef, schema_definition)
            cur.execute(idx_sql)
            executed.append(idx_sql[:200] + ("..." if len(idx_sql) > 200 else ""))

    pg_conn.commit()
    return executed


def create_postgresql_schema(
    pg_conn: Any,
    schema_definition: Dict[str, Any],
    *,
    if_not_exists: bool = True,  # reserved: all DDL uses IF NOT EXISTS
) -> List[str]:
    """
    Run CREATE TABLE / CREATE INDEX on an open psycopg connection.

    Virtual (FTS5) tables from the schema definition are not created on PostgreSQL.
    Convenience wrapper over :func:`create_postgresql_tables` +
    :func:`create_postgresql_indexes` for callers that do not need additive column
    migrations run between the two phases (e.g. a fresh database, or a caller that
    only ever creates the small self-contained table/index subsets that carry no
    such dependency). The connection-time bootstrap (``postgres_migrations.py``)
    does NOT use this combined form — it needs the migration step in between.

    Returns:
        List of DDL statements executed (for logging).
    """
    executed = create_postgresql_tables(
        pg_conn, schema_definition, if_not_exists=if_not_exists
    )
    executed += create_postgresql_indexes(pg_conn, schema_definition)
    return executed
