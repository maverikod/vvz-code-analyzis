"""
Load and normalize file-watcher watch_dirs from server config.json.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

from code_analysis.core.config import ServerConfig
from code_analysis.core.storage_paths import load_raw_config
from code_analysis.core.watch_dir_access import describe_watch_dir_access

from .multi_project_worker_specs import WatchDirSpec, build_watch_dir_specs

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileWatcherRuntimeSettings:
    """Runtime file-watcher settings read from config.json."""

    watch_dir_entries: List[Dict[str, Any]]
    watch_dir_specs: List[WatchDirSpec]
    scan_interval: int
    ignore_patterns: List[str]
    enabled: bool


def parse_worker_watch_dirs_raw(
    code_analysis_config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Return validated watch_dir dicts from ``code_analysis.worker.watch_dirs``."""
    worker_config = code_analysis_config.get("worker")
    if not isinstance(worker_config, dict):
        return []

    watch_dirs_raw = worker_config.get("watch_dirs", [])
    if not isinstance(watch_dirs_raw, list):
        return []

    parsed: List[Dict[str, Any]] = []
    for wd in watch_dirs_raw:
        if isinstance(wd, dict) and "id" in wd and "path" in wd:
            parsed.append(wd)
        else:
            logger.error(
                "Invalid watch_dir format: %s. "
                "Expected: {'id': 'uuid4', 'path': '/absolute/path'}",
                wd,
            )
    return parsed


def build_file_watcher_watch_dir_entries(
    watch_dirs_config: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Normalize configured watch dirs and log accessibility warnings.

    Returns all configured entries (even when missing or unreadable).
    """
    entries: List[Dict[str, Any]] = []
    for watch_dir_config in watch_dirs_config:
        watch_dir_id = watch_dir_config["id"]
        watch_dir_path_str = watch_dir_config["path"]
        try:
            watch_dir_path = Path(watch_dir_path_str).expanduser().resolve()
        except OSError:
            watch_dir_path = Path(watch_dir_path_str).expanduser().absolute()

        issue = describe_watch_dir_access(watch_dir_path)
        if issue:
            logger.warning(
                "Watch directory not accessible (id=%s, path=%s): %s — "
                "will retry on next config sync",
                watch_dir_id,
                watch_dir_path,
                issue,
            )

        entry: Dict[str, Any] = {"id": watch_dir_id, "path": str(watch_dir_path)}
        ignore = watch_dir_config.get("ignore_patterns")
        if isinstance(ignore, list):
            entry["ignore_patterns"] = ignore
        entries.append(entry)

    return entries


def _watch_dir_specs_signature(specs: Sequence[WatchDirSpec]) -> tuple[Any, ...]:
    return tuple((s.watch_dir_id, str(s.watch_dir), s.ignore_patterns) for s in specs)


def load_file_watcher_runtime_settings(
    config_path: Path,
) -> FileWatcherRuntimeSettings:
    """Read file-watcher runtime settings from ``config.json`` on disk."""
    config_data = load_raw_config(config_path)
    code_analysis_config = config_data.get("code_analysis", {})
    if not isinstance(code_analysis_config, dict):
        code_analysis_config = {}

    _allowed = set(ServerConfig.model_fields.keys())
    server_config_dict = {
        k: v for k, v in code_analysis_config.items() if k in _allowed
    }
    server_config = ServerConfig(**server_config_dict)

    file_watcher_config = server_config.file_watcher
    if not file_watcher_config or not isinstance(file_watcher_config, dict):
        file_watcher_config = {}

    enabled = bool(file_watcher_config.get("enabled", True))
    scan_interval = int(file_watcher_config.get("scan_interval", 60))
    ignore_patterns_raw = file_watcher_config.get("ignore_patterns", [])
    ignore_patterns = (
        list(ignore_patterns_raw) if isinstance(ignore_patterns_raw, list) else []
    )

    raw_dirs = parse_worker_watch_dirs_raw(code_analysis_config)
    entries = build_file_watcher_watch_dir_entries(raw_dirs)
    specs = build_watch_dir_specs(entries)

    return FileWatcherRuntimeSettings(
        watch_dir_entries=entries,
        watch_dir_specs=specs,
        scan_interval=scan_interval,
        ignore_patterns=ignore_patterns,
        enabled=enabled,
    )


def apply_runtime_settings_to_worker(
    worker: Any,
    settings: FileWatcherRuntimeSettings,
    *,
    log_changes: bool = True,
) -> bool:
    """
    Update worker fields from freshly loaded settings.

    Returns True when watch_dir_specs changed.
    """
    old_sig = _watch_dir_specs_signature(worker.watch_dirs)
    new_sig = _watch_dir_specs_signature(settings.watch_dir_specs)

    worker.scan_interval = settings.scan_interval
    worker.ignore_patterns = list(settings.ignore_patterns)
    worker.watch_dirs = list(settings.watch_dir_specs)

    if log_changes and old_sig != new_sig:
        logger.info(
            "Watch dirs reloaded from config: %s -> %s",
            len(old_sig),
            len(new_sig),
        )
    return old_sig != new_sig
