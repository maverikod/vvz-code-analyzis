"""Tests for file watcher config reload from config.json."""

from __future__ import annotations

import json
from pathlib import Path

from code_analysis.core.file_watcher_pkg.multi_project_worker_specs import (
    WatchDirSpec,
)
from code_analysis.core.file_watcher_pkg.watch_dirs_config import (
    apply_runtime_settings_to_worker,
    load_file_watcher_runtime_settings,
    parse_worker_watch_dirs_raw,
)


def _minimal_config(watch_dirs: list) -> dict:
    return {
        "code_analysis": {
            "worker": {
                "enabled": True,
                "watch_dirs": watch_dirs,
            },
            "file_watcher": {
                "enabled": True,
                "scan_interval": 45,
                "ignore_patterns": ["*.tmp"],
            },
        }
    }


def test_parse_worker_watch_dirs_raw_validates_format() -> None:
    cfg = {
        "worker": {
            "watch_dirs": [
                {"id": "a", "path": "/tmp/a"},
                "bad-entry",
                {"id": "b", "path": "/tmp/b"},
            ]
        }
    }
    parsed = parse_worker_watch_dirs_raw(cfg)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "a"


def test_load_file_watcher_runtime_settings(tmp_path: Path) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            _minimal_config([{"id": "wd-1", "path": str(watch)}]),
        ),
        encoding="utf-8",
    )

    settings = load_file_watcher_runtime_settings(config_path)
    assert settings.enabled is True
    assert settings.scan_interval == 45
    assert settings.ignore_patterns == ["*.tmp"]
    assert len(settings.watch_dir_specs) == 1
    assert settings.watch_dir_specs[0].watch_dir_id == "wd-1"


def test_load_file_watcher_runtime_settings_empty_watch_dirs(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(_minimal_config([])), encoding="utf-8")

    settings = load_file_watcher_runtime_settings(config_path)
    assert settings.watch_dir_specs == []


def test_apply_runtime_settings_to_worker_updates_specs() -> None:
    class _Worker:
        watch_dirs = [
            WatchDirSpec(
                watch_dir=Path("/old"),
                watch_dir_id="old",
            )
        ]
        scan_interval = 60
        ignore_patterns: list[str] = []

    worker = _Worker()
    watch = Path("/new")
    from code_analysis.core.file_watcher_pkg.watch_dirs_config import (
        FileWatcherRuntimeSettings,
    )

    settings = FileWatcherRuntimeSettings(
        watch_dir_entries=[{"id": "new", "path": str(watch)}],
        watch_dir_specs=[
            WatchDirSpec(watch_dir=watch, watch_dir_id="new"),
        ],
        scan_interval=30,
        ignore_patterns=["*.log"],
        enabled=True,
    )
    changed = apply_runtime_settings_to_worker(worker, settings)
    assert changed is True
    assert worker.scan_interval == 30
    assert worker.ignore_patterns == ["*.log"]
    assert worker.watch_dirs[0].watch_dir_id == "new"
