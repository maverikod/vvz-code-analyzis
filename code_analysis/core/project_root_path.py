"""
Project root path storage vs watch directory.

``projects.root_path`` under a ``watch_dir_id`` stores the **immediate child folder
name** under that watch directory's absolute path (POSIX segment, no ``/``). Only
``watch_dir_paths.absolute_path`` is a full absolute path. Legacy rows may still
store an absolute path in ``projects.root_path`` when ``watch_dir_id`` is NULL or
before migration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, cast

from code_analysis.core.path_normalization import normalize_path_simple

logger = logging.getLogger(__name__)


def is_legacy_projects_root_path_absolute_storage(stored: str) -> bool:
    """True if ``stored`` is a legacy absolute filesystem path (not a watch-relative segment)."""
    s = (stored or "").strip().replace("\\", "/")
    if not s:
        return False
    return Path(s).is_absolute()


def fetch_watch_dir_absolute_path(database: Any, watch_dir_id: str) -> Optional[str]:
    """Return ``watch_dir_paths.absolute_path`` for ``watch_dir_id``, or None."""
    wid = (watch_dir_id or "").strip()
    if not wid:
        return None
    sql = "SELECT absolute_path FROM watch_dir_paths WHERE watch_dir_id = ? LIMIT 1"
    params: tuple[Any, ...] = (wid,)

    gf = getattr(database, "_fetchone", None)
    if callable(gf):
        row = gf(sql, params)
        if isinstance(row, dict) and row.get("absolute_path"):
            return str(row["absolute_path"]).strip() or None
        return None

    ex = getattr(database, "execute", None)
    if not callable(ex):
        return None
    try:
        result = ex(sql, params)
    except Exception:
        return None
    if isinstance(result, list) and result:
        row0 = result[0]
        if isinstance(row0, dict) and row0.get("absolute_path"):
            return str(row0["absolute_path"]).strip() or None
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, list) and data:
            row0 = data[0]
            if isinstance(row0, dict) and row0.get("absolute_path"):
                return str(row0["absolute_path"]).strip() or None
    return None


def resolve_projects_root_path_row_to_absolute_str(
    *,
    root_path_stored: Optional[str],
    watch_dir_id: Optional[str],
    database: Any,
) -> str:
    """
    Resolve ``projects.root_path`` + ``watch_dir_id`` to a normalized absolute path string.

    Legacy: when ``root_path_stored`` is already absolute, return it normalized.
    New: single-segment folder name under ``watch_dir_paths.absolute_path``.
    """
    raw = (root_path_stored or "").strip()
    if not raw:
        return ""
    if is_legacy_projects_root_path_absolute_storage(raw):
        return normalize_path_simple(raw)
    wd = (watch_dir_id or "").strip() or None
    if not wd:
        return normalize_path_simple(raw) if Path(raw).is_absolute() else ""
    watch = fetch_watch_dir_absolute_path(database, wd)
    if not watch:
        logger.warning(
            "resolve_projects_root_path: no watch_dir_paths row for watch_dir_id=%s",
            wd,
        )
        return normalize_path_simple(raw) if Path(raw).is_absolute() else ""
    return normalize_path_simple(Path(watch) / raw)


def persist_projects_root_path_stored_value(
    *,
    project_root_absolute: Path,
    watch_dir_id: Optional[str],
    database: Any,
) -> str:
    """
    Value to persist in ``projects.root_path``.

    When linked to a watch dir and the project root is exactly one level below that
    watch path, store **only the folder name** (segment). Otherwise store a normalized
    absolute path (legacy / edge cases).
    """
    wd = (watch_dir_id or "").strip() or None
    if not wd:
        return normalize_path_simple(project_root_absolute)
    watch = fetch_watch_dir_absolute_path(database, wd)
    if not watch:
        return normalize_path_simple(project_root_absolute)
    try:
        pr = Path(project_root_absolute).resolve()
        w = Path(watch).resolve()
        rel = pr.relative_to(w)
    except (OSError, ValueError):
        return normalize_path_simple(project_root_absolute)
    parts = rel.parts
    if len(parts) != 1:
        return normalize_path_simple(project_root_absolute)
    return parts[0]


def enrich_project_dict_resolve_root_path(
    row: Mapping[str, Any], database: Any
) -> Dict[str, Any]:
    """Copy ``row`` and set ``root_path`` to the resolved absolute path string."""
    out = dict(cast(Dict[str, Any], row))
    out["root_path"] = resolve_projects_root_path_row_to_absolute_str(
        root_path_stored=str(out.get("root_path") or ""),
        watch_dir_id=str(out["watch_dir_id"])
        if out.get("watch_dir_id") is not None
        else None,
        database=database,
    )
    return out


def find_project_id_by_resolved_absolute_root(
    database: Any, absolute_root: str
) -> Optional[str]:
    """
    Find ``projects.id`` whose resolved filesystem root equals ``absolute_root``.

    Matches legacy rows (absolute ``root_path``) and watch-relative segment rows.
    """
    want = normalize_path_simple(absolute_root)

    def _fetchone(sql: str, params: tuple[Any, ...]) -> Optional[Dict[str, Any]]:
        gf = getattr(database, "_fetchone", None)
        if callable(gf):
            r = gf(sql, params)
            if isinstance(r, dict):
                return r
            if r is not None and not isinstance(r, dict):
                try:
                    return dict(cast(Any, r))
                except Exception:
                    return None
            return None
        ex = getattr(database, "execute", None)
        if not callable(ex):
            return None
        try:
            result = ex(sql, params)
        except Exception:
            return None
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return data[0]
        return None

    def _fetchall(sql: str, params: tuple[Any, ...]) -> List[Dict[str, Any]]:
        gf = getattr(database, "_fetchall", None)
        if callable(gf):
            rows = gf(sql, params)
            out: List[Dict[str, Any]] = []
            for r in rows:
                if isinstance(r, dict):
                    out.append(r)
                else:
                    try:
                        out.append(dict(cast(Any, r)))
                    except Exception:
                        continue
            return out
        ex = getattr(database, "execute", None)
        if not callable(ex):
            return []
        try:
            result = ex(sql, params)
        except Exception:
            return []
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
        return []

    hit = _fetchone(
        "SELECT id FROM projects WHERE root_path = ? LIMIT 1", (want,)
    )
    if hit and hit.get("id") is not None:
        return str(hit["id"])

    rows = _fetchall("SELECT id, root_path, watch_dir_id FROM projects", ())
    for r in rows:
        resolved = resolve_projects_root_path_row_to_absolute_str(
            root_path_stored=str(r.get("root_path") or ""),
            watch_dir_id=str(r["watch_dir_id"])
            if r.get("watch_dir_id") is not None
            else None,
            database=database,
        )
        if resolved and normalize_path_simple(resolved) == want:
            return str(r["id"])
    return None
