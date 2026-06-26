"""
Tests for list_projects disk discovery helpers (watch_dirs_from_config).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from code_analysis.core.watch_dirs_from_config import (
    discover_projects_for_watch_specs,
    discovered_project_to_list_row,
    load_watch_dir_specs_from_config,
)
from code_analysis.core.file_watcher_pkg.multi_project_worker_specs import WatchDirSpec


def _write_config(tmp_path: Path, watch_dirs: list[dict]) -> Path:
    """Return write config."""
    cfg = {
        "code_analysis": {
            "worker": {
                "watch_dirs": watch_dirs,
            }
        }
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(cfg), encoding="utf-8")
    return config_path


def _write_projectid(project_dir: Path, project_id: str, **extra: object) -> None:
    """Return write projectid."""
    project_dir.mkdir(parents=True, exist_ok=True)
    payload: dict = {"id": project_id, "description": "test project", **extra}
    (project_dir / "projectid").write_text(
        json.dumps(payload, indent=4) + "\n",
        encoding="utf-8",
    )


def test_load_watch_dir_specs_resolves_relative_paths(tmp_path: Path) -> None:
    """Verify test load watch dir specs resolves relative paths."""
    watch_root = tmp_path / "watched"
    watch_root.mkdir()
    wid = str(uuid.uuid4())
    config_path = _write_config(
        tmp_path,
        [{"id": wid, "path": "watched"}],
    )
    specs = load_watch_dir_specs_from_config(config_path)
    assert len(specs) == 1
    assert specs[0].watch_dir_id == wid
    assert specs[0].watch_dir == watch_root.resolve()


def test_discover_immediate_child_projects_only(tmp_path: Path) -> None:
    """Verify test discover immediate child projects only."""
    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    _write_projectid(watch_root / "proj_a", pid_a)
    _write_projectid(watch_root / "nested" / "proj_b", pid_b)

    spec = WatchDirSpec(watch_dir=watch_root, watch_dir_id=str(uuid.uuid4()))
    results = discover_projects_for_watch_specs([spec])
    assert len(results) == 1
    assert results[0].exists is True
    assert len(results[0].projects) == 1
    assert results[0].projects[0].project_id == pid_a
    assert results[0].projects[0].watch_dir_id == spec.watch_dir_id


def test_discover_reads_projectid_flags(tmp_path: Path) -> None:
    """Verify test discover reads projectid flags."""
    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    pid = str(uuid.uuid4())
    _write_projectid(
        watch_root / "paused",
        pid,
        deleted=True,
        processing_paused=True,
    )
    spec = WatchDirSpec(watch_dir=watch_root, watch_dir_id=str(uuid.uuid4()))
    item = discover_projects_for_watch_specs([spec])[0].projects[0]
    assert item.deleted is True
    assert item.processing_paused is True
    row = discovered_project_to_list_row(item)
    assert row["deleted"] is True
    assert row["processing_paused"] is True
    assert row["updated_at"] is None


def test_discover_skips_missing_watch_dir(tmp_path: Path) -> None:
    """Verify test discover skips missing watch dir."""
    missing = tmp_path / "missing"
    spec = WatchDirSpec(watch_dir=missing, watch_dir_id=str(uuid.uuid4()))
    results = discover_projects_for_watch_specs([spec])
    assert len(results) == 1
    assert results[0].exists is False
    assert results[0].projects == ()
