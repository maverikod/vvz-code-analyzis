"""
Partition-scoped read queries for watch_dirs / watch_dir_paths.

Usable from :class:`~code_analysis.core.database.base.CodeDatabase` (driver) and
:class:`~code_analysis.core.database_client.client.DatabaseClient` (RPC).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from code_analysis.core.project_root_path import (
    _normalize_existing_watch_dir_path,
    fetch_watch_dir_absolute_path,
)

from .watch_dirs_partition import current_server_instance_id


def _database_query_rows(
    database: Any, sql: str, params: tuple[Any, ...]
) -> List[Dict[str, Any]]:
    """Run SELECT and return row dicts (CodeDatabase or DatabaseClient)."""
    gf = getattr(database, "_fetchall", None)
    if callable(gf):
        raw = gf(sql, params)
        return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []

    ex = getattr(database, "execute", None)
    if not callable(ex):
        return []
    try:
        result = ex(sql, params)
    except Exception:
        return []
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
    return []


def list_watch_dirs_with_paths(database: Any) -> List[Dict[str, Any]]:
    """List watch dirs for the current server instance with optional absolute paths."""
    sid = current_server_instance_id()
    rows = _database_query_rows(
        database,
        """
        SELECT wd.id, wd.name, wdp.absolute_path
        FROM watch_dirs wd
        LEFT JOIN watch_dir_paths wdp
          ON wd.server_instance_id = wdp.server_instance_id
         AND wd.id = wdp.watch_dir_id
        WHERE wd.server_instance_id = ?
        ORDER BY wd.created_at
        """,
        (sid,),
    )
    return [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "absolute_path": r.get("absolute_path"),
        }
        for r in rows
    ]


def list_watch_dir_path_pairs(database: Any) -> List[tuple[str, str]]:
    """Return ``(watch_dir_id, absolute_path)`` for non-empty paths on this instance."""
    sid = current_server_instance_id()
    rows = _database_query_rows(
        database,
        """
        SELECT watch_dir_id, absolute_path FROM watch_dir_paths
        WHERE server_instance_id = ?
          AND absolute_path IS NOT NULL AND TRIM(absolute_path) != ''
        ORDER BY watch_dir_id
        """,
        (sid,),
    )
    out: List[tuple[str, str]] = []
    for row in rows:
        wid = str(row.get("watch_dir_id") or "").strip()
        path = _normalize_existing_watch_dir_path(str(row.get("absolute_path") or ""))
        if wid and path:
            out.append((wid, path))
    return out


def resolve_watch_dir_id_for_project_root(
    database: Any, project_root: Path
) -> Optional[str]:
    """
    Return ``watch_dir_id`` whose ``absolute_path`` is the direct parent of ``project_root``.
    """
    try:
        parent = project_root.resolve().parent
    except OSError:
        return None
    for wid, watch_abs in list_watch_dir_path_pairs(database):
        try:
            if parent == Path(watch_abs).resolve():
                return wid
        except (OSError, ValueError):
            continue
    return None


def get_watch_dir_absolute_path(database: Any, watch_dir_id: str) -> Optional[str]:
    """Thin alias to :func:`~code_analysis.core.project_root_path.fetch_watch_dir_absolute_path`."""
    return fetch_watch_dir_absolute_path(database, watch_dir_id)


def watch_dir_exists(database: Any, watch_dir_id: str) -> bool:
    """True when ``watch_dirs`` has a row for this instance and ``watch_dir_id``."""
    wid = (watch_dir_id or "").strip()
    if not wid:
        return False
    sid = current_server_instance_id()
    rows = _database_query_rows(
        database,
        "SELECT 1 FROM watch_dirs WHERE server_instance_id = ? AND id = ? LIMIT 1",
        (sid, wid),
    )
    return bool(rows)
