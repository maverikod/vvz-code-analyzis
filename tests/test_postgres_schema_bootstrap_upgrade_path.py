"""
Upgrade-path regression tests for the PostgreSQL connection-time schema bootstrap
(1.6.75 deploy incident).

Mechanism: ``_ensure_postgres_schema_once`` used to run the FULL table set
(``CREATE TABLE IF NOT EXISTS``, a no-op on a pre-existing table shape) and then
the FULL index set — including ``idx_files_content_stale``, a partial index on
``files.content_stale`` — before the additive column migration
(``migrate_files_content_stale_column``) had ever run. On any database with a
pre-existing ``files`` table missing that column, ``CREATE INDEX`` raised
``psycopg.errors.UndefinedColumn`` deterministically. Fresh databases were
unaffected (the column ships with ``CREATE TABLE`` on a brand-new table), which is
why the local suite and the fresh-project pipeline check never caught it.

Fix: split ``create_postgresql_schema`` into ``create_postgresql_tables`` /
``create_postgresql_indexes`` and run the additive column migration for
``files.content_stale`` / ``files.content_stale_since`` between the two phases.

These tests use a lightweight in-memory fake PostgreSQL connection/cursor (no real
DB, no ``psycopg`` server round-trip) that tracks table columns and created
indexes, and raises the same ``psycopg.errors.UndefinedColumn`` a real PostgreSQL
server would when a ``CREATE INDEX`` references a column the target table does not
have. This keeps the tests fast, deterministic, and independent of any live
database while still exercising the real production DDL-generation and bootstrap
code (``create_postgresql_tables``, ``create_postgresql_indexes``,
``_ensure_postgres_schema_once``, ``migrate_files_content_stale_column``) rather
than reimplementing their logic.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

import pytest
from psycopg import errors as pg_errors

from code_analysis.core.database.postgres_schema_ddl import (
    create_postgresql_indexes,
    create_postgresql_tables,
)
from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database_driver_pkg.drivers.postgres_migrations import (
    _ensure_postgres_schema_once,
)

# SQL keywords/literals that can appear as bare identifiers in a partial index's
# WHERE clause or column list but are never column names — filtered out before
# checking referenced identifiers against the fake table's known columns.
_SQL_NOISE_WORDS = {
    "AND",
    "OR",
    "IS",
    "NOT",
    "NULL",
    "TRUE",
    "FALSE",
    "WHERE",
}


def _referenced_identifiers(fragment: str) -> Set[str]:
    """Return bare SQL identifiers in ``fragment``, minus keywords/literals."""
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", fragment)
    return {t for t in tokens if t.upper() not in _SQL_NOISE_WORDS}


class _FakeCursor:
    """Minimal cursor double: recognizes the specific SQL shapes this module's
    production code issues and mutates/reads ``_FakePgConn`` state accordingly.
    Anything unrecognized is a harmless no-op (mirrors how the real bootstrap
    tolerates unrelated migrations touching tables this fixture does not model)."""

    def __init__(self, conn: "_FakePgConn") -> None:
        """Initialize the instance."""
        self._conn = conn
        self._last_rows: List[Tuple[Any, ...]] = []

    def __enter__(self) -> "_FakeCursor":
        """Return the cursor for ``with conn.cursor() as cur:`` usage."""
        return self

    def __exit__(self, *exc: Any) -> None:
        """No teardown needed."""
        return None

    def close(self) -> None:
        """No-op: matches real cursor's ``close()`` used outside a ``with`` block."""
        return None

    def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> None:
        """Interpret one SQL statement against the fake connection's state."""
        s = " ".join(sql.split())  # normalize whitespace
        upper = s.upper()
        self._last_rows = []

        if "PG_ADVISORY_LOCK" in upper or "PG_ADVISORY_UNLOCK" in upper:
            self._last_rows = [(1,)]
            return

        if "FROM INFORMATION_SCHEMA.TABLES" in upper:
            table = params[0] if params else _extract_literal(s, "table_name")
            self._last_rows = [(1,)] if table in self._conn.tables else []
            return

        if "COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT" in upper:
            table = params[0] if params else _extract_literal(s, "table_name")
            cols = self._conn.tables.get(table, set())
            self._last_rows = [(c, "text", "YES", None) for c in sorted(cols)]
            return

        if "KEY_COLUMN_USAGE" in upper:
            # Primary-key introspection: not modeled (no test here depends on PK
            # shape); an empty result is a safe, non-fatal default.
            self._last_rows = []
            return

        if "INFORMATION_SCHEMA.COLUMNS" in upper:
            if params and len(params) >= 2:
                table, column = params[0], params[1]
            else:
                table = _extract_literal(s, "table_name")
                column = _extract_literal(s, "column_name")
            self._last_rows = (
                [(1,)] if column in self._conn.tables.get(table, set()) else []
            )
            return

        if "SELECT 1 FROM DB_SETTINGS" in upper:
            key = params[0] if params else _extract_literal(s, "key")
            self._last_rows = [(1,)] if key in self._conn.db_settings else []
            return

        if upper.startswith("INSERT INTO DB_SETTINGS"):
            if params:
                self._conn.db_settings[params[0]] = params[1]
            return

        if upper.startswith("CREATE TABLE IF NOT EXISTS"):
            m = re.match(r"CREATE TABLE IF NOT EXISTS (\w+)", s, re.IGNORECASE)
            assert m, f"unrecognized CREATE TABLE statement: {s!r}"
            table = m.group(1)
            if table not in self._conn.tables:
                cols = {
                    c["name"]
                    for c in self._conn.schema_definition["tables"][table]["columns"]
                }
                self._conn.tables[table] = cols
            return

        if "CREATE" in upper and "INDEX IF NOT EXISTS" in upper:
            m = re.match(
                r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+) ON (\w+)\s*"
                r"\(([^)]*)\)(?:\s+WHERE\s+(.*))?$",
                s,
                re.IGNORECASE,
            )
            assert m, f"unrecognized CREATE INDEX statement: {s!r}"
            idx_name, table, cols_part, where_part = m.groups()
            referenced = _referenced_identifiers(cols_part)
            if where_part:
                referenced |= _referenced_identifiers(where_part)
            known = self._conn.tables.get(table, set())
            missing = referenced - known
            if missing:
                raise pg_errors.UndefinedColumn(
                    f'column "{sorted(missing)[0]}" does not exist '
                    f"(index {idx_name} on {table})"
                )
            self._conn.indexes[idx_name] = table
            return

        if upper.startswith("ALTER TABLE") and "ADD COLUMN" in upper:
            m = re.match(
                r"ALTER TABLE (\w+) ADD COLUMN (\w+)", s, re.IGNORECASE
            )
            assert m, f"unrecognized ALTER TABLE statement: {s!r}"
            table, column = m.groups()
            self._conn.tables.setdefault(table, set()).add(column)
            return

        if upper.startswith("CREATE EXTENSION"):
            return

        # Anything else (unrelated migrations' own SQL: watch_dirs partitioning,
        # projects root-path segmenting, legacy subordinate_sessions probe, ...)
        # is out of scope for this fixture and safely no-ops.
        return

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        """Return the first buffered row, or ``None``."""
        return self._last_rows[0] if self._last_rows else None

    def fetchall(self) -> List[Tuple[Any, ...]]:
        """Return all buffered rows."""
        return list(self._last_rows)

    @property
    def description(self) -> List[Tuple[str, ...]]:
        """Return a description tuple compatible with ``zip(cols, row)`` callers."""
        return [("col",)] * (len(self._last_rows[0]) if self._last_rows else 0)


