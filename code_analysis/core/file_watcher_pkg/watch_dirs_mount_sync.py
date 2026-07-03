"""
Filesystem-first synchronization of watch directories under a mount root.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from code_analysis.core.constants import (
    CASMGR_DOCKER_WATCH_ROOT,
    CASMGR_NATIVE_HOST_WATCH_ROOT,
)
from code_analysis.core.database.watch_dir_sql import watch_dirs_insert_new_row_sql
from code_analysis.core.docker_watch_paths import docker_watch_dir_container_path
from code_analysis.core.fs_permissions import log_fs_access_error
from code_analysis.core.path_normalization import normalize_path_simple
from code_analysis.core.watch_dir_settings import (
    WatchDirSettings,
    ensure_watch_dir_settings,
    load_watch_dir_settings,
    write_watch_dir_settings,
)
from code_analysis.core.worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY

from .multi_project_worker_specs import WatchDirSpec

logger = logging.getLogger(__name__)

LogicalWriteProgramV1 = Dict[str, Any]


def _current_server_instance_id() -> str:
    """Return current server instance id."""
    from code_analysis.core.server_instance import get_server_instance_id

    return get_server_instance_id()


def resolve_watch_mount_root(config_data: Mapping[str, Any]) -> Path | None:
    """
    Return mount root when mount-only watch-dir mode is configured.

    Enabled by ``code_analysis.file_watcher.watch_mount_root`` or
    ``CASMGR_WATCH_ROOT`` env (non-empty). Host deployments without either
    keep config-driven ``worker.watch_dirs``.
    """
    ca = config_data.get("code_analysis")
    if isinstance(ca, dict):
        fw = ca.get("file_watcher")
        if isinstance(fw, dict):
            explicit = fw.get("watch_mount_root")
            if explicit:
                return Path(str(explicit).strip())
    env_val = os.environ.get("CASMGR_WATCH_ROOT")
    if env_val is not None and str(env_val).strip():
        return Path(str(env_val).strip())
    return None


def _path_is_writable_dir(path: Path) -> bool:
    """True when ``path`` exists as a writable directory or can be created."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    if resolved.is_dir():
        return os.access(resolved, os.W_OK | os.X_OK)
    parent = resolved.parent
    try:
        if parent.is_dir():
            return os.access(parent, os.W_OK | os.X_OK)
    except OSError:
        pass
    return False


def resolve_effective_watch_mount_root(config_data: Mapping[str, Any]) -> Path | None:
    """
    Return the watch mount root used at runtime on this machine.

    When config/env point at ``/watched`` but that path is not writable (typical
    native host install with ``ProtectSystem=strict``), falls back to
    ``CASMGR_NATIVE_HOST_WATCH_ROOT`` so prepare-watch-mounts and the file watcher
    agree on the same directory.
    """
    raw = resolve_watch_mount_root(config_data)
    if raw is None:
        return None
    candidate = Path(raw)
    docker_root = Path(CASMGR_DOCKER_WATCH_ROOT)
    try:
        points_at_docker_root = candidate.resolve() == docker_root.resolve()
    except OSError:
        points_at_docker_root = candidate.as_posix().rstrip(
            "/"
        ) == docker_root.as_posix().rstrip("/")
    if points_at_docker_root and not _path_is_writable_dir(candidate):
        native = Path(CASMGR_NATIVE_HOST_WATCH_ROOT)
        logger.info(
            "watch_mount_root %s is not writable on this host; using %s",
            candidate,
            native,
        )
        return native
    return candidate


def _is_uuid4_name(name: str) -> bool:
    """Return is uuid4 name."""
    try:
        parsed = uuid.UUID(name)
    except ValueError:
        return False
    return parsed.version == 4


def _absolute_path_under_mount_root(absolute_path: str, mount_root: Path) -> bool:
    """True when ``absolute_path`` is the mount root or a subdirectory."""
    try:
        root = mount_root.resolve()
        candidate = Path(absolute_path).expanduser().resolve()
        candidate.relative_to(root)
        return True
    except (ValueError, OSError):
        root_s = normalize_path_simple(str(mount_root)).rstrip("/")
        cand_s = normalize_path_simple(absolute_path).rstrip("/")
        return cand_s == root_s or cand_s.startswith(root_s + "/")


