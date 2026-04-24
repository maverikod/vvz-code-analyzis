"""
Copy data from SQLite (code_analysis.db) into PostgreSQL.

Creates PostgreSQL schema from get_schema_definition() when requested, then
copies rows in FK-safe order. SQLite FTS5 virtual tables are skipped (content
lives in regular tables). Identity columns use OVERRIDING SYSTEM VALUE so
existing ids are preserved; sequences are realigned after load.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .schema_definition import get_schema_definition
from .schema_sync_models import IndexDef
from .schema_sync_sql import tables_recreate_order
from .schema_sync_sql_postgres import (
    generate_create_index_sql_postgres,
    generate_create_table_sql_postgres,
)

logger = logging.getLogger(__name__)


def _sqlite_table_names(conn: sqlite3.Connection) -> Set[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return {str(r[0]) for r in cur.fetchall()}


def _table_has_identity(schema_definition: Dict[str, Any], table_name: str) -> bool:
    for col in schema_definition["tables"][table_name]["columns"]:
        if (
            col.get("primary_key")
            and col.get("autoincrement")
            and str(col.get("type", "")).upper() in ("INTEGER", "INT")
        ):
            return True
    return False


def _identity_pk_column(
    schema_definition: Dict[str, Any], table_name: str
) -> Optional[str]:
    for col in schema_definition["tables"][table_name]["columns"]:
        if (
            col.get("primary_key")
            and col.get("autoincrement")
            and str(col.get("type", "")).upper() in ("INTEGER", "INT")
        ):
            return str(col["name"])
    return None


def create_postgresql_schema(
    pg_conn: Any,
    schema_definition: Dict[str, Any],
    *,
    if_not_exists: bool = True,  # reserved: all DDL uses IF NOT EXISTS
) -> List[str]:
    """
    Run CREATE TABLE / CREATE INDEX on an open psycopg connection.

    Virtual (FTS5) tables from the SQLite schema are not created on PostgreSQL.

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


def _row_values(row: sqlite3.Row) -> Tuple[Any, ...]:
    return tuple(row[c] for c in row.keys())


def _dedupe_code_chunks_rows(rows: List[sqlite3.Row]) -> List[sqlite3.Row]:
    """SQLite may contain duplicate chunk_uuid; PostgreSQL enforces uniqueness."""
    if not rows or "chunk_uuid" not in rows[0].keys():
        return rows
    best: Dict[Any, sqlite3.Row] = {}
    no_uuid: List[sqlite3.Row] = []
    for r in rows:
        u = r["chunk_uuid"]
        if u is None or u == "":
            no_uuid.append(r)
            continue
        cur = best.get(u)
        if cur is None or r["id"] < cur["id"]:
            best[u] = r
    return list(best.values()) + no_uuid


def sqlite_code_chunks_expected_row_count_for_postgres(sl: sqlite3.Connection) -> int:
    """
    Row count PostgreSQL will have after migrate, matching _dedupe_code_chunks_rows:
    all rows with NULL/empty chunk_uuid, plus one row per non-empty chunk_uuid.
    """
    n_nullish = sl.execute(
        "SELECT COUNT(*) FROM code_chunks WHERE chunk_uuid IS NULL OR chunk_uuid = ''"
    ).fetchone()[0]
    n_distinct_nonempty = sl.execute(
        "SELECT COUNT(DISTINCT chunk_uuid) FROM code_chunks "
        "WHERE chunk_uuid IS NOT NULL AND chunk_uuid != ''"
    ).fetchone()[0]
    return int(n_nullish) + int(n_distinct_nonempty)


def _adapt_row_for_postgres(
    row: sqlite3.Row,
    table_name: str,
    schema_definition: Dict[str, Any],
    column_order: List[str],
) -> Tuple[Any, ...]:
    """Coerce SQLite values (e.g. 0/1 integers) to PostgreSQL types (BOOLEAN)."""
    tdef = schema_definition["tables"].get(table_name, {})
    type_by_name = {
        str(c["name"]): str(c.get("type", "TEXT")).upper()
        for c in tdef.get("columns", [])
    }
    out: List[Any] = []
    for col in column_order:
        v = row[col]
        ct = type_by_name.get(col, "TEXT")
        if v is None:
            out.append(None)
        elif ct in ("BOOLEAN", "BOOL"):
            if isinstance(v, (int, float)):
                out.append(bool(int(v)))
            else:
                out.append(v)
        elif ct == "BLOB":
            if isinstance(v, memoryview):
                out.append(v.tobytes())
            else:
                out.append(v)
        else:
            out.append(v)
    return tuple(out)


