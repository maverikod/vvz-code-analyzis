"""Tests for host watch-dir resolution and runtime loading."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from code_analysis.core.watch_dirs_host_resolve import (
    HostWatchDirEntry,
    collect_host_watch_entries,
    format_docker_compose_watch_volumes,
)
from code_analysis.core.watch_dirs_runtime import (
    discover_projects_runtime,
    load_watch_dir_specs_runtime,
    runtime_has_watch_dirs,
)


def _write_config(
    path: Path,
    *,
    catalog: str | None = None,
    mount_root: str | None = "/watched",
    watch_dirs: list | None = None,
) -> None:
    """Return write config."""
    fw: dict = {"watch_mount_root": mount_root} if mount_root else {}
    if catalog:
        fw["host_watch_catalog"] = catalog
    data = {
        "code_analysis": {
            "worker": {"watch_dirs": watch_dirs or []},
            "file_watcher": fw,
        }
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_collect_catalog_uuid_dir_and_config(tmp_path: Path) -> None:
    """Verify test collect catalog uuid dir and config."""
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    wid = str(uuid.uuid4())
    project_root = tmp_path / "projects" / "tools"
    project_root.mkdir(parents=True)
    (catalog / wid).symlink_to(project_root, target_is_directory=True)

    config = tmp_path / "config.json"
    _write_config(
        config,
        catalog=str(catalog),
        watch_dirs=[{"id": wid, "path": str(project_root)}],
    )

    result = collect_host_watch_entries(config)
    assert not result.errors
    assert wid in result.entries
    assert result.entries[wid].host_path.resolve() == project_root.resolve()


def test_collect_conflict_same_id_different_path(tmp_path: Path) -> None:
    """Verify test collect conflict same id different path."""
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    wid = str(uuid.uuid4())
    path_a = tmp_path / "a"
    path_b = tmp_path / "b"
    path_a.mkdir()
    path_b.mkdir()
    (catalog / wid).symlink_to(path_a, target_is_directory=True)

    config = tmp_path / "config.json"
    _write_config(
        config,
        catalog=str(catalog),
        watch_dirs=[{"id": wid, "path": str(path_b)}],
    )

    result = collect_host_watch_entries(config)
    assert result.errors


def test_runtime_mount_root_scan(tmp_path: Path) -> None:
    """Verify test runtime mount root scan."""
    mount = tmp_path / "watched"
    mount.mkdir()
    wid = str(uuid.uuid4())
    (mount / wid).mkdir()

    config = tmp_path / "config.json"
    _write_config(config, mount_root=str(mount))

    specs = load_watch_dir_specs_runtime(config)
    assert len(specs) == 1
    assert specs[0].watch_dir_id == wid
    assert runtime_has_watch_dirs(config)


def test_discover_projects_under_mount(tmp_path: Path) -> None:
    """Verify test discover projects under mount."""
    mount = tmp_path / "watched"
    mount.mkdir()
    wid = str(uuid.uuid4())
    watch_dir = mount / wid
    watch_dir.mkdir()
    project = watch_dir / "myproj"
    project.mkdir()
    (project / "projectid").write_text(
        json.dumps({"id": str(uuid.uuid4()), "description": "test"}),
        encoding="utf-8",
    )

    config = tmp_path / "config.json"
    _write_config(config, mount_root=str(mount))

    results = discover_projects_runtime(config)
    flat = [p for block in results for p in block.projects]
    assert len(flat) == 1
    assert flat[0].name == "myproj"


def test_runtime_only_mount_uuid_not_config_paths(tmp_path: Path) -> None:
    """Config paths are invisible to runtime until prepare creates mount symlinks."""
    watch_path = tmp_path / "tools"
    watch_path.mkdir()
    wid = str(uuid.uuid4())
    mount = tmp_path / "watched"
    mount.mkdir()

    config = tmp_path / "config.json"
    _write_config(
        config,
        mount_root=str(mount),
        watch_dirs=[{"id": wid, "path": str(watch_path)}],
    )

    assert load_watch_dir_specs_runtime(config) == []
    assert not runtime_has_watch_dirs(config)

    (mount / wid).symlink_to(watch_path, target_is_directory=True)
    specs = load_watch_dir_specs_runtime(config)
    assert len(specs) == 1
    assert specs[0].watch_dir_id == wid


def test_format_compose_volumes(tmp_path: Path) -> None:
    """Verify test format compose volumes."""
    wid = str(uuid.uuid4())
    host = tmp_path / "host"
    host.mkdir()
    text = format_docker_compose_watch_volumes(
        [HostWatchDirEntry(wid, host.resolve(), "config")],
    )
    assert f"{host.as_posix()}:/watched/{wid}:rw" in text
