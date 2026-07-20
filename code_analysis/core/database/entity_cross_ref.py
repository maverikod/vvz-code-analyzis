"""
Module entity_cross_ref - entity-to-entity references (dependencies and dependents).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Valid ref_type values (must match usage_type from usages)
REF_TYPES = ("call", "instantiation", "attribute", "inherit")
CALLER_TYPES = ("class", "method", "function")
CALLEE_TYPES = ("class", "method", "function")


def _fetchall(db: Any, sql: str, params: tuple) -> List[Dict[str, Any]]:
    """
    Run a SELECT via the portable ``execute()`` interface.

    Every function in this module used to call the private
    ``_fetchall``/``_execute``/``_commit``/``_lastrowid``/``_in_transaction``
    quartet, which only ``CodeDatabase`` implements. ``sync_file_to_db_atomic``
    (the live caller of the whole entity_cross_ref builder chain) passes a
    ``DatabaseClient``, which has neither those private methods NOR
    ``add_entity_cross_ref``/``delete_entity_cross_ref_for_file`` as bound
    methods - every call raised ``AttributeError`` there. Both classes DO
    implement the public ``execute(sql, params) -> {"data": [...], ...}``
    (``CodeDatabase.execute``'s own docstring: "work with both DatabaseClient
    (RPC) and CodeDatabase"); this module now uses only that shared surface.
    """
    result = db.execute(sql, params)
    data = result.get("data") if isinstance(result, dict) else None
    return list(data) if data else []


def add_entity_cross_ref(
    self,
    caller_class_id: Optional[int],
    caller_method_id: Optional[int],
    caller_function_id: Optional[int],
    callee_class_id: Optional[int],
    callee_method_id: Optional[int],
    callee_function_id: Optional[int],
    ref_type: str,
    file_id: Optional[int] = None,
    line: Optional[int] = None,
) -> int:
    """
    Insert one entity cross-reference row.

    Exactly one of caller_class_id, caller_method_id, caller_function_id must be non-None.
    Exactly one of callee_class_id, callee_method_id, callee_function_id must be non-None.

    Uses the portable ``self.execute(sql, params)`` (implemented by both
    ``CodeDatabase`` and ``DatabaseClient`` - see :func:`_fetchall`'s
    docstring), not the private ``_execute``/``_commit``/``_lastrowid``/
    ``_in_transaction`` quartet this function used until two rounds of live
    verification found it broken: first because an unconditional
    ``self._commit()`` ended the caller's enclosing transaction early on
    PostgreSQL (invisible on SQLite, whose test facade's ``_commit()`` is an
    always-no-op), then because ``sync_file_to_db_atomic`` (the actual live
    caller of the whole entity_cross_ref builder chain, via
    ``entity_cross_ref_builder.build_entity_cross_ref_for_file``) passes a
    ``DatabaseClient``, which implements neither those private methods nor
    this function as a bound method at all. ``self.execute(...)`` with no
    ``transaction_id`` auto-commits per statement on both layers when called
    standalone (no wrapping transaction) - exactly how this chain is invoked
    today - while still respecting an ambient ``CodeDatabase`` transaction
    transparently for any caller that has one (``CodeDatabase.execute()``
    delegates to ``_execute()``, which still consults ``_driver_transaction_id()``
    internally).

    Args:
        caller_class_id: Caller class id (or None)
        caller_method_id: Caller method id (or None)
        caller_function_id: Caller function id (or None)
        callee_class_id: Callee class id (or None)
        callee_method_id: Callee method id (or None)
        callee_function_id: Callee function id (or None)
        ref_type: 'call', 'instantiation', 'attribute', 'inherit'
        file_id: Optional file where reference occurs
        line: Optional line number

    Returns:
        Inserted row id.

    Raises:
        ValueError: If caller or callee triple is invalid.
    """
    caller_count = sum(
        x is not None for x in (caller_class_id, caller_method_id, caller_function_id)
    )
    callee_count = sum(
        x is not None for x in (callee_class_id, callee_method_id, callee_function_id)
    )
    if caller_count != 1:
        raise ValueError(
            "Exactly one of caller_class_id, caller_method_id, caller_function_id must be set"
        )
    if callee_count != 1:
        raise ValueError(
            "Exactly one of callee_class_id, callee_method_id, callee_function_id must be set"
        )
    if ref_type not in REF_TYPES:
        raise ValueError(f"ref_type must be one of {REF_TYPES!r}")

    result = self.execute(
        """
        INSERT INTO entity_cross_ref (
            caller_class_id, caller_method_id, caller_function_id,
            callee_class_id, callee_method_id, callee_function_id,
            ref_type, file_id, line
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            caller_class_id,
            caller_method_id,
            caller_function_id,
            callee_class_id,
            callee_method_id,
            callee_function_id,
            ref_type,
            file_id,
            line,
        ),
    )
    lastrowid = result.get("lastrowid") if isinstance(result, dict) else None
    assert lastrowid is not None
    return lastrowid


