"""
Resolve host-side watch directories from catalog root, symlinks, and config.

Used by ``scripts/casmgr-prepare-watch-mounts.py`` before container bind mounts
or host staging symlinks under ``watch_mount_root``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from code_analysis.core.file_watcher_pkg.watch_dirs_mount_sync import _is_uuid4_name
from code_analysis.core.storage_paths import load_raw_config
from code_analysis.core.watch_dirs_from_config import (
    normalize_watch_dir_configs,
    resolve_watch_dir_path,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HostWatchDirEntry:
    """One watch directory on the host before staging / bind-mount."""

    watch_dir_id: str
    host_path: Path
    source: str  # ``catalog`` | ``config``


@dataclass
class HostWatchDirCollectResult:
    """Merged host watch-dir map plus non-fatal collection errors."""

    entries: Dict[str, HostWatchDirEntry] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


def host_watch_catalog_from_config(config_data: Mapping[str, Any]) -> Optional[Path]:
    """Return ``file_watcher.host_watch_catalog`` when configured."""
    ca = config_data.get("code_analysis")
    if not isinstance(ca, dict):
        return None
    fw = ca.get("file_watcher")
    if not isinstance(fw, dict):
        return None
    raw = fw.get("host_watch_catalog")
    if not raw:
        return None
    return Path(str(raw).strip()).expanduser()


def _worker_watch_dirs_raw(config_data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    worker_config = config_data.get("code_analysis", {})
    if not isinstance(worker_config, dict):
        worker_config = {}
    worker = worker_config.get("worker")
    if not isinstance(worker, dict):
        return []
    raw = worker.get("watch_dirs", [])
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and "id" in item and "path" in item:
            out.append(item)
    return out


def _resolve_existing_dir(path: Path) -> Optional[Path]:
    try:
        resolved = path.resolve()
    except OSError as exc:
        logger.warning("Cannot resolve watch path %s: %s", path, exc)
        return None
    if not resolved.is_dir():
        logger.warning("Watch path is not a directory: %s", resolved)
        return None
    return resolved


def _add_entry(
    result: HostWatchDirCollectResult,
    *,
    watch_dir_id: str,
    host_path: Path,
    source: str,
) -> None:
    wid = watch_dir_id.strip()
    if not wid:
        result.errors.append(f"Empty watch_dir id from {source}")
        return
    existing = result.entries.get(wid)
    if existing is not None:
        try:
            same = existing.host_path.resolve() == host_path.resolve()
        except OSError:
            same = str(existing.host_path) == str(host_path)
        if not same:
            result.errors.append(
                f"Watch dir id {wid!r} conflict: {existing.source}={existing.host_path!r} "
                f"vs {source}={host_path!r}"
            )
        return
    result.entries[wid] = HostWatchDirEntry(
        watch_dir_id=wid,
        host_path=host_path,
        source=source,
    )


def _scan_host_watch_catalog(
    catalog_root: Path,
    result: HostWatchDirCollectResult,
    *,
    config_path_by_resolved: Dict[Path, str],
) -> None:
    if not catalog_root.is_dir():
        result.errors.append(f"host_watch_catalog is not a directory: {catalog_root}")
        return
    try:
        children = sorted(catalog_root.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        result.errors.append(f"Cannot read host_watch_catalog {catalog_root}: {exc}")
        return

    for child in children:
        if not (child.is_dir() or child.is_symlink()):
            continue
        resolved = _resolve_existing_dir(child)
        if resolved is None:
            result.errors.append(
                f"Catalog entry {child.name!r} under {catalog_root} is not a directory"
            )
            continue
        if _is_uuid4_name(child.name):
            _add_entry(
                result,
                watch_dir_id=child.name,
                host_path=resolved,
                source="catalog",
            )
            continue
        wid = config_path_by_resolved.get(resolved)
        if wid:
            _add_entry(
                result,
                watch_dir_id=wid,
                host_path=resolved,
                source="catalog",
            )


def collect_host_watch_entries(config_path: Path) -> HostWatchDirCollectResult:
    """
    Merge watch directories from host catalog, symlinks, and config.

    Catalog rules (``file_watcher.host_watch_catalog``):

    - Immediate child named UUID4 (directory or symlink to directory) → id = name.
    - Other directory/symlink children → included when ``worker.watch_dirs`` lists
      the same resolved host path (id from config).

    Config rules (``code_analysis.worker.watch_dirs``):

    - Each ``{id, path}`` adds or confirms an entry; path resolved relative to
      the config file directory when relative.

    Conflicting ids or paths append human-readable messages to ``errors`` and skip
    the conflicting add.
    """
    config_path = config_path.resolve()
    config_data = load_raw_config(config_path)
    result = HostWatchDirCollectResult()

    normalized = normalize_watch_dir_configs(
        _worker_watch_dirs_raw(config_data),
        config_dir=config_path.parent,
    )
    config_path_by_resolved: Dict[Path, str] = {}
    for item in normalized:
        wid = str(item["id"]).strip()
        try:
            resolved = resolve_watch_dir_path(
                str(item["path"]), config_dir=config_path.parent
            ).resolve()
        except OSError:
            resolved = resolve_watch_dir_path(
                str(item["path"]), config_dir=config_path.parent
            )
        if resolved.is_dir():
            if (
                resolved in config_path_by_resolved
                and config_path_by_resolved[resolved] != wid
            ):
                result.errors.append(
                    f"Config maps two ids to the same path {resolved!r}: "
                    f"{config_path_by_resolved[resolved]!r} and {wid!r}"
                )
            else:
                config_path_by_resolved[resolved] = wid

    catalog = host_watch_catalog_from_config(config_data)
    if catalog is not None:
        catalog_resolved = catalog.expanduser()
        if not catalog_resolved.is_absolute():
            catalog_resolved = (config_path.parent / catalog_resolved).resolve()
        _scan_host_watch_catalog(
            catalog_resolved,
            result,
            config_path_by_resolved=config_path_by_resolved,
        )

    for item in normalized:
        wid = str(item["id"]).strip()
        path = resolve_watch_dir_path(str(item["path"]), config_dir=config_path.parent)
        resolved = _resolve_existing_dir(path)
        if resolved is None:
            result.errors.append(
                f"Config watch_dir {wid!r} path does not exist or is not a directory: {path}"
            )
            continue
        _add_entry(
            result,
            watch_dir_id=wid,
            host_path=resolved,
            source="config",
        )

    return result


def format_docker_compose_watch_volumes(
    entries: Sequence[HostWatchDirEntry],
    *,
    container_watch_root: str = "/watched",
) -> str:
    """Return a compose fragment: extra ``volumes`` lines for casmgr-server."""
    root = container_watch_root.rstrip("/")
    lines = ["services:", "  casmgr-server:", "    volumes:"]
    for entry in sorted(entries, key=lambda e: e.watch_dir_id):
        host = entry.host_path.as_posix()
        target = f"{root}/{entry.watch_dir_id}"
        lines.append(f"      - {host}:{target}:rw")
    return "\n".join(lines) + "\n"
