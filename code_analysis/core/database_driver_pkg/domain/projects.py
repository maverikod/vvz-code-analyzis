"""
Project operations, ported driver-direct (stage 2 layer collapse, Part 1).

Free-function port of ``code_analysis.core.database_client.client_api_projects``'s
``_ClientAPIProjectsMixin`` methods. Each function takes ``driver: Any`` (duck-typed
against ``execute``/``select``/``update`` - implemented identically by both
``PostgreSQLDriver`` and the legacy ``DatabaseClient``, see
scratchpad/stage2-parity-spike.md's primitive parity table) instead of ``self``, so
callers can be repointed to these functions immediately (passing either object) -
no construction-pivot dependency. Exact-shape preservation vs. the mixin methods is
mandatory and was the explicit acceptance criterion for this port (return dict keys,
None-vs-[] on empty, the two-tier get_project scoped/global fallback, the
insert_project_row 3-branch orphan-reclaim/raise, the scoped-write orphan-reclaim
helper) - verified line-for-line against client_api_projects.py during the port and
covered by tests/test_domain_projects_orphan_reclaim_gate.py (the Conscience
Condition 7 acceptance gate for this subsystem).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from code_analysis.core.database.watch_dirs_partition import (
    current_server_instance_id,
    current_server_instance_params,
    sql_projects_server_instance_filter,
)
from code_analysis.core.database_client.objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
)
from code_analysis.core.database_client.objects.project import Project
from code_analysis.core.project_root_path import (
    enrich_project_dict_resolve_root_path,
    normalize_path_simple,
    persist_projects_root_path_stored_value,
    resolve_project_root_absolute_str,
)
from code_analysis.core.sql_portable import (
    WHERE_FILES_ACTIVE,
    WHERE_FILES_ACTIVE_F,
    WHERE_FILES_ACTIVE_P,
    WHERE_PROJECTS_ACTIVE_P,
    sql_julian_timestamp_now_expr,
)

logger = logging.getLogger(__name__)


def _execute_select_first_row(
    driver: Any,
    sql: str,
    params: tuple[Any, ...],
    *,
    priority: int = 0,
    transaction_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Run SELECT via ``driver.execute`` and return the first row dict."""
    result = driver.execute(
        sql,
        params,
        transaction_id=transaction_id,
    )
    if not isinstance(result, dict):
        return None
    rows = result.get("data")
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    return dict(row) if isinstance(row, dict) else None