def _extract_literal(sql: str, column: str) -> Optional[str]:
    """Extract a single-quoted literal ``<column> = '<value>'`` from raw SQL text
    (fallback for the rare hardcoded-literal query with no ``%s`` params, e.g. the
    legacy ``subordinate_sessions`` probe)."""
    m = re.search(rf"{column}\s*=\s*'([^']*)'", sql)
    return m.group(1) if m else None


class _FakePgConn:
    """In-memory double for an open psycopg connection.

    ``tables`` maps table name -> set of column names; ``indexes`` maps index
    name -> table name (existence only, sufficient for these tests).
    """

    def __init__(
        self,
        schema_definition: Dict[str, Any],
        *,
        preexisting_tables: Optional[Dict[str, Set[str]]] = None,
    ) -> None:
        """Initialize the instance."""
        self.schema_definition = schema_definition
        self.tables: Dict[str, Set[str]] = {
            k: set(v) for k, v in (preexisting_tables or {}).items()
        }
        self.indexes: Dict[str, str] = {}
        self.db_settings: Dict[str, str] = {}
        self.committed = 0
        self.rolled_back = 0

    def cursor(self) -> _FakeCursor:
        """Return a fresh fake cursor bound to this connection's state."""
        return _FakeCursor(self)

    def commit(self) -> None:
        """Record a commit (no real transaction to flush)."""
        self.committed += 1

    def rollback(self) -> None:
        """Record a rollback (no real transaction to unwind)."""
        self.rolled_back += 1


