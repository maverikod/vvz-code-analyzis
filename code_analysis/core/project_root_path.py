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


def _is_existing_directory(path: str | Path) -> bool:
    """True when ``path`` resolves to an existing directory on this host."""
    try:
        return Path(path).resolve().is_dir()
    except OSError:
        return False


def _normalize_existing_watch_dir_path(path: str) -> Optional[str]:
    """Return normalized watch path when it exists as a directory, else None."""
    raw = (path or "").strip()
    if not raw:
        return None
    try:
        normalized = normalize_path_simple(str(Path(raw).resolve()))
    except OSError:
        return None
    if not normalized or not _is_existing_directory(normalized):
        return None
    return normalized


def is_legacy_projects_root_path_absolute_storage(stored: str) -> bool:
    """True if ``stored`` is a legacy absolute filesystem path (not a watch-relative segment)."""
    s = (stored or "").strip().replace("\\", "/")
    if not s:
        return False
    return Path(s).is_absolute()


def fetch_watch_dir_absolute_path(database: Any, watch_dir_id: str) -> Optional[str]:
    """Return ``watch_dir_paths.absolute_path`` for ``watch_dir_id``, or None."""
    from code_analysis.core.database.watch_dirs_partition import (
        current_server_instance_id,
    )

    wid = (watch_dir_id or "").strip()
    if not wid:
        return None
    sid = current_server_instance_id()
    sql = (
        "SELECT absolute_path FROM watch_dir_paths "
        "WHERE server_instance_id = ? AND watch_dir_id = ? LIMIT 1"
    )
    params: tuple[Any, ...] = (sid, wid)

    gf = getattr(database, "_fetchone", None)
    if callable(gf):
        row = gf(sql, params)
        if isinstance(row, dict) and row.get("absolute_path"):
            return _normalize_existing_watch_dir_path(str(row["absolute_path"]))
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
            return _normalize_existing_watch_dir_path(str(row0["absolute_path"]))
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, list) and data:
            row0 = data[0]
            if isinstance(row0, dict) and row0.get("absolute_path"):
                return _normalize_existing_watch_dir_path(str(row0["absolute_path"]))
    return None


def fetch_all_watch_dir_absolute_paths(database: Any) -> List[tuple[str, str]]:
    """Return ``(watch_dir_id, absolute_path)`` for rows whose path exists on disk."""
    from code_analysis.core.database.watch_dirs_partition import (
        current_server_instance_id,
    )

    sid = current_server_instance_id()
    sql = (
        "SELECT watch_dir_id, absolute_path FROM watch_dir_paths "
        "WHERE server_instance_id = ? "
        "AND absolute_path IS NOT NULL AND TRIM(absolute_path) != '' "
        "ORDER BY watch_dir_id"
    )
    params: tuple[Any, ...] = (sid,)

    def _rows_from_result(result: Any) -> List[Dict[str, Any]]:
        """Return rows from result."""
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
        return []

    gf = getattr(database, "_fetchall", None)
    if callable(gf):
        raw_rows = gf(sql, params)
    else:
        ex = getattr(database, "execute", None)
        if not callable(ex):
            return []
        try:
            raw_rows = _rows_from_result(ex(sql, params))
        except Exception:
            return []

    out: List[tuple[str, str]] = []
    for row in raw_rows if isinstance(raw_rows, list) else []:
        if not isinstance(row, dict):
            continue
        wid = str(row.get("watch_dir_id") or "").strip()
        path = _normalize_existing_watch_dir_path(str(row.get("absolute_path") or ""))
        if wid and path:
            out.append((wid, path))
    return out


def _folder_name_candidates(
    root_path_stored: Optional[str], project_name: Optional[str]
) -> List[str]:
    """Watch-relative folder names to probe under each known watch root."""
    raw = (root_path_stored or "").strip()
    out: List[str] = []
    if raw and not is_legacy_projects_root_path_absolute_storage(raw):
        out.append(raw)
    name = (project_name or "").strip()
    if name and name not in out:
        out.append(name)
    return out


def _projectid_matches(project_root: Path, project_id: str) -> bool:
    """True when ``project_root/projectid`` exists and its id equals ``project_id``."""
    pid = (project_id or "").strip()
    if not pid:
        return True
    try:
        from code_analysis.core.project_resolution import load_project_info

        info = load_project_info(project_root)
        return info.project_id == pid
    except Exception:
        return False


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


