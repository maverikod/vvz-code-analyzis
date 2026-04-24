"""
PostgreSQL CRUD helpers (%s placeholders, same behavior as SQLite operations).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from ..exceptions import DriverOperationError

logger = logging.getLogger(__name__)

# Callers often pass SQLite-style 0/1 for BOOLEAN columns; PostgreSQL needs IS TRUE/NOT TRUE.
_BOOL_FALSEY = (0, False)
_BOOL_TRUTHY = (1, True)

# Schema uses BOOLEAN; callers often pass SQLite-style 0/1 integers.
_PG_BOOL_COLUMNS = frozenset({"deleted", "has_docstring", "processing_paused"})


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


def _postgres_where_clauses(
    where: Dict[str, Any],
) -> tuple[list[str], list[Any]]:
    """Build WHERE fragments and bind values for portable bool vs 0/1."""
    clauses: list[str] = []
    values: list[Any] = []
    for col, val in where.items():
        if col == "deleted" and val in _BOOL_FALSEY:
            clauses.append("(deleted IS NOT TRUE OR deleted IS NULL)")
            continue
        if col == "deleted" and val in _BOOL_TRUTHY:
            clauses.append("(deleted IS TRUE)")
            continue
        if col == "has_docstring" and val in _BOOL_FALSEY:
            clauses.append("(has_docstring IS NOT TRUE OR has_docstring IS NULL)")
            continue
        if col == "has_docstring" and val in _BOOL_TRUTHY:
            clauses.append("(has_docstring IS TRUE)")
            continue
        if col == "processing_paused" and val in _BOOL_FALSEY:
            clauses.append(
                "(processing_paused IS NOT TRUE OR processing_paused IS NULL)"
            )
            continue
        if col == "processing_paused" and val in _BOOL_TRUTHY:
            clauses.append("(processing_paused IS TRUE)")
            continue
        clauses.append(f"{col} = %s")
        values.append(val)
    return clauses, values


class PostgreSQLOperations:
    """Thread-safe CRUD for PostgreSQL driver."""

    def __init__(self, connection: Any, schema_tables: Dict[str, Any]) -> None:
        self.conn = connection
        self._schema_tables = schema_tables
        self._lock = threading.Lock()

    def _returning_column(self, table_name: str) -> str:
        t = self._schema_tables.get(table_name, {})
        for c in t.get("columns", []):
            if c.get("primary_key"):
                return str(c["name"])
        return "id"

    def insert(self, table_name: str, data: Dict[str, Any]) -> int:
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
                    if row and row[0] is not None and isinstance(row[0], int):
                        return int(row[0])
                    return 0
                finally:
                    cursor.close()
            except Exception as e:
                self.conn.rollback()
                raise DriverOperationError(f"Failed to insert row: {e}") from e

    def update(
        self, table_name: str, where: Dict[str, Any], data: Dict[str, Any]
    ) -> int:
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
    ) -> List[Dict[str, Any]]:
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        with self._lock:
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

                cursor = self.conn.cursor()
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
                # the next RPC — long CPU/IO gaps (e.g. file_watcher scan) can hit
                # idle_in_transaction_session_timeout and kill the connection, breaking
                # unrelated commands (e.g. list_projects). End the read-only txn here.
                try:
                    self.conn.commit()
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
                    self.conn.rollback()
                except Exception:
                    pass
                raise DriverOperationError(f"Failed to select rows: {e}") from e