def get_dependencies_by_caller(
    self, caller_entity_type: str, caller_entity_id: int
) -> List[Dict[str, Any]]:
    """
    Get dependencies of an entity (what it calls/uses).

    Args:
        caller_entity_type: 'class', 'method', or 'function'
        caller_entity_id: Corresponding id

    Returns:
        List of dicts with callee_entity_type, callee_entity_id, ref_type, file_id, line.
    """
    if caller_entity_type not in CALLER_TYPES:
        raise ValueError(f"caller_entity_type must be one of {CALLER_TYPES!r}")

    if caller_entity_type == "class":
        col = "caller_class_id"
    elif caller_entity_type == "method":
        col = "caller_method_id"
    else:
        col = "caller_function_id"

    rows = _fetchall(
        self,
        f"""
        SELECT callee_class_id, callee_method_id, callee_function_id,
               ref_type, file_id, line
        FROM entity_cross_ref
        WHERE {col} = ?
        """,
        (caller_entity_id,),
    )

    result: List[Dict[str, Any]] = []
    for row in rows:
        if row["callee_class_id"] is not None:
            callee_type, callee_id = "class", row["callee_class_id"]
        elif row["callee_method_id"] is not None:
            callee_type, callee_id = "method", row["callee_method_id"]
        else:
            callee_type, callee_id = "function", row["callee_function_id"]
        result.append(
            {
                "callee_entity_type": callee_type,
                "callee_entity_id": callee_id,
                "ref_type": row["ref_type"],
                "file_id": row["file_id"],
                "line": row["line"],
            }
        )
    return result


def get_dependents_by_callee(
    self, callee_entity_type: str, callee_entity_id: int
) -> List[Dict[str, Any]]:
    """
    Get dependents of an entity (what calls/uses it).

    Args:
        callee_entity_type: 'class', 'method', or 'function'
        callee_entity_id: Corresponding id

    Returns:
        List of dicts with caller_entity_type, caller_entity_id, ref_type, file_id, line.
    """
    if callee_entity_type not in CALLEE_TYPES:
        raise ValueError(f"callee_entity_type must be one of {CALLEE_TYPES!r}")

    if callee_entity_type == "class":
        col = "callee_class_id"
    elif callee_entity_type == "method":
        col = "callee_method_id"
    else:
        col = "callee_function_id"

    rows = _fetchall(
        self,
        f"""
        SELECT caller_class_id, caller_method_id, caller_function_id,
               ref_type, file_id, line
        FROM entity_cross_ref
        WHERE {col} = ?
        """,
        (callee_entity_id,),
    )

    result: List[Dict[str, Any]] = []
    for row in rows:
        if row["caller_class_id"] is not None:
            caller_type, caller_id = "class", row["caller_class_id"]
        elif row["caller_method_id"] is not None:
            caller_type, caller_id = "method", row["caller_method_id"]
        else:
            caller_type, caller_id = "function", row["caller_function_id"]
        result.append(
            {
                "caller_entity_type": caller_type,
                "caller_entity_id": caller_id,
                "ref_type": row["ref_type"],
                "file_id": row["file_id"],
                "line": row["line"],
            }
        )
    return result


def delete_entity_cross_ref_for_file(self, file_id: Any) -> None:
    """
    Delete all entity_cross_ref rows for a file and its entities.

    Removes rows where:
    - file_id = file_id (reference location), or
    - caller/callee class/method/function belongs to this file.

    Uses the portable ``self.execute(sql, params)`` throughout (see
    :func:`_fetchall`'s docstring) - same rationale as ``add_entity_cross_ref``:
    ``sync_file_to_db_atomic`` (the live caller, via
    ``entity_cross_ref_builder.build_entity_cross_ref_for_file``) passes a
    ``DatabaseClient``, which has neither the private ``_fetchall``/
    ``_execute``/``_commit``/``_in_transaction`` this function used before, nor
    this function itself as a bound method.

    Args:
        file_id: File id to clear cross-refs for (UUID string post-migration;
            ``Any`` here since callers pass the real runtime id, not the legacy
            pre-migration ``int`` this module's other signatures still declare).
    """
    # Get all class_ids for this file
    class_rows = _fetchall(self, "SELECT id FROM classes WHERE file_id = ?", (file_id,))
    class_ids = [r["id"] for r in class_rows]

    # Get all method_ids for those classes
    method_ids: List[int] = []
    if class_ids:
        placeholders = ",".join("?" * len(class_ids))
        method_rows = _fetchall(
            self,
            f"SELECT id FROM methods WHERE class_id IN ({placeholders})",
            tuple(class_ids),
        )
        method_ids = [r["id"] for r in method_rows]

    # Get all function_ids for this file
    func_rows = _fetchall(
        self, "SELECT id FROM functions WHERE file_id = ?", (file_id,)
    )
    function_ids = [r["id"] for r in func_rows]

    # Build DELETE: WHERE file_id = ? OR caller/callee in (ids)
    conditions = ["file_id = ?"]
    params: List[Any] = [file_id]

    if class_ids:
        placeholders = ",".join("?" * len(class_ids))
        conditions.append(f"caller_class_id IN ({placeholders})")
        params.extend(class_ids)
        conditions.append(f"callee_class_id IN ({placeholders})")
        params.extend(class_ids)
    if method_ids:
        placeholders = ",".join("?" * len(method_ids))
        conditions.append(f"caller_method_id IN ({placeholders})")
        params.extend(method_ids)
        conditions.append(f"callee_method_id IN ({placeholders})")
        params.extend(method_ids)
    if function_ids:
        placeholders = ",".join("?" * len(function_ids))
        conditions.append(f"caller_function_id IN ({placeholders})")
        params.extend(function_ids)
        conditions.append(f"callee_function_id IN ({placeholders})")
        params.extend(function_ids)

    where_clause = " OR ".join(conditions)
    self.execute(f"DELETE FROM entity_cross_ref WHERE {where_clause}", tuple(params))
