"""
Entity cross-reference builder: resolve caller/callee from file+line and usages.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def resolve_caller(db: Any, file_id: int, line: int) -> Optional[Tuple[str, int]]:
    """
    Resolve (file_id, line) to the containing entity (method, function, or class).

    Prefer smallest containing span: method > function > class.
    Uses end_line when present; if end_line is NULL, treats entity as single-line (line only).

    Args:
        db: Legacy DB facade-like instance (_execute, _fetchall).
        file_id: File id.
        line: 1-based line number.

    Returns:
        (entity_type, entity_id) e.g. ('method', 42), or None if not found.
    """
    candidates: List[Tuple[str, int, int, int]] = []  # (type, id, start, end)

    # Methods for this file (via classes)
    rows = db._fetchall(
        """
        SELECT m.id, m.line, m.end_line
        FROM methods m
        JOIN classes c ON m.class_id = c.id
        WHERE c.file_id = ?
        """,
        (file_id,),
    )
    for row in rows:
        start = row["line"]
        end = row["end_line"] if row["end_line"] is not None else row["line"]
        if start <= line <= end:
            candidates.append(("method", row["id"], start, end))

    # Functions for this file
    rows = db._fetchall(
        "SELECT id, line, end_line FROM functions WHERE file_id = ?",
        (file_id,),
    )
    for row in rows:
        start = row["line"]
        end = row["end_line"] if row["end_line"] is not None else row["line"]
        if start <= line <= end:
            candidates.append(("function", row["id"], start, end))

    # Classes for this file
    rows = db._fetchall(
        "SELECT id, line, end_line FROM classes WHERE file_id = ?",
        (file_id,),
    )
    for row in rows:
        start = row["line"]
        end = row["end_line"] if row["end_line"] is not None else row["line"]
        if start <= line <= end:
            candidates.append(("class", row["id"], start, end))

    if not candidates:
        return None

    # Prefer smallest containing span; then order: method > function > class
    def key(item: Tuple[str, int, int, int]) -> Tuple[int, int, int]:
        """Return key."""
        entity_type, entity_id, start, end = item
        span = end - start
        type_rank = {"method": 0, "function": 1, "class": 2}[entity_type]
        return (span, type_rank, -start)

    candidates.sort(key=key)
    best = candidates[0]
    return (best[0], best[1])


def resolve_callee(
    db: Any,
    project_id: str,
    file_id: int,
    line: int,
    target_type: str,
    target_name: str,
    target_class: Optional[str] = None,
) -> Optional[Tuple[str, int]]:
    """
    Resolve (target_type, target_name, target_class) to (entity_type, entity_id) in project.

    Prefer same file_id when multiple matches.

    Args:
        db: Legacy DB facade-like instance.
        project_id: Project id for scoping.
        file_id: File id where reference occurs (for same-file preference).
        line: Line number (unused; for future use).
        target_type: 'class', 'function', or 'method'.
        target_name: Name of target.
        target_class: Class name for method (required when target_type is 'method').

    Returns:
        (entity_type, entity_id) or None if not found.
    """
    if target_type == "class":
        rows = db._fetchall(
            """
            SELECT c.id FROM classes c
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND c.name = ?
            ORDER BY (c.file_id = ?) DESC
            """,
            (project_id, target_name, file_id),
        )
        if rows:
            return ("class", rows[0]["id"])
        return None

    if target_type == "function":
        rows = db._fetchall(
            """
            SELECT fn.id FROM functions fn
            JOIN files f ON fn.file_id = f.id
            WHERE f.project_id = ? AND fn.name = ?
            ORDER BY (fn.file_id = ?) DESC
            """,
            (project_id, target_name, file_id),
        )
        if rows:
            return ("function", rows[0]["id"])
        return None

    if target_type == "method":
        if not target_class:
            return None
        rows = db._fetchall(
            """
            SELECT m.id FROM methods m
            JOIN classes c ON m.class_id = c.id
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND c.name = ? AND m.name = ?
            ORDER BY (f.id = ?) DESC
            """,
            (project_id, target_class, target_name, file_id),
        )
        if rows:
            return ("method", rows[0]["id"])
        return None

    return None


def _add_inheritance_cross_ref_for_file(db: Any, file_id: int, project_id: str) -> int:
    """
    Build entity_cross_ref inheritance edges from this file's ``classes.bases``.

    For each class defined in the file, resolves each base class name (project-scoped,
    same-file preferred, qualified names reduced to the last segment - same convention
    as ``get_class_hierarchy``) and inserts a ``ref_type='inherit'`` row with the child
    class as caller and the base class as callee. Unresolved bases (external/stdlib,
    or simply not found) are skipped - same convention as unresolved usage callees in
    :func:`build_entity_cross_ref_for_file`.

    Args:
        db: Legacy DB facade-like (add_entity_cross_ref semantics).
        file_id: File id.
        project_id: Project id for resolve_callee.

    Returns:
        Number of entity_cross_ref rows added.
    """
    rows = db._fetchall(
        "SELECT id, line, bases FROM classes WHERE file_id = ?",
        (file_id,),
    )
    added = 0
    for row in rows:
        class_id = row["id"]
        line = row["line"]
        bases_raw = row.get("bases")
        if not bases_raw:
            continue
        try:
            bases = json.loads(bases_raw) if isinstance(bases_raw, str) else bases_raw
        except (ValueError, TypeError):
            continue
        if not isinstance(bases, list):
            continue

        for base in bases:
            base_name = base.split(".")[-1] if isinstance(base, str) else str(base)
            if not base_name:
                continue
            callee = resolve_callee(db, project_id, file_id, line, "class", base_name)
            if callee is None:
                continue
            _, callee_id = callee
            try:
                db.add_entity_cross_ref(
                    caller_class_id=class_id,
                    caller_method_id=None,
                    caller_function_id=None,
                    callee_class_id=callee_id,
                    callee_method_id=None,
                    callee_function_id=None,
                    ref_type="inherit",
                    file_id=file_id,
                    line=line,
                )
                added += 1
            except Exception as e:
                logger.debug(
                    "Failed to add inheritance entity_cross_ref for %s at line %s: %s",
                    base_name,
                    line,
                    e,
                    exc_info=True,
                )
    return added


def build_entity_cross_ref_for_file(
    db: Any, file_id: int, project_id: str, source_code: str
) -> int:
    """
    Build entity_cross_ref rows for a file from its usages and class inheritance.

    Fetches usages for file_id, resolves caller and callee for each usage,
    and inserts into entity_cross_ref when both are resolved. Also derives
    inheritance edges from this file's classes.bases (see
    :func:`_add_inheritance_cross_ref_for_file`). On failure for a single
    usage/inheritance edge, logs and continues.

    Note: this only runs on (re-)index of the file - existing projects only get
    inheritance rows once their files are re-indexed (update_indexes / file change),
    not retroactively.

    Args:
        db: Legacy DB facade-like (add_entity_cross_ref, add_usage semantics).
        file_id: File id.
        project_id: Project id for resolve_callee.
        source_code: Unused; for future context.

    Returns:
        Number of entity_cross_ref rows added (usages + inheritance).
    """
    usages = db._fetchall(
        "SELECT line, usage_type, target_type, target_name, target_class FROM usages WHERE file_id = ?",
        (file_id,),
    )
    added = 0
    for row in usages:
        line = row["line"]
        usage_type = row["usage_type"]
        target_type = row["target_type"]
        target_name = row["target_name"]
        target_class = row.get("target_class")

        caller = resolve_caller(db, file_id, line)
        callee = resolve_callee(
            db, project_id, file_id, line, target_type, target_name, target_class
        )
        if caller is None or callee is None:
            continue

        caller_type, caller_id = caller
        callee_type, callee_id = callee

        caller_class_id = caller_method_id = caller_function_id = None
        if caller_type == "class":
            caller_class_id = caller_id
        elif caller_type == "method":
            caller_method_id = caller_id
        else:
            caller_function_id = caller_id

        callee_class_id = callee_method_id = callee_function_id = None
        if callee_type == "class":
            callee_class_id = callee_id
        elif callee_type == "method":
            callee_method_id = callee_id
        else:
            callee_function_id = callee_id

        try:
            db.add_entity_cross_ref(
                caller_class_id=caller_class_id,
                caller_method_id=caller_method_id,
                caller_function_id=caller_function_id,
                callee_class_id=callee_class_id,
                callee_method_id=callee_method_id,
                callee_function_id=callee_function_id,
                ref_type=usage_type,
                file_id=file_id,
                line=line,
            )
            added += 1
        except Exception as e:
            logger.debug(
                "Failed to add entity_cross_ref for %s at line %s: %s",
                target_name,
                line,
                e,
                exc_info=True,
            )

    added += _add_inheritance_cross_ref_for_file(db, file_id, project_id)
    return added
