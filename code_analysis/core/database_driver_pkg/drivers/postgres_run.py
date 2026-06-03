"""
Execute SQL for PostgreSQL driver (? placeholders → %%s, INSERT RETURNING for lastrowid).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any, Dict, List, NoReturn, Optional, Tuple

from code_analysis.core.database.code_chunk_sql import (
    code_chunk_upsert_norm_for_postgres_adapter,
)
from code_analysis.core.database.watch_dir_sql import (
    watch_dir_paths_upsert_norm_for_postgres_adapter,
    watch_dir_paths_upsert_null_norm_for_postgres_adapter,
    watch_dirs_upsert_norm_for_postgres_adapter,
)

from ..exceptions import (
    DatabaseErrorInfo,
    DriverOperationError,
    TransientDatabaseError,
)
from .sqlite_batch import expand_operations, group_for_executemany, split_batch_sql

logger = logging.getLogger(__name__)


def classify_postgres_error(
    exc: BaseException, *, for_commit: bool = False
) -> DatabaseErrorInfo:
    """
    Classify a PostgreSQL error using SQLSTATE and message. No string parsing
    of driver-specific 'deadlock detected' phrasing (SQLSTATE 40P01 is used).
    """
    message = str(exc) if str(exc) else type(exc).__name__
    msg_lower = message.lower()
    sqlstate: str | None = getattr(exc, "sqlstate", None)
    if sqlstate is None:
        diag = getattr(exc, "diag", None)
        if diag is not None:
            sqlstate = getattr(diag, "sqlstate", None)
    if sqlstate is None:
        return DatabaseErrorInfo(
            sqlstate=None,
            error_kind="non_postgres",
            retryable=False,
            message=message,
            commit_outcome_unknown=False,
        )
    if sqlstate == "40P01":
        base = DatabaseErrorInfo(
            sqlstate=sqlstate,
            error_kind="deadlock",
            retryable=True,
            message=message,
            commit_outcome_unknown=False,
        )
    elif sqlstate == "40001":
        base = DatabaseErrorInfo(
            sqlstate=sqlstate,
            error_kind="serialization_failure",
            retryable=True,
            message=message,
            commit_outcome_unknown=False,
        )
    elif sqlstate == "55P03":
        base = DatabaseErrorInfo(
            sqlstate=sqlstate,
            error_kind="lock_not_available",
            retryable=True,
            message=message,
            commit_outcome_unknown=False,
        )
    elif sqlstate == "57014":
        is_timeout = (
            "lock timeout" in msg_lower
            or "statement timeout" in msg_lower
            or "canceling statement due to statement timeout" in msg_lower
        )
        base = DatabaseErrorInfo(
            sqlstate=sqlstate,
            error_kind="query_canceled",
            retryable=is_timeout,
            message=message,
            commit_outcome_unknown=False,
        )
    else:
        base = DatabaseErrorInfo(
            sqlstate=sqlstate,
            error_kind="postgres_error",
            retryable=False,
            message=message,
            commit_outcome_unknown=False,
        )

    if (
        for_commit
        and base.sqlstate
        and (
            base.sqlstate.startswith("08")
            or base.sqlstate in ("57P01", "57P02", "57P03")
        )
    ):
        return replace(
            base,
            commit_outcome_unknown=True,
            retryable=False,
        )
    return base


def _raise_classified(
    e: BaseException, *, for_commit: bool, message_prefix: str
) -> NoReturn:
    info = classify_postgres_error(e, for_commit=for_commit)
    if info.retryable and not info.commit_outcome_unknown:
        raise TransientDatabaseError(
            f"{message_prefix}{e}",
            sqlstate=info.sqlstate,
            error_kind=info.error_kind,
            retryable=True,
            original_error=e,
            commit_outcome_unknown=info.commit_outcome_unknown,
        ) from e
    raise DriverOperationError(f"{message_prefix}{e}") from e


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
    watch_dirs_upsert_norm_for_postgres_adapter()
)

_WATCH_DIR_PATHS_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(
    watch_dir_paths_upsert_norm_for_postgres_adapter()
)

_WATCH_DIR_PATHS_INSERT_OR_REPLACE_NULL_PATH_NORM = _norm_sql_one_line(
    watch_dir_paths_upsert_null_norm_for_postgres_adapter()
)

# Portable ``code_chunks`` upsert: lookup norm from ``code_chunk_sql`` only
# (single source). Adapted INSERT … ON CONFLICT below must stay column-aligned
# with ``CODE_CHUNK_UPSERT_SQL`` / ``CODE_CHUNK_UPSERT_PARAM_ORDER`` in that module.
_CODE_CHUNKS_INSERT_OR_REPLACE_NORM = code_chunk_upsert_norm_for_postgres_adapter()
# Entity INSERT OR REPLACE norms (classes / methods / functions)
_CLASSES_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(
    "INSERT OR REPLACE INTO classes "
    "(file_id, name, line, end_line, cst_node_id, docstring, bases) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

_METHODS_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(
    "INSERT OR REPLACE INTO methods "
    "(class_id, name, line, end_line, cst_node_id, args, docstring) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

_FUNCTIONS_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(
    "INSERT OR REPLACE INTO functions "
    "(file_id, name, line, end_line, cst_node_id, args, docstring) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

_FILES_INSERT_OR_REPLACE_NORM = _norm_sql_one_line(
    "INSERT OR REPLACE INTO files "
    "(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "
    "VALUES (?, ?, ?, ?, ?, ?, 0, ?)"
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
            "INSERT INTO watch_dirs (server_instance_id, id, name, updated_at) "
            "VALUES (?, ?, ?, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))) "
            "ON CONFLICT (server_instance_id, id) DO UPDATE SET "
            "name = EXCLUDED.name, "
            "updated_at = EXCLUDED.updated_at"
        )
    if norm == _WATCH_DIR_PATHS_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO watch_dir_paths "
            "(server_instance_id, watch_dir_id, absolute_path, updated_at) "
            "VALUES (?, ?, ?, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))) "
            "ON CONFLICT (server_instance_id, watch_dir_id) DO UPDATE SET "
            "absolute_path = EXCLUDED.absolute_path, "
            "updated_at = EXCLUDED.updated_at"
        )
    if norm == _WATCH_DIR_PATHS_INSERT_OR_REPLACE_NULL_PATH_NORM:
        return (
            "INSERT INTO watch_dir_paths "
            "(server_instance_id, watch_dir_id, absolute_path, updated_at) "
            "VALUES (?, ?, NULL, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))) "
            "ON CONFLICT (server_instance_id, watch_dir_id) DO UPDATE SET "
            "absolute_path = EXCLUDED.absolute_path, "
            "updated_at = EXCLUDED.updated_at"
        )
    if norm == _CODE_CHUNKS_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO code_chunks "
            "( id, file_id, project_id, chunk_uuid, chunk_type, chunk_text, "
            "chunk_ordinal, vector_id, embedding_model, bm25_score, "
            "embedding_vector, token_count, class_id, function_id, method_id, "
            "line, ast_node_type, source_type, binding_level, "
            "updated_at ) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "(EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))) "
            "ON CONFLICT (chunk_uuid) DO UPDATE SET "
            "id = EXCLUDED.id, "
            "file_id = EXCLUDED.file_id, "
            "project_id = EXCLUDED.project_id, "
            "chunk_type = EXCLUDED.chunk_type, "
            "chunk_text = EXCLUDED.chunk_text, "
            "chunk_ordinal = EXCLUDED.chunk_ordinal, "
            "vector_id = EXCLUDED.vector_id, "
            "embedding_model = EXCLUDED.embedding_model, "
            "bm25_score = EXCLUDED.bm25_score, "
            "embedding_vector = EXCLUDED.embedding_vector, "
            "token_count = EXCLUDED.token_count, "
            "class_id = EXCLUDED.class_id, "
            "function_id = EXCLUDED.function_id, "
            "method_id = EXCLUDED.method_id, "
            "line = EXCLUDED.line, "
            "ast_node_type = EXCLUDED.ast_node_type, "
            "source_type = EXCLUDED.source_type, "
            "binding_level = EXCLUDED.binding_level, "
            "updated_at = EXCLUDED.updated_at"
        )
    if norm == _CLASSES_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO classes "
            "(file_id, name, line, end_line, cst_node_id, docstring, bases) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (file_id, name, line) DO UPDATE SET "
            "end_line = EXCLUDED.end_line, "
            "cst_node_id = EXCLUDED.cst_node_id, "
            "docstring = EXCLUDED.docstring, "
            "bases = EXCLUDED.bases"
        )
    if norm == _METHODS_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO methods "
            "(class_id, name, line, end_line, cst_node_id, args, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (class_id, name, line) DO UPDATE SET "
            "end_line = EXCLUDED.end_line, "
            "cst_node_id = EXCLUDED.cst_node_id, "
            "args = EXCLUDED.args, "
            "docstring = EXCLUDED.docstring"
        )
    if norm == _FUNCTIONS_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO functions "
            "(file_id, name, line, end_line, cst_node_id, args, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (file_id, name, line) DO UPDATE SET "
            "end_line = EXCLUDED.end_line, "
            "cst_node_id = EXCLUDED.cst_node_id, "
            "args = EXCLUDED.args, "
            "docstring = EXCLUDED.docstring"
        )
    if norm == _FILES_INSERT_OR_REPLACE_NORM:
        return (
            "INSERT INTO files "
            "(project_id, path, relative_path, lines, last_modified, has_docstring, deleted, watch_dir_id) "
            "VALUES (?, ?, ?, ?, ?, ?, FALSE, ?) "
            "ON CONFLICT (project_id, path) DO UPDATE SET "
            "path = EXCLUDED.path, "
            "relative_path = EXCLUDED.relative_path, "
            "lines = EXCLUDED.lines, "
            "last_modified = EXCLUDED.last_modified, "
            "has_docstring = EXCLUDED.has_docstring, "
            "deleted = EXCLUDED.deleted, "
            "watch_dir_id = EXCLUDED.watch_dir_id"
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
    """PK column for RETURNING on INSERT; ``None`` if table is unknown (no guessed ``id``).

    Migration and ad-hoc tables (e.g. ``uuid_migration_*``) are often absent from ``schema_tables``;
    appending ``RETURNING id`` would fail when the real PK is ``old_id`` or there is no ``id``.
    """
    tdef = schema_tables.get(table_name)
    if not tdef:
        return None
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
                    _raise_classified(
                        commit_err, for_commit=True, message_prefix="Failed to commit: "
                    )
        return last_result
    except TransientDatabaseError:
        raise
    except DriverOperationError:
        raise
    except Exception as e:
        if not transaction_id:
            try:
                conn.rollback()
            except Exception:
                pass
        _raise_classified(e, for_commit=False, message_prefix="Failed to execute SQL: ")


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
                    except TransientDatabaseError:
                        raise
                    except Exception as ie:
                        if pg_errors and isinstance(ie, pg_errors.IntegrityError):
                            raise DriverOperationError(
                                f"execute_batch failed: {ie}"
                            ) from ie
                        _raise_classified(
                            ie,
                            for_commit=False,
                            message_prefix="execute_batch failed: ",
                        )
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
                    _raise_classified(
                        commit_err, for_commit=True, message_prefix="Failed to commit: "
                    )
        return results
    except TransientDatabaseError:
        raise
    except DriverOperationError:
        raise
    except Exception as e:
        if not transaction_id:
            try:
                conn.rollback()
            except Exception:
                pass
        _raise_classified(e, for_commit=False, message_prefix="execute_batch failed: ")
