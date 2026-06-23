"""
Persist integrity findings into ``issues`` via DatabaseClient (RPC → driver → SUBD).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from code_analysis.core.database_client.objects.analysis import Issue

logger = logging.getLogger(__name__)

ISSUE_MISSING_FILE = "missing_file_on_disk"
ISSUE_CIRCULAR_IMPORT = "circular_import"
INTEGRITY_ISSUE_TYPES: tuple[str, ...] = (
    ISSUE_MISSING_FILE,
    ISSUE_CIRCULAR_IMPORT,
)


def clear_integrity_issues(database: Any, project_id: str) -> int:
    """Delete existing integrity issues for ``project_id``; return rows removed."""
    if hasattr(database, "clear_project_integrity_issues"):
        return database.clear_project_integrity_issues(
            project_id, INTEGRITY_ISSUE_TYPES
        )
    placeholders = ",".join("?" for _ in INTEGRITY_ISSUE_TYPES)
    sql = (
        f"DELETE FROM issues WHERE project_id = ? "
        f"AND issue_type IN ({placeholders})"
    )
    params = (project_id, *INTEGRITY_ISSUE_TYPES)
    result = database.execute(sql, params)
    affected = result.get("affected_rows", 0) if isinstance(result, dict) else 0
    try:
        return int(affected) if affected is not None else 0
    except (TypeError, ValueError):
        return 0


def register_missing_file_issues(
    database: Any,
    project_id: str,
    missing: Sequence[Dict[str, Any]],
) -> int:
    """Insert ``missing_file_on_disk`` issues; return count inserted."""
    count = 0
    for item in missing:
        file_id = item.get("file_id")
        rel = item.get("relative_path") or item.get("path") or ""
        resolved = item.get("resolved_path") or ""
        desc = f"Indexed file missing on disk: {rel}"
        issue = Issue(
            file_id=file_id,
            project_id=project_id,
            issue_type=ISSUE_MISSING_FILE,
            description=desc,
            metadata={"resolved_path": resolved, "relative_path": rel},
        )
        _persist_issue(database, issue)
        count += 1
    return count


def register_circular_import_issues(
    database: Any,
    project_id: str,
    cycles: Sequence[Sequence[str]],
    *,
    file_id_to_path: Optional[Dict[str, str]] = None,
) -> int:
    """Insert ``circular_import`` issues; return count inserted."""
    path_map = file_id_to_path or {}
    count = 0
    for cycle in cycles:
        # find_cycles returns SCC node lists (no repeated closing node), so a
        # genuine 2-file cycle a<->b is [a, b] (length 2). Only single-node
        # self-loops (length 1) are dropped. (The old SQL path-form repeated the
        # closing node, hence the previous len<3 threshold — wrong for SCCs.)
        if len(cycle) < 2:
            continue
        anchor = cycle[0]
        path_labels = [path_map.get(fid, fid) for fid in cycle]
        # Show the closure for readability: a -> b -> a.
        desc = "Circular import: " + " -> ".join([*path_labels, path_labels[0]])
        issue = Issue(
            file_id=anchor,
            project_id=project_id,
            issue_type=ISSUE_CIRCULAR_IMPORT,
            description=desc,
            metadata={"file_ids": list(cycle), "paths": path_labels},
        )
        _persist_issue(database, issue)
        count += 1
    return count


def _persist_issue(database: Any, issue: Issue) -> None:
    """Write one issue through the universal client API when available."""
    if hasattr(database, "create_issue"):
        database.create_issue(issue)
        return
    row = issue.to_db_row()
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT INTO issues ({', '.join(cols)}) VALUES ({placeholders})"
    database.execute(sql, tuple(row[c] for c in cols))