def _project_row_by_id_global(
    driver: Any,
    project_id: str,
    *,
    priority: int = 0,
    transaction_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch a ``projects`` row by ``id`` without ``server_instance_id`` filter."""
    return _execute_select_first_row(
        driver,
        "SELECT * FROM projects WHERE id = ? LIMIT 1",
        (project_id,),
        priority=priority,
        transaction_id=transaction_id,
    )


def _reclaim_orphan_and_retry_scoped_projects_write(
    driver: Any,
    *,
    sid: str,
    project_id: str,
    write_fn: "Callable[[], int]",
    priority: int = 0,
    transaction_id: Optional[str] = None,
) -> int:
    """Run a ``projects`` write scoped to ``(server_instance_id, id)``; reclaim orphans.

    See ``client_api_projects.py``'s function of the same name for the full
    rationale (orphan instance after a server reinstall/rebind). Ported verbatim,
    ``database`` renamed ``driver``.
    """
    affected = write_fn()
    if affected:
        return affected
    global_row = _project_row_by_id_global(
        driver, project_id, priority=priority, transaction_id=transaction_id
    )
    if global_row is None:
        return 0
    other_sid = global_row.get("server_instance_id")
    if other_sid == sid:
        return 0
    driver.update(
        "projects",
        where={"id": project_id},
        data={"server_instance_id": sid},
    )
    return write_fn()


def _resolved_project_root_norm(
    driver: Any,
    *,
    project_id: str,
    root_path_stored: Optional[str],
    watch_dir_id: Optional[str],
    project_name: Optional[str] = None,
) -> str:
    """Normalized absolute project root for same-disk comparisons (RPC-only reads)."""
    try:
        resolved = resolve_project_root_absolute_str(
            project_id=project_id or None,
            root_path_stored=root_path_stored,
            watch_dir_id=(
                str(watch_dir_id).strip()
                if watch_dir_id is not None and str(watch_dir_id).strip()
                else None
            ),
            project_name=project_name,
            database=driver,
            require_exists=False,
        )
    except Exception:
        return ""
    if not resolved:
        return ""
    return normalize_path_simple(resolved)


def insert_project_row(
    driver: Any,
    project_id: str,
    root_path_stored: str,
    name: str,
    *,
    comment: Optional[str] = None,
    watch_dir_id: Optional[str] = None,
    transaction_id: Optional[str] = None,
    priority: int = 0,
    deleted: bool = False,
    processing_paused: bool = False,
) -> None:
    """Insert or reclaim a ``projects`` row for the current server instance.

    Exact port of ``_ClientAPIProjectsMixin.insert_project_row`` - lookup and
    writes go only through ``driver.execute``/``driver.get_project``-equivalent
    (here: the module-level :func:`get_project`).
    """
    sid = current_server_instance_id()
    _now = sql_julian_timestamp_now_expr(driver)

    if get_project(driver, project_id) is not None:
        return

    global_row = _project_row_by_id_global(
        driver,
        project_id,
        priority=priority,
        transaction_id=transaction_id,
    )
    if global_row is not None:
        other_sid = global_row.get("server_instance_id")
        other_sid_str = str(other_sid).strip() if other_sid is not None else ""
        if not other_sid_str:
            driver.execute(
                f"""
                UPDATE projects
                SET server_instance_id = ?, root_path = ?, name = ?, comment = ?,
                    watch_dir_id = ?, updated_at = {_now}
                WHERE id = ?
                  AND (server_instance_id IS NULL OR server_instance_id = '')
                """,
                (
                    sid,
                    root_path_stored,
                    name,
                    comment,
                    watch_dir_id,
                    project_id,
                ),
                transaction_id=transaction_id,
            )
            logger.info(
                "Reclaimed orphan projects row id=%s for server_instance_id=%s",
                project_id,
                sid,
            )
            return
        if other_sid_str != sid:
            incoming_root = _resolved_project_root_norm(
                driver,
                project_id=project_id,
                root_path_stored=root_path_stored,
                watch_dir_id=watch_dir_id,
                project_name=name,
            )
            existing_root = _resolved_project_root_norm(
                driver,
                project_id=project_id,
                root_path_stored=str(global_row.get("root_path") or ""),
                watch_dir_id=(
                    str(global_row["watch_dir_id"])
                    if global_row.get("watch_dir_id") is not None
                    else None
                ),
                project_name=str(global_row.get("name") or "") or None,
            )
            if incoming_root and existing_root and incoming_root == existing_root:
                driver.execute(
                    f"""
                    UPDATE projects
                    SET server_instance_id = ?, root_path = ?, name = ?, comment = ?,
                        watch_dir_id = ?, updated_at = {_now}
                    WHERE id = ?
                      AND server_instance_id = ?
                    """,
                    (
                        sid,
                        root_path_stored,
                        name,
                        comment,
                        watch_dir_id,
                        project_id,
                        other_sid_str,
                    ),
                    transaction_id=transaction_id,
                )
                logger.info(
                    "Reassigned projects row id=%s from server_instance_id=%s "
                    "to %s (same disk root %s)",
                    project_id,
                    other_sid_str,
                    sid,
                    incoming_root,
                )
                return
            raise ValueError(
                f"Project id {project_id} is already registered under "
                f"server_instance_id={other_sid_str} (current instance {sid}). "
                "Cannot insert the same project UUID for another server instance "
                "while projects.id remains a global primary key."
            )
        return

    driver.execute(
        f"""
        INSERT INTO projects (
            id, server_instance_id, root_path, name, comment, watch_dir_id,
            deleted, processing_paused, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, {_now})
        """,
        (
            project_id,
            sid,
            root_path_stored,
            name,
            comment,
            watch_dir_id,
            bool(deleted),
            bool(processing_paused),
        ),
        transaction_id=transaction_id,
    )


def sync_project_metadata_from_projectid(
    driver: Any,
    root_dir: str | Path,
    *,
    transaction_id: Optional[str] = None,
    priority: int = 0,
) -> Optional[str]:
    """Sync ``projects.deleted``, ``processing_paused``, ``comment`` from ``projectid``.

    Exact port of ``_ClientAPIProjectsMixin.sync_project_metadata_from_projectid``.
    """
    from code_analysis.core.project_resolution import load_project_info

    try:
        info = load_project_info(root_dir)
    except Exception as e:
        logger.warning(
            "sync_project_metadata_from_projectid: cannot load projectid at %s: %s",
            root_dir,
            e,
        )
        return None

    sid = current_server_instance_id()

    def _write() -> int:
        """Run the scoped UPDATE once; return affected row count."""
        result = driver.execute(
            """
            UPDATE projects
            SET deleted = ?,
                processing_paused = ?,
                comment = ?
            WHERE server_instance_id = ? AND id = ?
            """,
            (
                bool(info.deleted),
                bool(info.processing_paused),
                info.description or None,
                sid,
                info.project_id,
            ),
            transaction_id=transaction_id,
        )
        affected_rows = result.get("affected_rows", 0) if isinstance(result, dict) else 0
        return int(affected_rows) if isinstance(affected_rows, int) else 0

    _reclaim_orphan_and_retry_scoped_projects_write(
        driver,
        sid=sid,
        project_id=info.project_id,
        write_fn=_write,
        priority=priority,
        transaction_id=transaction_id,
    )
    return info.project_id


def get_project(driver: Any, project_id: str) -> Optional[Project]:
    """Get project by ID.

    Exact port of ``_ClientAPIProjectsMixin.get_project`` - scoped lookup first,
    unscoped global-by-id fallback (:func:`_project_row_by_id_global`) on miss.
    """
    sid = current_server_instance_id()
    rows = driver.select(
        "projects",
        where={"server_instance_id": sid, "id": project_id},
    )
    if rows:
        row = enrich_project_dict_resolve_root_path(dict(rows[0]), driver)
        return db_row_to_object(row, Project)

    global_row = _project_row_by_id_global(driver, project_id)
    if global_row is None:
        return None
    row = enrich_project_dict_resolve_root_path(dict(global_row), driver)
    return db_row_to_object(row, Project)


def list_projects(driver: Any, *, include_deleted: bool = False) -> List[Project]:
    """List projects in database.

    Exact port of ``_ClientAPIProjectsMixin.list_projects``.
    """
    sid_params = current_server_instance_params()
    if include_deleted:
        sql = (
            "SELECT p.* FROM projects p "
            "WHERE p.server_instance_id = ? ORDER BY p.created_at"
        )
        list_params: tuple[Any, ...] = sid_params
    else:
        _proj_del = f" AND {WHERE_PROJECTS_ACTIVE_P}"
        sql = (
            "SELECT p.* FROM projects p "
            "WHERE p.server_instance_id = ? "
            "AND p.id IN ("
            "  SELECT project_id FROM files "
            f"  WHERE {WHERE_FILES_ACTIVE} "
            "  GROUP BY project_id"
            ")" + _proj_del + " UNION "
            "SELECT p.* FROM projects p "
            "WHERE p.server_instance_id = ? "
            "AND p.id NOT IN (SELECT project_id FROM files)"
            + _proj_del
            + " ORDER BY created_at"
        )
        list_params = sid_params + sid_params
    result = driver.execute(sql, list_params)
    rows = (
        result.get("data", [])
        if isinstance(result, dict)
        else (result if isinstance(result, list) else [])
    )
    enriched = [enrich_project_dict_resolve_root_path(dict(r), driver) for r in rows]
    return db_rows_to_objects(enriched, Project)


def get_all_projects(driver: Any) -> List[Dict[str, Any]]:
    """Get all active (non-soft-deleted) projects as row dicts.

    Exact port of ``_ClientAPIProjectsMixin.get_all_projects``.
    """
    proj_where, proj_params = sql_projects_server_instance_filter("p")
    sql = (
        "SELECT p.id, p.root_path, p.name, p.comment, p.watch_dir_id, p.updated_at "
        "FROM projects p "
        f"WHERE {proj_where} AND " + WHERE_FILES_ACTIVE_P + " "
        "AND (NOT EXISTS (SELECT 1 FROM files f WHERE f.project_id = p.id) "
        "   OR EXISTS (SELECT 1 FROM files f WHERE f.project_id = p.id "
        "              AND " + WHERE_FILES_ACTIVE_F + ")) "
        "ORDER BY p.name, p.root_path"
    )
    result = driver.execute(sql, proj_params)
    rows = (
        result.get("data", [])
        if isinstance(result, dict)
        else (result if isinstance(result, list) else [])
    )
    return rows if rows else []


def relocate_project_root_after_disk_move(
    driver: Any,
    project_id: str,
    old_root_path: str,
    new_root_path: str,
    new_watch_dir_id: Optional[str] = None,
) -> bool:
    """
    Same project UUID, new directory under a watch root: update only ``projects``.

    Exact port of ``_ClientAPIProjectsMixin.relocate_project_root_after_disk_move``.
    """
    try:
        old_r = Path(old_root_path).expanduser().resolve()
        new_r = Path(new_root_path).expanduser().resolve()
    except OSError as e:
        logger.warning(
            "relocate_project_root_after_disk_move: cannot resolve old=%s new=%s: %s",
            old_root_path,
            new_root_path,
            e,
        )
        return False

    def _fetchone(sql: str, params: tuple[Any, ...]) -> Optional[Dict[str, Any]]:
        """Return fetchone."""
        r = driver.execute(sql, params)
        if not isinstance(r, dict):
            return None
        data = r.get("data")
        if isinstance(data, list) and data:
            row0 = data[0]
            return row0 if isinstance(row0, dict) else None
        return None

    def _affected_rows(result: Any) -> int:
        """Return ``affected_rows`` from a ``driver.execute`` UPDATE result."""
        affected = result.get("affected_rows", 0) if isinstance(result, dict) else 0
        return int(affected) if isinstance(affected, int) else 0

    now_sql = sql_julian_timestamp_now_expr(driver)
    sid = current_server_instance_id()

    if old_r == new_r:
        if new_watch_dir_id is not None:

            def _write_watch_dir_only() -> int:
                """Scoped ``watch_dir_id``-only UPDATE; returns affected row count."""
                return _affected_rows(
                    driver.execute(
                        f"UPDATE projects SET watch_dir_id = ?, "
                        f"updated_at = {now_sql} "
                        "WHERE server_instance_id = ? AND id = ?",
                        (new_watch_dir_id, sid, project_id),
                    )
                )

            _reclaim_orphan_and_retry_scoped_projects_write(
                driver,
                sid=sid,
                project_id=project_id,
                write_fn=_write_watch_dir_only,
            )
        return True

    cur = _fetchone(
        "SELECT watch_dir_id FROM projects WHERE server_instance_id = ? AND id = ?",
        (sid, project_id),
    )
    if cur is None:
        global_cur = _project_row_by_id_global(driver, project_id)
        if global_cur is not None:
            cur = global_cur
    effective_wd = (
        str(new_watch_dir_id)
        if new_watch_dir_id is not None
        else (
            str(cur.get("watch_dir_id"))
            if isinstance(cur, dict) and cur.get("watch_dir_id")
            else ""
        )
    )
    new_stored = persist_projects_root_path_stored_value(
        project_root_absolute=new_r,
        watch_dir_id=effective_wd or None,
        database=driver,
    )
    if effective_wd:
        other = _fetchone(
            "SELECT id FROM projects WHERE server_instance_id = ? "
            "AND watch_dir_id IS NOT NULL AND watch_dir_id = ? "
            "AND root_path = ? AND id != ? LIMIT 1",
            (sid, effective_wd, new_stored, project_id),
        )
    else:
        other = _fetchone(
            "SELECT id FROM projects WHERE server_instance_id = ? "
            "AND root_path = ? AND id != ? LIMIT 1",
            (sid, new_stored, project_id),
        )
    if other:
        logger.error(
            "relocate_project_root_after_disk_move: root_path %s already used by "
            "project %s; refusing to move project %s from %s",
            new_stored,
            other.get("id"),
            project_id,
            old_r,
        )
        return False

    if (
        _fetchone(
            "SELECT id FROM projects WHERE server_instance_id = ? AND id = ?",
            (sid, project_id),
        )
        is None
        and _project_row_by_id_global(driver, project_id) is None
    ):
        logger.warning(
            "relocate_project_root_after_disk_move: project %s not found",
            project_id,
        )
        return False

    new_name = new_r.name
    if new_watch_dir_id is not None:

        def _write_root() -> int:
            """Scoped root-relocation UPDATE incl. ``watch_dir_id``."""
            return _affected_rows(
                driver.execute(
                    f"UPDATE projects SET root_path = ?, name = ?, watch_dir_id = ?, "
                    f"updated_at = {now_sql} WHERE server_instance_id = ? AND id = ?",
                    (new_stored, new_name, new_watch_dir_id, sid, project_id),
                )
            )

    else:

        def _write_root() -> int:
            """Scoped root-relocation UPDATE (``watch_dir_id`` unchanged)."""
            return _affected_rows(
                driver.execute(
                    f"UPDATE projects SET root_path = ?, name = ?, "
                    f"updated_at = {now_sql} "
                    "WHERE server_instance_id = ? AND id = ?",
                    (new_stored, new_name, sid, project_id),
                )
            )

    _reclaim_orphan_and_retry_scoped_projects_write(
        driver,
        sid=sid,
        project_id=project_id,
        write_fn=_write_root,
    )

    logger.info(
        "relocate_project_root_after_disk_move: project_id=%s root %s -> %s "
        "(projects row only; file paths unchanged)",
        project_id,
        old_r,
        new_r,
    )
    return True
