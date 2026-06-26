"""
Load worker watch directories from server config and discover projects on disk.

Uses the same config shape and discovery rules as the file watcher
(``discover_projects_in_directory``): only ``watch_dir/<subdir>/projectid``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .file_watcher_pkg.multi_project_worker_specs import (
    WatchDirSpec,
    build_watch_dir_specs,
)
from .project_discovery import ProjectRoot, discover_projects_in_directory
from .storage_paths import load_raw_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DiscoveredProjectOnDisk:
    """One project found under a configured watch directory."""

    watch_dir_id: str
    watch_dir_path: str
    project_id: str
    name: str
    root_path: str
    root_path_absolute: str
    description: str
    deleted: bool = False
    processing_paused: bool = False


def discovered_project_to_list_row(item: DiscoveredProjectOnDisk) -> Dict[str, Any]:
    """Map disk discovery row to ``list_projects`` API project dict."""
    return {
        "id": item.project_id,
        "watch_dir": item.watch_dir_path,
        "name": item.name,
        "root_path": item.root_path,
        "comment": item.description or None,
        "watch_dir_id": item.watch_dir_id,
        "processing_paused": item.processing_paused,
        "deleted": item.deleted,
        "updated_at": None,
    }


@dataclass(frozen=True, slots=True)
class WatchDirDiscoveryResult:
    """Discovery outcome for one configured watch directory."""

    watch_dir_id: str
    absolute_path: str
    exists: bool
    projects: tuple[DiscoveredProjectOnDisk, ...]


def _worker_watch_dirs_raw(config_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return ``code_analysis.worker.watch_dirs`` entries from parsed config."""
    worker_config = config_data.get("code_analysis", {}).get("worker", {})
    if not isinstance(worker_config, dict):
        return []
    raw = worker_config.get("watch_dirs", [])
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and "id" in item and "path" in item:
            out.append(item)
        else:
            logger.warning(
                "Skipping invalid watch_dir entry in config (expected id+path dict): %r",
                item,
            )
    return out


def resolve_watch_dir_path(path_str: str, *, config_dir: Path) -> Path:
    """Resolve a watch directory path from config (absolute or relative to config dir)."""
    raw = Path(path_str).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    return (config_dir / raw).resolve()


def normalize_watch_dir_configs(
    watch_dirs_raw: Sequence[Dict[str, Any]],
    *,
    config_dir: Path,
) -> List[Dict[str, Any]]:
    """Build watch-dir dicts with resolved absolute ``path`` strings for spec builder."""
    normalized: List[Dict[str, Any]] = []
    for item in watch_dirs_raw:
        watch_dir_id = str(item["id"]).strip()
        resolved = resolve_watch_dir_path(str(item["path"]), config_dir=config_dir)
        entry: Dict[str, Any] = {
            "id": watch_dir_id,
            "path": str(resolved),
        }
        raw_ignore = item.get("ignore_patterns")
        if isinstance(raw_ignore, (list, tuple)):
            entry["ignore_patterns"] = [str(p) for p in raw_ignore if p]
        normalized.append(entry)
    return normalized


def load_watch_dir_specs_from_config(
    config_path: Path,
) -> List[WatchDirSpec]:
    """Load ``WatchDirSpec`` list from ``config_path`` (no database)."""
    config_path = config_path.resolve()
    config_data = load_raw_config(config_path)
    raw = _worker_watch_dirs_raw(config_data)
    if not raw:
        return []
    normalized = normalize_watch_dir_configs(raw, config_dir=config_path.parent)
    return build_watch_dir_specs(normalized)


def _project_to_disk_entry(
    spec: WatchDirSpec,
    project: ProjectRoot,
) -> DiscoveredProjectOnDisk:
    """Return project to disk entry."""
    from .project_resolution import load_project_info

    root_abs = project.root_path.resolve()
    info = load_project_info(root_abs)
    return DiscoveredProjectOnDisk(
        watch_dir_id=spec.watch_dir_id,
        watch_dir_path=str(spec.watch_dir.resolve()),
        project_id=info.project_id,
        name=root_abs.name,
        root_path=root_abs.name,
        root_path_absolute=str(root_abs),
        description=info.description,
        deleted=info.deleted,
        processing_paused=info.processing_paused,
    )


def discover_projects_for_watch_specs(
    specs: Sequence[WatchDirSpec],
    *,
    watch_dir_id: Optional[str] = None,
) -> List[WatchDirDiscoveryResult]:
    """Discover projects on disk for each watch-dir spec (no database).

    Args:
        specs: Watch directory specs (typically from ``load_watch_dir_specs_from_config``).
        watch_dir_id: When set, only scan the matching watch directory id.

    Returns:
        One ``WatchDirDiscoveryResult`` per spec (after optional id filter).
    """
    filter_id = (watch_dir_id or "").strip() or None
    results: List[WatchDirDiscoveryResult] = []
    for spec in specs:
        if filter_id is not None and spec.watch_dir_id != filter_id:
            continue
        watch_path = spec.watch_dir.resolve()
        exists = watch_path.exists() and watch_path.is_dir()
        projects: List[DiscoveredProjectOnDisk] = []
        if exists:
            discovered = discover_projects_in_directory(watch_path)
            projects = [_project_to_disk_entry(spec, p) for p in discovered]
        results.append(
            WatchDirDiscoveryResult(
                watch_dir_id=spec.watch_dir_id,
                absolute_path=str(watch_path),
                exists=exists,
                projects=tuple(projects),
            )
        )
    return results


def discover_projects_from_config(
    config_path: Path,
    *,
    watch_dir_id: Optional[str] = None,
) -> List[WatchDirDiscoveryResult]:
    """Load watch dirs from config and discover immediate-child projects on disk."""
    specs = load_watch_dir_specs_from_config(config_path)
    return discover_projects_for_watch_specs(specs, watch_dir_id=watch_dir_id)


def flatten_discovered_projects(
    watch_results: Sequence[WatchDirDiscoveryResult],
) -> List[DiscoveredProjectOnDisk]:
    """Return a flat list of all discovered projects."""
    flat: List[DiscoveredProjectOnDisk] = []
    for block in watch_results:
        flat.extend(block.projects)
    return flat