def _old_shape_files_columns(schema_definition: Dict[str, Any]) -> Set[str]:
    """Return the real ``files`` column set MINUS the additive content_stale
    columns — i.e. the shape of a ``files`` table from before bug 56c23bd9's
    migration existed, which is exactly the pre-existing production shape that
    triggered the 1.6.75 deploy incident."""
    all_cols = {c["name"] for c in schema_definition["tables"]["files"]["columns"]}
    return all_cols - {"content_stale", "content_stale_since"}


# ---------------------------------------------------------------------------
# (a) RED: reproduce the incident directly — old table order (tables -> indexes,
# no migration in between) against a pre-existing old-shape files table.
# ---------------------------------------------------------------------------


def test_old_order_reproduces_undefined_column_on_pre_existing_files_table() -> None:
    """Bug mechanism proof: tables-then-indexes with NO migration in between
    (the pre-fix order) raises UndefinedColumn on a pre-existing old-shape
    ``files`` table — same failure as the 1.6.75 deploy incident."""
    schema = get_schema_definition()
    conn = _FakePgConn(
        schema,
        preexisting_tables={"files": _old_shape_files_columns(schema)},
    )

    create_postgresql_tables(conn, schema)  # no-op on pre-existing files table
    with pytest.raises(pg_errors.UndefinedColumn, match="content_stale"):
        create_postgresql_indexes(conn, schema)


# ---------------------------------------------------------------------------
# (a) GREEN: the fixed bootstrap succeeds against the same pre-existing
# old-shape files table, and the column + index exist afterward.
# ---------------------------------------------------------------------------


def test_ensure_postgres_schema_once_upgrades_pre_existing_old_shape_files_table() -> (
    None
):
    """Fixed bootstrap order: tables -> content_stale migration -> indexes
    succeeds against a pre-existing old-shape ``files`` table, and both the
    column and the dependent partial index exist afterward."""
    schema = get_schema_definition()
    conn = _FakePgConn(
        schema,
        preexisting_tables={"files": _old_shape_files_columns(schema)},
    )

    _ensure_postgres_schema_once(conn, schema, vector_dim=8)

    assert "content_stale" in conn.tables["files"]
    assert "content_stale_since" in conn.tables["files"]
    assert conn.indexes.get("idx_files_content_stale") == "files"


# ---------------------------------------------------------------------------
# (b) regression: fresh-database path (no pre-existing tables) stays green.
# ---------------------------------------------------------------------------


def test_ensure_postgres_schema_once_still_succeeds_on_fresh_database() -> None:
    """Regression: a brand-new database (files table created fresh, column comes
    with CREATE TABLE) is unaffected by the reordering fix."""
    schema = get_schema_definition()
    conn = _FakePgConn(schema)

    _ensure_postgres_schema_once(conn, schema, vector_dim=8)

    assert "content_stale" in conn.tables["files"]
    assert "content_stale_since" in conn.tables["files"]
    assert conn.indexes.get("idx_files_content_stale") == "files"
