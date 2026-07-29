"""
PostgreSQL CRUD helpers (%s placeholders, same behavior as SQLite operations).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from ..exceptions import DriverOperationError
from .base import DbIdentity

logger = logging.getLogger(__name__)

# Callers often pass SQLite-style 0/1 for BOOLEAN columns; PostgreSQL needs IS TRUE/NOT TRUE.
_BOOL_FALSEY = (0, False)
_BOOL_TRUTHY = (1, True)

# Schema uses BOOLEAN; callers often pass SQLite-style 0/1 integers. Every column the
# schema definition marks BOOLEAN (schema_definition_tables_core.py) must be listed
# here, or a dict-based driver.insert()/update()/select() call with a bare 0/1 for
# that column raises "operator does not exist: boolean = integer" on real PostgreSQL
# (the incident #3 defect class -- content_stale, is_abstract, has_pass, and
# has_not_implemented were missing from this set until the fix that added this
# comment; see test_postgres_dml_boolean_literal_guard.py for the drift guard that
# cross-checks this set against the schema definition).
_PG_BOOL_COLUMNS = frozenset(
    {
        "deleted",
        "has_docstring",
        "processing_paused",
        "content_stale",
        "is_abstract",
        "has_pass",
        "has_not_implemented",
    }
)


def _coerce_pg_boolean_values(data: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce 0/1 to bool for SET/INSERT into PostgreSQL BOOLEAN columns."""
    if not data:
        return data
    out: Dict[str, Any] = {}
    for col, val in data.items():
        if col in _PG_BOOL_COLUMNS and isinstance(val, int) and val in (0, 1):
            out[col] = bool(val)
        else:
            out[col] = val
    return out