def discover_uuid_watch_dirs(mount_root: Path) -> dict[str, Path]:
    """Map UUID4 directory names to resolved paths under ``mount_root``."""
    if not mount_root.is_dir():
        return {}
    discovered: dict[str, Path] = {}
    try:
        children = list(mount_root.iterdir())
    except OSError:
        log_fs_access_error(mount_root, "discover_uuid_watch_dirs")
        raise
    for child in children:
        if not child.is_dir():
            continue
        if not _is_uuid4_name(child.name):
            continue
        try:
            discovered[child.name] = child.resolve()
        except OSError:
            discovered[child.name] = child.absolute()
    return discovered


def build_mark_watch_dir_absent_program(
    watch_dir_id: str,
    *,
    server_instance_id: str,
) -> LogicalWriteProgramV1:
    """Soft-delete watch_dir, its projects, and their files in one logical write."""
    wid = watch_dir_id
    sid = server_instance_id
    return {
        "batches": [
            [
                (
                    "UPDATE watch_dirs SET deleted = 1 "
                    "WHERE server_instance_id = ? AND id = ?",
                    (sid, wid),
                ),
                (
                    "UPDATE projects SET deleted = 1 "
                    "WHERE watch_dir_id = ? "
                    "AND (server_instance_id IS NULL OR server_instance_id = ?)",
                    (wid, sid),
                ),
                (
                    "UPDATE files SET deleted = 1 "
                    "WHERE project_id IN ("
                    "  SELECT id FROM projects "
                    "  WHERE watch_dir_id = ? "
                    "    AND (server_instance_id IS NULL OR server_instance_id = ?)"
                    ")",
                    (wid, sid),
                ),
            ]
        ]
    }


