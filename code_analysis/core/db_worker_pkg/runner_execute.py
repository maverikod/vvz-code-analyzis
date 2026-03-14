"""
Database worker: execute DB operations (execute, fetchone, fetchall, transactions).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

_transaction_connections: Dict[str, Any] = {}


def execute_operation(
    operation: str,
    db_path: str,
    sql: Optional[str] = None,
    params: Optional[tuple] = None,
    table_name: Optional[str] = None,
    transaction_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute database operation. Returns dict with success, result, error."""
    db_path_obj = Path(db_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    conn: Optional[sqlite3.Connection] = None
    use_transaction_connection = False

    if operation == "begin_transaction":
        if not transaction_id:
            raise ValueError("transaction_id is required for begin_transaction")
        if transaction_id in _transaction_connections:
            raise ValueError(f"Transaction {transaction_id} already exists")
        conn = sqlite3.connect(str(db_path_obj), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            pass
        conn.execute("BEGIN TRANSACTION")
        _transaction_connections[transaction_id] = conn
        use_transaction_connection = True
        return {"success": True, "result": {"success": True}, "error": None}

    if transaction_id:
        if transaction_id in _transaction_connections:
            conn = _transaction_connections[transaction_id]
            use_transaction_connection = True
        else:
            raise ValueError(
                f"Transaction {transaction_id} not found. Call begin_transaction first."
            )
    else:
        conn = sqlite3.connect(str(db_path_obj), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            pass

    try:
        result: Union[Dict[str, Any], List[Dict[str, Any]], None] = None

        if operation == "commit_transaction":
            if transaction_id and transaction_id in _transaction_connections:
                conn = _transaction_connections[transaction_id]
                conn.commit()
                conn.close()
                del _transaction_connections[transaction_id]
                result = {"success": True}
            else:
                raise ValueError(f"Transaction {transaction_id} not found")

        elif operation == "rollback_transaction":
            if transaction_id and transaction_id in _transaction_connections:
                conn = _transaction_connections[transaction_id]
                conn.rollback()
                conn.close()
                del _transaction_connections[transaction_id]
                result = {"success": True}
            else:
                raise ValueError(f"Transaction {transaction_id} not found")

        elif operation == "execute":
            if not sql:
                raise ValueError("sql parameter is required for execute operation")
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            if not use_transaction_connection:
                conn.commit()
            result = {
                "affected_rows": cursor.rowcount,
                "lastrowid": cursor.lastrowid,
            }
            if sql.strip().upper().startswith("SELECT"):
                rows = cursor.fetchall()
                result["data"] = [dict(zip(row.keys(), row)) for row in rows]

        elif operation == "fetchone":
            if not sql:
                raise ValueError("sql parameter is required for fetchone operation")
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            row = cursor.fetchone()
            result = dict(zip(row.keys(), row)) if row else None

        elif operation == "fetchall":
            if not sql:
                raise ValueError("sql parameter is required for fetchall operation")
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            rows = cursor.fetchall()
            result = [dict(zip(row.keys(), row)) for row in rows]

        elif operation == "commit":
            conn.commit()
            result = None

        elif operation == "rollback":
            conn.rollback()
            result = None

        elif operation == "lastrowid":
            result = None

        elif operation == "get_table_info":
            if not table_name:
                raise ValueError(
                    "table_name parameter is required for get_table_info operation"
                )
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            rows = cursor.fetchall()
            columns = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
            result = [dict(zip(columns, row)) for row in rows]

        else:
            raise ValueError(f"Unknown operation: {operation}")

        return {"success": True, "result": result, "error": None}

    except Exception as e:
        logger.error(
            f"Database operation '{operation}' failed: {e}",
            exc_info=True,
            extra={
                "operation": operation,
                "db_path": db_path,
                "sql": sql[:200] if sql else None,
            },
        )
        return {
            "success": False,
            "result": None,
            "error": {
                "type": type(e).__name__,
                "message": str(e),
                "sql": sql[:200] if sql else None,
            },
        }

    finally:
        if not use_transaction_connection and conn:
            conn.close()
