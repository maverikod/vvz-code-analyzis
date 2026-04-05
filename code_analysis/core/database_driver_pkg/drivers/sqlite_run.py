"""
Execute batch and execute SQL for SQLite driver (shared implementation).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..exceptions import DriverOperationError
from .sqlite_batch import expand_operations, group_for_executemany, split_batch_sql

logger = logging.getLogger(__name__)

_SQL_PREVIEW_MAX = 160
_PARAMS_PREVIEW_ELEM = 4
_PARAMS_PREVIEW_STR = 36


def _sql_preview_for_log(sql: str, max_len: int = _SQL_PREVIEW_MAX) -> str:
    s = " ".join(sql.strip().split())
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def _params_preview_compact(params: Optional[tuple]) -> str:
    """Short preview: length + a few elements; no huge blobs."""
    if params is None:
        return "None"
    n = len(params)
    if n == 0:
        return "()"

    def _one(x: Any) -> str:
        if isinstance(x, (int, bool)) or x is None:
            return repr(x)
        if isinstance(x, str):
            if len(x) <= _PARAMS_PREVIEW_STR:
                return repr(x)
            return repr(x[: _PARAMS_PREVIEW_STR - 3] + "...")
        s = repr(x)
        if len(s) > _PARAMS_PREVIEW_STR:
            return s[: _PARAMS_PREVIEW_STR - 3] + "..."
        return s

    shown = min(_PARAMS_PREVIEW_ELEM, n)
    parts = [_one(params[i]) for i in range(shown)]
    inner = ", ".join(parts)
    if n > shown:
        return f"len={n} ({inner}, ...)"
    return f"len={n} ({inner})"


def _probe_executemany_failing_row(
    cursor: Any, sql: str, params_list: Sequence[tuple[Any, ...]]
) -> Optional[int]:
    """Find 0-based row index of first IntegrityError when executing rows sequentially."""
    for row_idx, prow in enumerate(params_list):
        bind = tuple(prow) if prow is not None else ()
        try:
            cursor.execute(sql, bind)
        except sqlite3.IntegrityError:
            return row_idx
    return None


def _log_batch_integrity_error(
    transaction_id: Optional[str],
    *,
    run_idx: int,
    row_in_group: Optional[str],
    sql: str,
    params_preview: str,
    many_rows: Optional[int],
    err: Exception,
) -> None:
    tid = transaction_id if transaction_id else "none"
    rig = row_in_group if row_in_group is not None else "-"
    many_part = f" many_rows={many_rows}" if many_rows is not None else ""
    logger.error(
        "[BATCH_INTEGRITY] sqlite execute_batch IntegrityError tid=%s run_idx=%s "
        "row_in_group=%s%s sql_preview=%s params_preview=%s err=%s",
        tid,
        run_idx,
        rig,
        many_part,
        _sql_preview_for_log(sql),
        params_preview,
        err,
    )


def run_execute_batch(
    conn: Any,
    operations: List[Tuple[str, Optional[tuple]]],
    transaction_id: Optional[str],
    query_journal: Any,
) -> List[Dict[str, Any]]:
    """Execute multiple SQL statements with batch recognition and executemany."""
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
                cursor = conn.cursor()
                try:
                    try:
                        if bind_params:
                            cursor.execute(sql, bind_params)
                        else:
                            cursor.execute(sql)
                    except sqlite3.IntegrityError as ie:
                        _log_batch_integrity_error(
                            transaction_id,
                            run_idx=exp_idx,
                            row_in_group=None,
                            sql=sql,
                            params_preview=_params_preview_compact(bind_params),
                            many_rows=None,
                            err=ie,
                        )
                        raise DriverOperationError(
                            f"execute_batch failed: {ie}"
                        ) from ie
                    res: Dict[str, Any] = {
                        "affected_rows": cursor.rowcount,
                        "lastrowid": cursor.lastrowid,
                    }
                    if sql.strip().upper().startswith("SELECT"):
                        res["data"] = [dict(row) for row in cursor.fetchall()]
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
                cursor = conn.cursor()
                sp_name = f"sp_sqlite_batch_{base_exp_idx}"
                use_sp = False
                try:
                    try:
                        cursor.execute(f"SAVEPOINT {sp_name}")
                        use_sp = True
                    except Exception:
                        use_sp = False

                    try:
                        cursor.executemany(sql, params_list)
                    except sqlite3.IntegrityError as ie:
                        if use_sp:
                            try:
                                cursor.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                            except Exception:
                                use_sp = False
                        row_fail: Optional[int] = None
                        if use_sp:
                            row_fail = _probe_executemany_failing_row(
                                cursor, sql, params_list
                            )
                            try:
                                cursor.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                            except Exception:
                                pass
                        run_idx = (
                            base_exp_idx + row_fail
                            if row_fail is not None
                            else base_exp_idx
                        )
                        rig = str(row_fail) if row_fail is not None else "unknown"
                        if row_fail is not None and row_fail < len(params_list):
                            pv: Optional[tuple] = tuple(params_list[row_fail])
                        elif params_list:
                            pv = tuple(params_list[0])
                        else:
                            pv = None
                        _log_batch_integrity_error(
                            transaction_id,
                            run_idx=run_idx,
                            row_in_group=rig,
                            sql=sql,
                            params_preview=_params_preview_compact(pv),
                            many_rows=n if n else None,
                            err=ie,
                        )
                        if use_sp:
                            try:
                                cursor.execute(f"RELEASE SAVEPOINT {sp_name}")
                            except Exception:
                                pass
                        raise DriverOperationError(
                            f"execute_batch failed: {ie}"
                        ) from ie
                    if use_sp:
                        cursor.execute(f"RELEASE SAVEPOINT {sp_name}")
                    lastrowid = cursor.lastrowid
                    for i in range(n):
                        results.append(
                            {
                                "affected_rows": 1,
                                "lastrowid": lastrowid if i == n - 1 else None,
                                "data": None,
                            }
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


def run_execute(
    conn: Any,
    sql: str,
    params: Optional[tuple],
    transaction_id: Optional[str],
    query_journal: Any,
) -> Dict[str, Any]:
    """Execute SQL (one or more statements); return only last result."""
    statements = split_batch_sql(sql)
    if not statements:
        return {"affected_rows": 0, "lastrowid": None, "data": None}

    sql_preview = (sql.strip()[:60] + "…") if len(sql.strip()) > 60 else sql.strip()
    logger.info(
        "[CHAIN] sqlite driver execute sql_preview=%s tid=%s n_stmts=%s",
        sql_preview,
        (transaction_id[:8] + "…") if transaction_id else None,
        len(statements),
    )

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
        for i, stmt in enumerate(statements):
            use_params = bind_params if i == 0 else None
            if use_params is not None and use_params == ():
                use_params = None
            cursor = conn.cursor()
            try:
                if use_params:
                    cursor.execute(stmt, use_params)
                else:
                    cursor.execute(stmt)
                last_result = {
                    "affected_rows": cursor.rowcount,
                    "lastrowid": cursor.lastrowid,
                }
                if stmt.strip().upper().startswith("SELECT"):
                    last_result["data"] = [dict(row) for row in cursor.fetchall()]
                else:
                    last_result["data"] = None
                if query_journal:
                    query_journal.write(
                        stmt,
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
