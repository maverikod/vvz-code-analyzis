"""
Execute SQL for PostgreSQL driver (? placeholders → %%s, INSERT RETURNING for lastrowid).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ..exceptions import DriverOperationError
from .sqlite_batch import expand_operations, group_for_executemany, split_batch_sql

logger = logging.getLogger(__name__)

_INSERT_INTO_RE = re.compile(
    r"^\s*INSERT\s+INTO\s+(?:\"([^\"]+)\"|'([^']+)'|([a-zA-Z_][a-zA-Z0-9_]*))",
    re.IGNORECASE | re.DOTALL,
)


def _norm_sql_one_line(sql: str) -> str:
    return " ".join(sql.strip().rstrip(";").split())


# After ``julianday('now')`` → EXTRACT; matches indexing_worker batch upsert.
_INDEXING_ERRORS_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(
    "INSERT OR REPLACE INTO indexing_errors "
    "(project_id, file_path, error_type, error_message, created_at) "
    "VALUES (?, ?, ?, ?, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)))"
)

_WATCH_DIRS_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(
    "INSERT OR REPLACE INTO watch_dirs (id, name, updated_at) "
    "VALUES (?, ?, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)))"
)

_WATCH_DIR_PATHS_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(
    "INSERT OR REPLACE INTO watch_dir_paths (watch_dir_id, absolute_path, updated_at) "
    "VALUES (?, ?, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)))"
)

_WATCH_DIR_PATHS_INSERT_OR_REPLACE_NULL_PATH_NORM = _norm_sql_one_line(
    "INSERT OR REPLACE INTO watch_dir_paths (watch_dir_id, absolute_path, updated_at) "
    "VALUES (?, NULL, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)))"
)

# SQLite schema often uses INTEGER 0/1 for these; PostgreSQL uses native BOOLEAN.
_BOOL_COL_INT_ASSIGN = ("deleted", "has_docstring", "processing_paused")


def _adapt_sqlite_bool_int_assignments_for_postgres(sql: str) -> str:
    """Map ``col = 0`` / ``col = 1`` to BOOLEAN literals for known BOOLEAN columns."""
    s = sql
    for col in _BOOL_COL_INT_ASSIGN:
        s = re.sub(
            rf"\b{re.escape(col)}\s*=\s*0\b",
            f"{col} = FALSE",
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(
            rf"\b{re.escape(col)}\s*=\s*1\b",
            f"{col} = TRUE",
            s,
            flags=re.IGNORECASE,
        )
    return s


def _adapt_sqlite_dml_for_postgres(sql: str) -> str:
    """Replace SQLite-only datetime helpers in DML with PostgreSQL equivalents.

    Schema DDL is generated separately; application code often still uses
    ``julianday('now')`` (Julian day REAL timestamps, same convention as SQLite).

    ``INSERT OR REPLACE`` is SQLite-specific; map known statements to
    ``INSERT ... ON CONFLICT ... DO UPDATE`` where the schema has a matching
    UNIQUE constraint (see :mod:`code_analysis.core.indexing_worker_pkg.processing`).

    Integer ``0``/``1`` assignments to BOOLEAN columns (e.g. ``files.deleted``) are
    rewritten to ``FALSE``/``TRUE`` so portable SQLite-style SQL does not raise
    ``DatatypeMismatch`` on PostgreSQL.
    """
    s = sql.replace("julianday('now')", "(EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))")
    s = _adapt_sqlite_bool_int_assignments_for_postgres(s)
    norm = _norm_sql_one_line(s)
    if norm == _INDEXING_ERRORS_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO indexing_errors "
            "(project_id, file_path, error_type, error_message, created_at) "
            "VALUES (?, ?, ?, ?, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))) "
            "ON CONFLICT (project_id, file_path) DO UPDATE SET "
            "error_type = EXCLUDED.error_type, "
            "error_message = EXCLUDED.error_message, "
            "created_at = EXCLUDED.created_at"
        )
    if norm == _WATCH_DIRS_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO watch_dirs (id, name, updated_at) "
            "VALUES (?, ?, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))) "
            "ON CONFLICT (id) DO UPDATE SET "
            "name = EXCLUDED.name, "
            "updated_at = EXCLUDED.updated_at"
        )
    if norm == _WATCH_DIR_PATHS_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO watch_dir_paths (watch_dir_id, absolute_path, updated_at) "
            "VALUES (?, ?, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))) "
            "ON CONFLICT (watch_dir_id) DO UPDATE SET "
            "absolute_path = EXCLUDED.absolute_path, "
            "updated_at = EXCLUDED.updated_at"
        )
    if norm == _WATCH_DIR_PATHS_INSERT_OR_REPLACE_NULL_PATH_NORM:
        return (
            "INSERT INTO watch_dir_paths (watch_dir_id, absolute_path, updated_at) "
            "VALUES (?, NULL, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))) "
            "ON CONFLICT (watch_dir_id) DO UPDATE SET "
            "absolute_path = EXCLUDED.absolute_path, "
            "updated_at = EXCLUDED.updated_at"
        )
    return s


def _sqlite_qmarks_to_psycopg(
    sql: str, params: Optional[tuple]
) -> Tuple[str, Optional[tuple]]:
    if params is None:
        if "?" in sql:
            raise DriverOperationError("SQL contains ? but params is None")
        return sql, None
    n = sql.count("?")
    if n != len(params):
        raise DriverOperationError(
            f"Placeholder count mismatch: {n} ? vs {len(params)} params"
        )
    return ("%s".join(sql.split("?")), params)


def _returning_column_for_table(
    table_name: str, schema_tables: Dict[str, Any]
) -> Optional[str]:
    tdef = schema_tables.get(table_name)
    if not tdef:
        return "id"
    pks = [c["name"] for c in tdef["columns"] if c.get("primary_key")]
    if len(pks) == 1:
        return str(pks[0])
    return None


def _maybe_append_returning(stmt: str, schema_tables: Dict[str, Any]) -> str:
    s = stmt.strip()
    up = s.upper()
    if not up.startswith("INSERT"):
        return stmt
    if "RETURNING" in up:
        return stmt
    m = _INSERT_INTO_RE.match(s)
    if not m:
        return stmt
    table = m.group(1) or m.group(2) or m.group(3)
    rcol = _returning_column_for_table(table, schema_tables)
    if not rcol:
        return stmt
    base = s.rstrip().rstrip(";")
    return f"{base} RETURNING {rcol}"


def _rows_to_dicts(cursor: Any) -> List[Dict[str, Any]]:
    if cursor.description is None:
        return []
    cols = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def run_execute(
    conn: Any,
    sql: str,
    params: Optional[tuple],
    transaction_id: Optional[str],
    query_journal: Any,
    schema_tables: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute one or more statements; return last result (affected_rows, lastrowid, data)."""
    statements = split_batch_sql(sql)
    if not statements:
        return {"affected_rows": 0, "lastrowid": None, "data": None}

    bind_params: Optional[tuple] = None
    if params is not None:
        if isinstance(params, (list, tuple)):
            bind_params = tuple(params) if params else ()
        else:
            raise DriverOperationError(
                f"execute params must be tuple or list; got {type(params).__name__}"
            )

    last_result: Dict[str, Any] = {
        "affected_rows": 0,
        "lastrowid": None,
        "data": None,
    }
    try:
        for i, raw_stmt in enumerate(statements):
            use_params = bind_params if i == 0 else None
            if use_params is not None and use_params == ():
                use_params = None
            raw_adapted = _adapt_sqlite_dml_for_postgres(raw_stmt)
            stmt, conv_params = _sqlite_qmarks_to_psycopg(raw_adapted, use_params)
            stmt = _maybe_append_returning(stmt, schema_tables)

            cursor = conn.cursor()
            try:
                if conv_params:
                    cursor.execute(stmt, conv_params)
                else:
                    cursor.execute(stmt)

                st = raw_stmt.strip().upper()
                lastrowid: Any = None
                if st.startswith("INSERT") and "RETURNING" in stmt.upper():
                    row = cursor.fetchone()
                    if row is not None:
                        lastrowid = row[0]

                last_result = {
                    "affected_rows": cursor.rowcount if cursor.rowcount >= 0 else 0,
                    "lastrowid": lastrowid,
                }
                if st.startswith("SELECT") or st.startswith("WITH"):
                    last_result["data"] = _rows_to_dicts(cursor)
                else:
                    last_result["data"] = None

                if query_journal:
                    query_journal.write(
                        raw_stmt,
                        params=use_params,
                        transaction_id=transaction_id,
                        success=True,
                    )
            finally:
                cursor.close()

        if not transaction_id:
            try:
                conn.commit()
            except Exception as commit_err:
                msg = str(commit_err).lower()
                if "no transaction" in msg or "cannot commit" in msg:
                    logger.debug(
                        "Commit skipped (no active transaction): %s", commit_err
                    )
                else:
                    raise DriverOperationError(
                        f"Failed to commit: {commit_err}"
                    ) from commit_err
        return last_result
    except DriverOperationError:
        raise
    except Exception as e:
        if not transaction_id:
            try:
                conn.rollback()
            except Exception:
                pass
        raise DriverOperationError(f"Failed to execute SQL: {e}") from e