def _fetch_db_watch_dirs(
    database: Any, server_instance_id: str
) -> dict[str, dict[str, Any]]:
    """Return fetch db watch dirs."""
    result = database.execute(
        """
        SELECT wd.id, wd.name, wd.deleted, wdp.absolute_path
        FROM watch_dirs wd
        LEFT JOIN watch_dir_paths wdp
          ON wd.server_instance_id = wdp.server_instance_id
         AND wd.id = wdp.watch_dir_id
        WHERE wd.server_instance_id = ?
        """,
        (server_instance_id,),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    rows = result.get("data", []) if isinstance(result, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        wid = str(row.get("id") or "").strip()
        if wid:
            out[wid] = row
    return out


def _register_new_watch_dir_row(
    database: Any,
    *,
    server_instance_id: str,
    watch_dir_id: str,
    absolute_path: str,
) -> None:
    """Return register new watch dir row."""
    database.execute(
        watch_dirs_insert_new_row_sql(),
        (server_instance_id, watch_dir_id, watch_dir_id, False),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    database.execute(
        """
        INSERT INTO watch_dir_paths (
            server_instance_id, watch_dir_id, absolute_path, updated_at
        )
        VALUES (?, ?, ?, julianday('now'))
        """,
        (server_instance_id, watch_dir_id, absolute_path),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )


def _activate_watch_dir_row(
    database: Any,
    *,
    server_instance_id: str,
    watch_dir_id: str,
    absolute_path: str,
) -> None:
    """Return activate watch dir row."""
    database.execute(
        """
        UPDATE watch_dirs
        SET deleted = 0, name = ?, updated_at = julianday('now')
        WHERE server_instance_id = ? AND id = ?
        """,
        (watch_dir_id, server_instance_id, watch_dir_id),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    path_update = database.execute(
        """
        UPDATE watch_dir_paths
        SET absolute_path = ?, updated_at = julianday('now')
        WHERE server_instance_id = ? AND watch_dir_id = ?
        """,
        (absolute_path, server_instance_id, watch_dir_id),
        priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
    )
    affected = 0
    if isinstance(path_update, dict):
        affected = int(path_update.get("affected_rows") or 0)
    if affected <= 0:
        database.execute(
            """
            INSERT INTO watch_dir_paths (
                server_instance_id, watch_dir_id, absolute_path, updated_at
            )
            VALUES (?, ?, ?, julianday('now'))
            """,
            (server_instance_id, watch_dir_id, absolute_path),
            priority=BACKGROUND_WORKER_DB_RPC_PRIORITY,
        )


def _restore_watch_dir_presence(
    database: Any,
    *,
    server_instance_id: str,
    watch_dir_id: str,
    watch_dir_path: Path,
) -> WatchDirSettings:
    """Return restore watch dir presence."""
    normalized = normalize_path_simple(str(watch_dir_path))
    _activate_watch_dir_row(
        database,
        server_instance_id=server_instance_id,
        watch_dir_id=watch_dir_id,
        absolute_path=normalized,
    )
    existing = load_watch_dir_settings(watch_dir_path)
    restored = WatchDirSettings(
        deleted=False,
        ignore_patterns=existing.ignore_patterns,
    )
    write_watch_dir_settings(watch_dir_path, restored)
    return restored


def _mark_watch_dir_absent(
    database: Any,
    *,
    server_instance_id: str,
    watch_dir_id: str,
) -> None:
    """Return mark watch dir absent."""
    if hasattr(database, "execute_logical_write_operation"):
        database.execute_logical_write_operation(
            build_mark_watch_dir_absent_program(
                watch_dir_id,
                server_instance_id=server_instance_id,
            )
        )
        return
    program = build_mark_watch_dir_absent_program(
        watch_dir_id,
        server_instance_id=server_instance_id,
    )
    for batch in program.get("batches", []):
        for sql, params in batch:
            database.execute(sql, params, priority=BACKGROUND_WORKER_DB_RPC_PRIORITY)


def sync_watch_dirs_from_mount(
    database: Any,
    mount_root: Path,
) -> List[WatchDirSpec]:
    """
    Synchronize DB watch_dirs registry with UUID subdirectories on disk.

    Only rows whose ``absolute_path`` lies under ``mount_root`` are soft-deleted
    when absent on disk. Host-path rows outside the mount root are untouched.

    Returns active (non-deleted, on-disk) :class:`WatchDirSpec` entries under
    ``mount_root``.
    """
    server_instance_id = _current_server_instance_id()
    mount_root = mount_root.resolve()
    on_disk = discover_uuid_watch_dirs(mount_root)
    db_rows = _fetch_db_watch_dirs(database, server_instance_id)

    on_disk_ids = set(on_disk)
    db_ids = set(db_rows)

    for wid in sorted(on_disk_ids - db_ids):
        path = on_disk[wid]
        canonical = normalize_path_simple(
            docker_watch_dir_container_path(wid, watch_root=str(mount_root))
        )
        try:
            canonical_path = Path(canonical)
        except OSError:
            canonical_path = path
        _register_new_watch_dir_row(
            database,
            server_instance_id=server_instance_id,
            watch_dir_id=wid,
            absolute_path=canonical,
        )
        settings = ensure_watch_dir_settings(
            canonical_path if canonical_path.exists() else path
        )
        logger.info(
            "Mount sync: registered new watch_dir id=%s path=%s",
            wid,
            canonical,
        )
        _ = settings

    for wid in sorted(db_ids - on_disk_ids):
        abs_path = str(db_rows.get(wid, {}).get("absolute_path") or "")
        if abs_path and not _absolute_path_under_mount_root(abs_path, mount_root):
            continue
        _mark_watch_dir_absent(
            database,
            server_instance_id=server_instance_id,
            watch_dir_id=wid,
        )
        logger.info(
            "Mount sync: watch_dir id=%s absent on disk; soft-deleted cascade", wid
        )

    for wid in sorted(on_disk_ids & db_ids):
        path = on_disk[wid]
        canonical = normalize_path_simple(
            docker_watch_dir_container_path(wid, watch_root=str(mount_root))
        )
        was_deleted = bool(db_rows.get(wid, {}).get("deleted"))
        settings = _restore_watch_dir_presence(
            database,
            server_instance_id=server_instance_id,
            watch_dir_id=wid,
            watch_dir_path=path,
        )
        if was_deleted:
            logger.info(
                "Mount sync: watch_dir id=%s reappeared; cleared deleted flag",
                wid,
            )
        _ = settings

    specs: List[WatchDirSpec] = []
    for wid in sorted(on_disk_ids):
        path = on_disk[wid]
        settings = load_watch_dir_settings(path)
        specs.append(
            WatchDirSpec(
                watch_dir=path,
                watch_dir_id=wid,
                ignore_patterns=settings.ignore_patterns,
            )
        )
    return specs
