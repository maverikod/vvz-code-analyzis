"""
Entity-index integrity self-check (TZ-CA-INDEX-INTEGRITY-001 C-1).

The relational entity tables (functions/classes/methods) can become empty or
unlinked for a project while files/trees survive. Consumers of the entity path
then return a silent empty instead of an error. This check makes that condition
loud: if a project has indexed files but ZERO entity rows, ``ok`` is False and
the caller logs/surfaces it as a hard signal rather than a clean-looking empty.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE


def _count(database: Any, sql: str, project_id: str) -> int:
    """Return count."""
    res = database.execute(sql, (project_id,))
    rows = res.get("data", []) if isinstance(res, dict) else (res or [])
    if not rows:
        return 0
    row = rows[0]
    val = row.get("cnt") if hasattr(row, "get") else row[0]
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def check_entity_index(database: Any, project_id: str) -> Dict[str, Any]:
    """Return entity-index health for a project.

    ``ok`` is False only for the desync signature: indexed files exist but the
    functions/classes/methods tables are all empty for the project.
    """
    files = _count(
        database,
        f"SELECT COUNT(*) AS cnt FROM files WHERE project_id = ? AND {WHERE_FILES_ACTIVE}",
        project_id,
    )
    functions = _count(
        database,
        "SELECT COUNT(*) AS cnt FROM functions fn JOIN files f ON f.id = fn.file_id "
        "WHERE f.project_id = ?",
        project_id,
    )
    classes = _count(
        database,
        "SELECT COUNT(*) AS cnt FROM classes c JOIN files f ON f.id = c.file_id "
        "WHERE f.project_id = ?",
        project_id,
    )
    methods = _count(
        database,
        "SELECT COUNT(*) AS cnt FROM methods m JOIN classes c ON c.id = m.class_id "
        "JOIN files f ON f.id = c.file_id WHERE f.project_id = ?",
        project_id,
    )
    entities = functions + classes + methods
    return {
        "files": files,
        "functions": functions,
        "classes": classes,
        "methods": methods,
        "entities": entities,
        "ok": not (files > 0 and entities == 0),
    }
