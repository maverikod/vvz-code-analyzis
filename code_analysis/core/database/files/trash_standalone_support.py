"""
Driver-backed file data clearing for trash operations (RPC driver process).

Duplicates :func:`~code_analysis.core.database.files.crud.clear_file_data` /
``_clear_file_vectors`` logic using :class:`~code_analysis.core.database_driver_pkg.drivers.base.BaseDatabaseDriver`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .trash_codedatabase_adapter import TrashSqlDriver

logger = logging.getLogger(__name__)


def driver_fetchone(
    driver: TrashSqlDriver,
    sql: str,
    params: Optional[tuple] = None,
) -> Optional[Dict[str, Any]]:
    """SELECT one row via ``driver.execute`` (backend-agnostic)."""
    res = driver.execute(sql, params, None)
    if not isinstance(res, dict):
        return None
    rows = res.get("data") or []
    return rows[0] if rows else None


def driver_fetchall(
    driver: TrashSqlDriver,
    sql: str,
    params: Optional[tuple] = None,
) -> List[Dict[str, Any]]:
    """SELECT many rows via ``driver.execute``."""
    res = driver.execute(sql, params, None)
    if not isinstance(res, dict):
        return []
    data = res.get("data") or []
    return list(data)


def driver_execute_write(
    driver: TrashSqlDriver,
    sql: str,
    params: Optional[tuple] = None,
) -> None:
    """Execute DML/DDL via ``driver.execute`` (commits per driver contract)."""
    driver.execute(sql, params, None)


def clear_file_vectors_via_driver(driver: TrashSqlDriver, file_id: str) -> None:
    """Mirror :func:`~code_analysis.core.database.files.crud._clear_file_vectors`."""
    class_ids = [
        row["id"]
        for row in driver_fetchall(
            driver, "SELECT id FROM classes WHERE file_id = ?", (file_id,)
        )
    ]
    function_ids = [
        row["id"]
        for row in driver_fetchall(
            driver, "SELECT id FROM functions WHERE file_id = ?", (file_id,)
        )
    ]
    method_ids = [
        row["id"]
        for row in driver_fetchall(
            driver,
            "SELECT m.id FROM methods m JOIN classes c ON m.class_id = c.id "
            "WHERE c.file_id = ?",
            (file_id,),
        )
    ]
    entity_ids = class_ids + function_ids + method_ids
    driver_execute_write(
        driver, "DELETE FROM code_chunks WHERE file_id = ?", (file_id,)
    )
    driver_execute_write(
        driver,
        "DELETE FROM vector_index WHERE entity_type = 'file' AND entity_id = ?",
        (file_id,),
    )
    if entity_ids:
        placeholders = ",".join("?" * len(entity_ids))
        driver_execute_write(
            driver,
            "DELETE FROM vector_index WHERE entity_type IN "
            "('class', 'function', 'method') AND entity_id IN (" + placeholders + ")",
            tuple(entity_ids),
        )


def clear_file_data_via_driver(driver: TrashSqlDriver, file_id: str) -> None:
    """Mirror :meth:`~code_analysis.core.database.files.crud.clear_file_data` via driver."""
    clear_file_vectors_via_driver(driver, file_id)

    class_rows = driver_fetchall(
        driver, "SELECT id FROM classes WHERE file_id = ?", (file_id,)
    )
    class_ids = [row["id"] for row in class_rows]

    method_ids: List[Any] = []
    if class_ids:
        ph = ",".join("?" * len(class_ids))
        method_rows = driver_fetchall(
            driver,
            f"SELECT id FROM methods WHERE class_id IN ({ph})",
            tuple(class_ids),
        )
        method_ids = [r["id"] for r in method_rows]

    func_rows = driver_fetchall(
        driver, "SELECT id FROM functions WHERE file_id = ?", (file_id,)
    )
    function_ids = [r["id"] for r in func_rows]

    conditions = ["file_id = ?"]
    params_ecr: List[Any] = [file_id]
    if class_ids:
        ph = ",".join("?" * len(class_ids))
        conditions.append(f"caller_class_id IN ({ph})")
        params_ecr.extend(class_ids)
        conditions.append(f"callee_class_id IN ({ph})")
        params_ecr.extend(class_ids)
    if method_ids:
        ph = ",".join("?" * len(method_ids))
        conditions.append(f"caller_method_id IN ({ph})")
        params_ecr.extend(method_ids)
        conditions.append(f"callee_method_id IN ({ph})")
        params_ecr.extend(method_ids)
    if function_ids:
        ph = ",".join("?" * len(function_ids))
        conditions.append(f"caller_function_id IN ({ph})")
        params_ecr.extend(function_ids)
        conditions.append(f"callee_function_id IN ({ph})")
        params_ecr.extend(function_ids)
    where_clause = " OR ".join(conditions)
    ops: List[Tuple[str, Optional[tuple]]] = [
        (f"DELETE FROM entity_cross_ref WHERE {where_clause}", tuple(params_ecr))
    ]

    if class_ids:
        ph = ",".join("?" * len(class_ids))
        ops.append((f"DELETE FROM methods WHERE class_id IN ({ph})", tuple(class_ids)))

    ops.extend(
        [
            ("DELETE FROM classes WHERE file_id = ?", (file_id,)),
            ("DELETE FROM functions WHERE file_id = ?", (file_id,)),
            ("DELETE FROM imports WHERE file_id = ?", (file_id,)),
            ("DELETE FROM issues WHERE file_id = ?", (file_id,)),
            ("DELETE FROM usages WHERE file_id = ?", (file_id,)),
            ("DELETE FROM code_content WHERE file_id = ?", (file_id,)),
            ("DELETE FROM ast_trees WHERE file_id = ?", (file_id,)),
            ("DELETE FROM cst_trees WHERE file_id = ?", (file_id,)),
        ]
    )
    driver.execute_batch(ops, transaction_id=None)