def _normalize_postgres_returning_pk(value: Any) -> DbIdentity:
    """Map RETURNING primary key cell to universal driver identity (int or str).

    Never coerce non-integer PKs to ``0`` — UUID and TEXT ids must surface as strings.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        return value
    if value is None:
        raise DriverOperationError("INSERT RETURNING produced NULL primary key")
    return str(value)


def _postgres_where_clauses(
    where: Dict[str, Any],
) -> tuple[list[str], list[Any]]:
    """Build WHERE fragments and bind values for portable bool vs 0/1.

    Column-set-driven (over ``_PG_BOOL_COLUMNS``, not a hardcoded per-column
    if/elif chain) so a column added to that set is automatically handled here
    too -- the two used to drift independently (incident #3: ``content_stale``,
    ``is_abstract``, ``has_pass``, ``has_not_implemented`` were BOOLEAN in the
    schema but absent from both this function's dispatch and the old
    ``_PG_BOOL_COLUMNS``).
    """
    clauses: list[str] = []
    values: list[Any] = []
    for col, val in where.items():
        if col in _PG_BOOL_COLUMNS and val in _BOOL_FALSEY:
            clauses.append(f"({col} IS NOT TRUE OR {col} IS NULL)")
            continue
        if col in _PG_BOOL_COLUMNS and val in _BOOL_TRUTHY:
            clauses.append(f"({col} IS TRUE)")
            continue
        clauses.append(f"{col} = %s")
        values.append(val)
    return clauses, values


class PostgreSQLOperations:
    """Thread-safe CRUD for PostgreSQL driver."""

    def __init__(self, connection: Any, schema_tables: Dict[str, Any]) -> None:
        """Initialize the instance."""
        self.conn = connection
        self._schema_tables = schema_tables
        self._lock = threading.Lock()

    def _returning_column(self, table_name: str) -> str:
        """Return returning column."""
        t = self._schema_tables.get(table_name, {})
        for c in t.get("columns", []):
            if c.get("primary_key"):
                return str(c["name"])
        return "id"

    def insert(self, table_name: str, data: Dict[str, Any]) -> Optional[DbIdentity]:
        """Return insert."""
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        with self._lock:
            try:
                data = _coerce_pg_boolean_values(data)
                columns = list(data.keys())
                values = tuple(data.values())
                placeholders = ", ".join(["%s"] * len(values))
                rcol = self._returning_column(table_name)
                sql = (
                    f'INSERT INTO "{table_name}" ({", ".join(columns)}) '
                    f"VALUES ({placeholders}) RETURNING {rcol}"
                )
                cursor = self.conn.cursor()
                try:
                    cursor.execute(sql, values)
                    row = cursor.fetchone()
                    self.conn.commit()
                    if not row or row[0] is None:
                        return None
                    return _normalize_postgres_returning_pk(row[0])
                finally:
                    cursor.close()
            except Exception as e:
                self.conn.rollback()
                raise DriverOperationError(f"Failed to insert row: {e}") from e

    def update(
        self, table_name: str, where: Dict[str, Any], data: Dict[str, Any]
    ) -> int:
        """Return update."""
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        with self._lock:
            try:
                data = _coerce_pg_boolean_values(data)
                set_clauses = []
                set_values: List[Any] = []
                for col, val in data.items():
                    set_clauses.append(f"{col} = %s")
                    set_values.append(val)

                where_clauses, where_values = _postgres_where_clauses(where)

                sql = (
                    f'UPDATE "{table_name}" SET {", ".join(set_clauses)} '
                    f'WHERE {" AND ".join(where_clauses)}'
                )
                cursor = self.conn.cursor()
                try:
                    cursor.execute(sql, tuple(set_values + where_values))
                    self.conn.commit()
                    return cursor.rowcount if cursor.rowcount >= 0 else 0
                finally:
                    cursor.close()
            except Exception as e:
                self.conn.rollback()
                raise DriverOperationError(f"Failed to update rows: {e}") from e

    def delete(self, table_name: str, where: Dict[str, Any]) -> int:
        """Return delete."""
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        with self._lock:
            try:
                where_clauses, where_values = _postgres_where_clauses(where)

                sql = f'DELETE FROM "{table_name}" WHERE {" AND ".join(where_clauses)}'
                cursor = self.conn.cursor()
                try:
                    cursor.execute(sql, tuple(where_values))
                    self.conn.commit()
                    return cursor.rowcount if cursor.rowcount >= 0 else 0
                finally:
                    cursor.close()
            except Exception as e:
                self.conn.rollback()
                raise DriverOperationError(f"Failed to delete rows: {e}") from e

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[str]] = None,
        *,
        connection: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Return select.

        Unlike insert/update/delete (main connection + ``self._lock``), select()
        never touches ``self.conn`` and takes no lock: it always runs on a
        caller-supplied ``connection`` (bug 8e6acb34 -- routing reads off the
        single main connection under an unbounded lock was a process-wide read
        bottleneck). ``PostgreSQLDriver.select()`` is the only production caller;
        it leases ``connection`` from ``PostgreSQLConnectionPool``'s read lane via
        ``pool.acquire(write=False)``, mirroring how ``run_execute`` receives an
        already-acquired connection rather than acquiring one itself.

        ``connection`` is keyword-only and required in practice -- ``None`` raises
        ``DriverOperationError`` immediately, the same contract as the old
        "connection not established" guard.
        """
        conn = connection
        if conn is None:
            raise DriverOperationError("Database connection not established")

        try:
            select_clause = ", ".join(columns) if columns else "*"
            sql = f'SELECT {select_clause} FROM "{table_name}"'

            where_values: List[Any] = []
            if where:
                where_clauses, where_values = _postgres_where_clauses(where)
                sql += f' WHERE {" AND ".join(where_clauses)}'

            if order_by:
                sql += f' ORDER BY {", ".join(order_by)}'

            if limit is not None:
                sql += f" LIMIT {int(limit)}"
                if offset is not None:
                    sql += f" OFFSET {int(offset)}"
            elif offset is not None:
                sql += f" OFFSET {int(offset)}"

            cursor = conn.cursor()
            try:
                cursor.execute(sql, tuple(where_values))
                cols = (
                    [d[0] for d in cursor.description] if cursor.description else []
                )
                rows = cursor.fetchall()
                out = [dict(zip(cols, row)) for row in rows]
            finally:
                cursor.close()
            # With autocommit=False, a SELECT opens an implicit transaction. If we
            # return without commit, the session stays "idle in transaction" until
            # the next lease of this pooled connection — long CPU/IO gaps can hit
            # idle_in_transaction_session_timeout and kill the connection, breaking
            # whichever caller next leases this slot. End the read-only txn here.
            try:
                conn.commit()
            except Exception as commit_err:
                msg = str(commit_err).lower()
                if "no transaction" in msg or "cannot commit" in msg:
                    logger.debug(
                        "PostgreSQL select: commit skipped (%s)", commit_err
                    )
                else:
                    raise DriverOperationError(
                        f"Failed to commit after select: {commit_err}"
                    ) from commit_err
            return out
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            raise DriverOperationError(f"Failed to select rows: {e}") from e
