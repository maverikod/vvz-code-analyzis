"""
Runtime watch-directory resolution (mount root only).

The server never reads ``worker.watch_dirs`` paths directly. Host
``casmgr-prepare-watch-mounts`` materializes catalog + config as UUID4 children
under ``watch_mount_root``; runtime scans that directory only.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional

from code_analysis.core.file_watcher_pkg.multi_project_worker_specs import WatchDirSpec
from code_analysis.core.file_watcher_pkg.watch_dirs_mount_sync import (
    discover_uuid_watch_dirs,
    resolve_effective_watch_mount_root,
    sync_watch_dirs_from_mount,
)
from code_analysis.core.storage_paths import load_raw_config
from code_analysis.core.watch_dir_settings import load_watch_dir_settings
from code_analysis.core.watch_dirs_from_config import (
    discover_project_candidates_for_watch_specs,
    discover_projects_for_watch_specs,
)

logger = logging.getLogger(__name__)


def resolve_runtime_watch_mount_root(config_path: Path) -> Path | None:
    """Return effective mount root from config (native-host ``/watched`` remap included)."""
    config_path = config_path.resolve()
    config_data = load_raw_config(config_path)
    return resolve_effective_watch_mount_root(config_data)


def mount_root_mode_active(config_path: Path) -> bool:
    """True when ``watch_mount_root`` / ``CASMGR_WATCH_ROOT`` is configured."""
    return resolve_runtime_watch_mount_root(config_path) is not None


def load_watch_dir_specs_from_mount(
    mount_root: Path,
    *,
    database: Any | None = None,
) -> List[WatchDirSpec]:
    """
    Load watch specs from UUID4 direct children of ``mount_root``.

    When ``database`` is set, runs ``sync_watch_dirs_from_mount`` (watcher path).
    """
    mount_root = mount_root.resolve()
    if not mount_root.is_dir():
        return []

    if database is not None:
        return sync_watch_dirs_from_mount(database, mount_root)

    on_disk = discover_uuid_watch_dirs(mount_root)
    specs: List[WatchDirSpec] = []
    for wid in sorted(on_disk):
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


def load_watch_dir_specs_runtime(
    config_path: Path,
    *,
    database: Any | None = None,
) -> List[WatchDirSpec]:
    """
    Watch specs for runtime: UUID4 children of ``watch_mount_root`` only.

    ``worker.watch_dirs`` in config is host-only input for ``casmgr-prepare-watch-mounts``.
    """
    config_path = config_path.resolve()
    mount_root = resolve_runtime_watch_mount_root(config_path)
    if mount_root is None:
        logger.error(
            "file_watcher.watch_mount_root (or CASMGR_WATCH_ROOT) is required; "
            "worker.watch_dirs is applied by casmgr-prepare-watch-mounts on the host"
        )
        return []
    if not mount_root.is_dir():
        logger.error("watch_mount_root is not a directory: %s", mount_root)
        return []
    return load_watch_dir_specs_from_mount(mount_root, database=database)


def discover_projects_runtime(
    config_path: Path,
    *,
    database: Any | None = None,
    watch_dir_id: Optional[str] = None,
) -> List:
    """Discover projects under mounted UUID4 watch directories."""
    specs = load_watch_dir_specs_runtime(config_path, database=database)
    return discover_projects_for_watch_specs(specs, watch_dir_id=watch_dir_id)


def discover_project_candidates_runtime(
    config_path: Path,
    *,
    database: Any | None = None,
    watch_dir_id: Optional[str] = None,
) -> List:
    """Cheap (no-walk) candidate discovery under mounted UUID4 watch directories.

    Used by the ``list_projects`` paginated fast path only; other runtime
    callers keep using :func:`discover_projects_runtime` unchanged.
    """
    specs = load_watch_dir_specs_runtime(config_path, database=database)
    return discover_project_candidates_for_watch_specs(specs, watch_dir_id=watch_dir_id)


def runtime_has_watch_dirs(config_path: Path) -> bool:
    """True when ``watch_mount_root`` contains at least one UUID4 watch directory."""
    mount_root = resolve_runtime_watch_mount_root(config_path)
    if mount_root is None or not mount_root.is_dir():
        return False
    return bool(discover_uuid_watch_dirs(mount_root))
