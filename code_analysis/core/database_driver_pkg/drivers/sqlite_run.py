"""
Execute batch and execute SQL for SQLite driver (shared implementation).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..exceptions import DriverOperationError
from .sqlite_batch import expand_operations, group_for_executemany, split_batch_sql

logger = logging.getLogger(__name__)


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
    try:
        for kind, payload in runs:
            if kind == "single":
                sql, params = payload
                bind_params: Optional[tuple] = (
                    tuple(params) if params is not None else None
                )
                if bind_params is not None and bind_params == ():
                    bind_params = None
                cursor = conn.cursor()
                try:
                    if bind_params:
                        cursor.execute(sql, bind_params)
                    else:
                        cursor.execute(sql)
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
                cursor = conn.cursor()
                if params_list is None:
                    params_list = []
                try:
                    cursor.executemany(sql, params_list)
                    n = len(params_list)
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
