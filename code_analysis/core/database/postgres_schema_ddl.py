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


def create_postgresql_schema(
    pg_conn: Any,
    schema_definition: Dict[str, Any],
    *,
    if_not_exists: bool = True,  # reserved: all DDL uses IF NOT EXISTS
) -> List[str]:
    """
    Run CREATE TABLE / CREATE INDEX on an open psycopg connection.

    Virtual (FTS5) tables from the schema definition are not created on PostgreSQL.

    Returns:
        List of DDL statements executed (for logging).
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

        for idx in schema_definition.get("indexes", []):
            idef = IndexDef(
                name=idx["name"],
                table=idx["table"],
                columns=list(idx["columns"]),
                unique=bool(idx.get("unique")),
                where_clause=idx.get("where_clause"),
            )
            idx_sql = generate_create_index_sql_postgres(idef)
            cur.execute(idx_sql)
            executed.append(idx_sql[:200] + ("..." if len(idx_sql) > 200 else ""))

    pg_conn.commit()
    _ = if_not_exists
    return executed