def migrate_sqlite_to_postgresql(
    sqlite_path: str | Path,
    pg_conn: Any,
    *,
    schema_definition: Optional[Dict[str, Any]] = None,
    create_schema: bool = True,
    copy_data: bool = True,
) -> Dict[str, Any]:
    """
    Migrate SQLite database content into PostgreSQL.

    Args:
        sqlite_path: Path to .db file.
        pg_conn: Open psycopg connection (autocommit off is fine).
        schema_definition: Defaults to get_schema_definition().
        create_schema: When True, run CREATE TABLE / INDEX first.
        copy_data: When True, copy rows for every table present in both DBs.

    Returns:
        Summary dict with tables_copied, rows_per_table, errors.
    """
    try:
        import psycopg  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "psycopg is required. Install with: pip install 'psycopg[binary]>=3.1' or pip install -e ."
        ) from e

    schema_definition = schema_definition or get_schema_definition()
    sqlite_path = Path(sqlite_path)

    summary: Dict[str, Any] = {
        "sqlite_path": str(sqlite_path.resolve()),
        "created_schema": False,
        "tables_copied": [],
        "rows_per_table": {},
        "sequences_reset": [],
        "errors": [],
    }

    if create_schema:
        create_postgresql_schema(pg_conn, schema_definition)
        summary["created_schema"] = True

    if not copy_data:
        return summary

    sl = sqlite3.connect(str(sqlite_path))
    sl.row_factory = sqlite3.Row
    try:
        sqlite_tables = _sqlite_table_names(sl)
        schema_tables: Set[str] = set(schema_definition["tables"].keys())
        to_copy = [
            t
            for t in tables_recreate_order(
                schema_definition, schema_tables & sqlite_tables
            )
        ]

        vt_names = {v["name"] for v in schema_definition.get("virtual_tables", [])}
        to_copy = [t for t in to_copy if t not in vt_names]

        with pg_conn.cursor() as pg_cur:
            for table in to_copy:
                sl_cur = sl.execute(f"SELECT * FROM {table}")
                rows = sl_cur.fetchall()
                if table == "code_chunks":
                    rows = _dedupe_code_chunks_rows(list(rows))
                if not rows:
                    summary["rows_per_table"][table] = 0
                    continue
                tdef = schema_definition["tables"].get(table, {})
                schema_order = [c["name"] for c in tdef.get("columns", [])]
                sqlite_keys = set(rows[0].keys())
                if schema_order:
                    cols = [c for c in schema_order if c in sqlite_keys]
                else:
                    cols = list(rows[0].keys())
                placeholders = ", ".join(["%s"] * len(cols))
                col_list = ", ".join(f'"{c}"' for c in cols)
                use_ov = _table_has_identity(schema_definition, table)
                if use_ov:
                    insert_sql = (
                        f'INSERT INTO "{table}" ({col_list}) '
                        f"OVERRIDING SYSTEM VALUE VALUES ({placeholders})"
                    )
                else:
                    insert_sql = (
                        f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'
                    )
                batch = [
                    _adapt_row_for_postgres(r, table, schema_definition, cols)
                    for r in rows
                ]
                pg_cur.executemany(insert_sql, batch)
                summary["rows_per_table"][table] = len(batch)
                summary["tables_copied"].append(table)

            # Align identity sequences
            for table in summary["tables_copied"]:
                pkcol = _identity_pk_column(schema_definition, table)
                if not pkcol:
                    continue
                try:
                    pg_cur.execute(
                        f"SELECT setval(pg_get_serial_sequence(%s, %s), "
                        f'(SELECT COALESCE(MAX("{pkcol}"), 1) FROM "{table}"), true)',
                        (table, pkcol),
                    )
                    seq = pg_cur.fetchone()
                    summary["sequences_reset"].append(
                        {
                            "table": table,
                            "column": pkcol,
                            "setval": seq[0] if seq else None,
                        }
                    )
                except Exception as ex:
                    logger.warning(
                        "Could not reset sequence for %s.%s: %s", table, pkcol, ex
                    )
                    summary["errors"].append(f"sequence_reset:{table}:{ex}")

        pg_conn.commit()
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sl.close()

    return summary