def run_execute_batch(
    conn: Any,
    operations: List[Tuple[str, Optional[tuple]]],
    transaction_id: Optional[str],
    query_journal: Any,
    schema_tables: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Batch execute with executemany grouping (same contract as SQLite driver)."""
    try:
        from psycopg import errors as pg_errors  # type: ignore[import-untyped]
    except ImportError:
        pg_errors = None  # type: ignore[assignment]

    if not operations:
        return []
    expanded = expand_operations(operations)
    if not expanded:
        return []
    runs = group_for_executemany(expanded)

    results: List[Dict[str, Any]] = []
    expanded_offset = 0
    try:
        for kind, payload in runs:
            if kind == "single":
                sql, params = payload
                exp_idx = expanded_offset
                expanded_offset += 1
                bind_params: Optional[tuple] = (
                    tuple(params) if params is not None else None
                )
                if bind_params is not None and bind_params == ():
                    bind_params = None
                stmt, bind_params = _sqlite_qmarks_to_psycopg(
                    _adapt_sqlite_dml_for_postgres(sql), bind_params
                )
                stmt = _maybe_append_returning(stmt, schema_tables)
                cursor = conn.cursor()
                try:
                    if bind_params:
                        cursor.execute(stmt, bind_params)
                    else:
                        cursor.execute(stmt)
                    lastrowid = None
                    if sql.strip().upper().startswith("INSERT"):
                        if "RETURNING" in stmt.upper():
                            row = cursor.fetchone()
                            if row is not None:
                                lastrowid = row[0]
                    res: Dict[str, Any] = {
                        "affected_rows": cursor.rowcount if cursor.rowcount >= 0 else 0,
                        "lastrowid": lastrowid,
                    }
                    if stmt.strip().upper().startswith("SELECT"):
                        res["data"] = _rows_to_dicts(cursor)
                    else:
                        res["data"] = None
                    results.append(res)
                    if query_journal:
                        query_journal.write(
                            sql,
                            params=bind_params,
                            transaction_id=transaction_id,
                            success=True,
                        )
                finally:
                    cursor.close()
            else:
                sql, params_list = payload
                if params_list is None:
                    params_list = []
                n = len(params_list)
                base_exp_idx = expanded_offset
                expanded_offset += n
                if n:
                    sql_pg, _ = _sqlite_qmarks_to_psycopg(
                        _adapt_sqlite_dml_for_postgres(sql), params_list[0]
                    )
                else:
                    sql_pg = _adapt_sqlite_dml_for_postgres(sql)
                cursor = conn.cursor()
                try:
                    try:
                        cursor.executemany(sql_pg, params_list)
                    except Exception as ie:
                        if pg_errors and isinstance(ie, pg_errors.IntegrityError):
                            raise DriverOperationError(
                                f"execute_batch failed: {ie}"
                            ) from ie
                        raise
                    lastrowid = None
                    results.extend(
                        [
                            {
                                "affected_rows": 1,
                                "lastrowid": lastrowid if i == n - 1 else None,
                                "data": None,
                            }
                            for i in range(n)
                        ]
                    )
                    if query_journal:
                        for p in params_list:
                            query_journal.write(
                                sql,
                                params=tuple(p),
                                transaction_id=transaction_id,
                                success=True,
                            )
                finally:
                    cursor.close()

        if not transaction_id:
            try:
                conn.commit()
            except Exception as commit_err:
                msg = str(commit_err).lower()
                if "no transaction" in msg or "cannot commit" in msg:
                    logger.debug(
                        "Commit skipped (no active transaction): %s", commit_err
                    )
                else:
                    raise DriverOperationError(
                        f"Failed to commit: {commit_err}"
                    ) from commit_err
        return results
    except DriverOperationError:
        raise
    except Exception as e:
        if not transaction_id:
            try:
                conn.rollback()
            except Exception:
                pass
        raise DriverOperationError(f"execute_batch failed: {e}") from e