def resolve_project_root_absolute_str(
    *,
    project_id: Optional[str] = None,
    root_path_stored: Optional[str],
    watch_dir_id: Optional[str],
    project_name: Optional[str] = None,
    database: Any,
    require_exists: bool = True,
) -> str:
    """
    Resolve a project row to an absolute root path string.

    Primary: ``watch_dir_id`` linked in ``projects`` + ``root_path`` segment (or legacy
    absolute ``root_path``). Fallback: scan **all** ``watch_dir_paths`` rows whose path
    exists on this host. Shared DB + per-server watch UUIDs are supported.

    When ``require_exists`` is True (default), both the watch directory and the resolved
    project root directory must exist on disk on this server instance.
    """
    raw = (root_path_stored or "").strip()

    if raw and is_legacy_projects_root_path_absolute_storage(raw):
        legacy = normalize_path_simple(raw)
        if legacy and Path(legacy).is_absolute():
            if not require_exists or _is_existing_directory(legacy):
                if _projectid_matches(Path(legacy), project_id or ""):
                    return legacy

    primary = resolve_projects_root_path_row_to_absolute_str(
        root_path_stored=raw,
        watch_dir_id=watch_dir_id,
        database=database,
    ).strip()
    if primary and Path(primary).is_absolute():
        primary_exists = _is_existing_directory(primary)
        if not require_exists or primary_exists:
            # When the target does not exist yet on disk (require_exists=False,
            # e.g. restore_project_from_trash resolving the pre-move destination),
            # there is nothing under ``primary`` for _projectid_matches to read --
            # it always returns False, which would wrongly discard a primary path
            # that was already correctly derived from the caller-supplied, trusted
            # watch_dir_id. Trust it directly in that case. When primary DOES
            # exist, keep validating the projectid match (guards against an
            # unrelated project's folder occupying the same path).
            if not primary_exists or _projectid_matches(Path(primary), project_id or ""):
                return primary

    folders = _folder_name_candidates(raw, project_name)
    if not folders:
        return ""

    matches: List[str] = []
    for _wid, watch in fetch_all_watch_dir_absolute_paths(database):
        for folder in folders:
            try:
                candidate = normalize_path_simple(str((Path(watch) / folder).resolve()))
            except OSError:
                continue
            if not candidate or not Path(candidate).is_absolute():
                continue
            if require_exists and not _is_existing_directory(candidate):
                continue
            root = Path(candidate)
            pid_file = root / "projectid"
            if pid_file.is_file() and project_id:
                if not _projectid_matches(root, project_id):
                    continue
            matches.append(candidate)

    if not matches:
        return ""

    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return unique[0]

    if project_id:
        for candidate in unique:
            if _projectid_matches(Path(candidate), project_id):
                return candidate

    logger.warning(
        "resolve_project_root_absolute_str: ambiguous roots for project_id=%s: %s",
        project_id,
        unique,
    )
    return unique[0]


def resolve_watch_dir_absolute_for_project_row(
    *,
    project_id: Optional[str],
    root_path_stored: Optional[str],
    watch_dir_id: Optional[str],
    project_name: Optional[str],
    database: Any,
) -> Optional[str]:
    """Watch directory path that resolves ``project_id`` on this server, if any."""
    resolved_root = resolve_project_root_absolute_str(
        project_id=project_id,
        root_path_stored=root_path_stored,
        watch_dir_id=watch_dir_id,
        project_name=project_name,
        database=database,
        require_exists=True,
    )
    if not resolved_root:
        return None
    try:
        project_root = Path(resolved_root).resolve()
    except OSError:
        return None
    for _wid, watch in fetch_all_watch_dir_absolute_paths(database):
        try:
            watch_root = Path(watch).resolve()
            project_root.relative_to(watch_root)
        except (OSError, ValueError):
            continue
        return normalize_path_simple(watch)
    return None


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
    out["root_path"] = resolve_project_root_absolute_str(
        project_id=str(out.get("id") or "").strip() or None,
        root_path_stored=str(out.get("root_path") or ""),
        watch_dir_id=(
            str(out["watch_dir_id"]) if out.get("watch_dir_id") is not None else None
        ),
        project_name=str(out.get("name") or "").strip() or None,
        database=database,
        require_exists=True,
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
        """Return fetchone."""
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
        """Return fetchall."""
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

    from code_analysis.core.database.watch_dirs_partition import (
        current_server_instance_id,
    )

    sid = current_server_instance_id()
    hit = _fetchone(
        "SELECT id FROM projects WHERE server_instance_id = ? AND root_path = ? LIMIT 1",
        (sid, want),
    )
    if hit and hit.get("id") is not None:
        return str(hit["id"])

    rows = _fetchall(
        "SELECT id, root_path, watch_dir_id, name FROM projects "
        "WHERE server_instance_id = ?",
        (sid,),
    )
    for r in rows:
        resolved = resolve_project_root_absolute_str(
            project_id=str(r.get("id") or "").strip() or None,
            root_path_stored=str(r.get("root_path") or ""),
            watch_dir_id=(
                str(r["watch_dir_id"]) if r.get("watch_dir_id") is not None else None
            ),
            project_name=str(r.get("name") or "").strip() or None,
            database=database,
            require_exists=True,
        )
        if resolved and normalize_path_simple(resolved) == want:
            return str(r["id"])
    return None
