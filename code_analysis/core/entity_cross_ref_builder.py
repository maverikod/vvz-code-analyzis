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


def _base_names_from_bases_raw(bases_raw: Any) -> Optional[List[str]]:
    """Parse a ``classes.bases`` value into simple (last-segment) base names.

    Returns None when ``bases_raw`` is empty/unparseable/not a list (caller skips).
    """
    if not bases_raw:
        return None
    try:
        bases = json.loads(bases_raw) if isinstance(bases_raw, str) else bases_raw
    except (ValueError, TypeError):
        return None
    if not isinstance(bases, list):
        return None
    names = []
    for base in bases:
        name = base.split(".")[-1] if isinstance(base, str) else str(base)
        if name:
            names.append(name)
    return names


def _resolve_unique_base_class_id(
    db: Any, project_id: str, base_name: str
) -> Optional[Any]:
    """
    Resolve a base class name to a class id, project-wide, ONLY when unambiguous.

    Unlike :func:`resolve_callee` (which breaks ties by preferring a same-file
    match - fine for usages, but risks silently binding an inheritance edge to
    the wrong same-named class when the real base lives in another file and an
    unrelated class happens to share its name in the child's own file), this
    resolves the base class by name across the whole project and returns a hit
    ONLY when exactly one class with that name exists in the project. Zero or
    more than one match -> unresolved (None), same "skip, do not guess"
    convention as other unresolved callees in this module.

    Args:
        db: Legacy DB facade-like instance.
        project_id: Project id for scoping.
        base_name: Simple (unqualified) base class name.

    Returns:
        The unique class id, or None if zero or ambiguous (>1) matches.
    """
    rows = db._fetchall(
        """
        SELECT c.id FROM classes c
        JOIN files f ON c.file_id = f.id
        WHERE f.project_id = ? AND c.name = ?
        """,
        (project_id, base_name),
    )
    if len(rows) == 1:
        return rows[0]["id"]
    return None


def _inherit_edge_exists(db: Any, caller_class_id: Any, callee_class_id: Any) -> bool:
    """True if a ``ref_type='inherit'`` entity_cross_ref row already links these classes."""
    rows = db._fetchall(
        "SELECT 1 FROM entity_cross_ref "
        "WHERE caller_class_id = ? AND callee_class_id = ? AND ref_type = 'inherit'",
        (caller_class_id, callee_class_id),
    )
    return bool(rows)


def _backfill_children_inheritance_for_class(
    db: Any, project_id: str, parent_class_id: Any, parent_name: str
) -> int:
    """
    Retroactively add inherit edges FROM already-indexed children TO this class.

    ``update_indexes`` processes a project's files in a fixed (sorted) order that
    has no notion of base-before-derived; when a child's file is (re)indexed
    before its base class exists in the DB, the forward resolution in
    :func:`_add_inheritance_cross_ref_for_file` finds nothing for that base name
    and skips the edge - and nothing else ever revisits that child once the base
    class is indexed later in the same run. This closes that gap: every time a
    class is (re)indexed, scan the project for OTHER classes whose ``bases``
    reference this class's name and add the missing edge for each, regardless
    of which file was processed first. Idempotent via :func:`_inherit_edge_exists`
    so re-running (e.g. the base class file touched again later) never duplicates
    an edge already present.

    Args:
        db: Legacy DB facade-like (add_entity_cross_ref semantics).
        project_id: Project id for scoping.
        parent_class_id: Id of the class that may be a base of others.
        parent_name: Simple (unqualified) name of that class.

    Returns:
        Number of entity_cross_ref rows added.
    """
    rows = db._fetchall(
        """
        SELECT c.id, c.file_id, c.line, c.bases FROM classes c
        JOIN files f ON c.file_id = f.id
        WHERE f.project_id = ? AND c.id != ?
        """,
        (project_id, parent_class_id),
    )
    added = 0
    for row in rows:
        base_names = _base_names_from_bases_raw(row.get("bases"))
        if not base_names or parent_name not in base_names:
            continue
        child_id = row["id"]
        if _inherit_edge_exists(db, child_id, parent_class_id):
            continue
        try:
            db.add_entity_cross_ref(
                caller_class_id=child_id,
                caller_method_id=None,
                caller_function_id=None,
                callee_class_id=parent_class_id,
                callee_method_id=None,
                callee_function_id=None,
                ref_type="inherit",
                file_id=row.get("file_id"),
                line=row.get("line"),
            )
            added += 1
        except Exception as e:
            logger.debug(
                "Failed to backfill inheritance entity_cross_ref child=%s parent=%s: %s",
                child_id,
                parent_class_id,
                e,
                exc_info=True,
            )
    return added


def _add_inheritance_cross_ref_for_file(db: Any, file_id: int, project_id: str) -> int:
    """
    Build entity_cross_ref inheritance edges to/from this file's classes.

    For each class defined in the file:
    - Forward: resolves each base name in ``classes.bases`` (qualified names
      reduced to the last segment, same convention as ``get_class_hierarchy``)
      via :func:`_resolve_unique_base_class_id` (project-wide, unique-name-only)
      and inserts a ``ref_type='inherit'`` row (this class = caller, base = callee).
      Unresolved bases (external/stdlib, not found, or ambiguous - multiple
      same-named classes in the project) are skipped.
    - Backward: calls :func:`_backfill_children_inheritance_for_class` so any
      already-indexed class elsewhere in the project that lists this class as a
      base gets its edge filled in too - order-independent w.r.t. batch reindex.

    Args:
        db: Legacy DB facade-like (add_entity_cross_ref semantics).
        file_id: File id.
        project_id: Project id for resolution.

    Returns:
        Number of entity_cross_ref rows added.
    """
    rows = db._fetchall(
        "SELECT id, name, line, bases FROM classes WHERE file_id = ?",
        (file_id,),
    )
    added = 0
    for row in rows:
        class_id = row["id"]
        class_name = row.get("name")
        line = row["line"]

        base_names = _base_names_from_bases_raw(row.get("bases"))
        for base_name in base_names or []:
            callee_id = _resolve_unique_base_class_id(db, project_id, base_name)
            if callee_id is None:
                continue
            # Another class in this same file, processed earlier in this loop,
            # may already have backfilled this exact edge via
            # _backfill_children_inheritance_for_class (e.g. base and child
            # both defined in the file being indexed) - do not duplicate it.
            if _inherit_edge_exists(db, class_id, callee_id):
                continue
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

        if class_name:
            added += _backfill_children_inheritance_for_class(
                db, project_id, class_id, class_name
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

        # A single bad usage row (resolver or insert raising) must never abort
        # the whole function - that would also skip the inheritance step below
        # for the entire file, silently, with only a warning one level up in
        # atomic.py ("do not fail the whole file update"). Wrap the full
        # per-usage body, not just the insert.
        try:
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

    try:
        added += _add_inheritance_cross_ref_for_file(db, file_id, project_id)
    except Exception as e:
        logger.warning(
            "Failed to add inheritance entity_cross_ref for file_id=%s: %s",
            file_id,
            e,
            exc_info=True,
        )
    return added
