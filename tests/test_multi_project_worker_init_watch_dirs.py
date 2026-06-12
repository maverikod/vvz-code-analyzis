"""Tests for watch dir id normalization in initialize_watch_dirs."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from code_analysis.core.file_watcher_pkg.multi_project_worker_init import (
    _resolve_project_row_absolute_path,
    _verify_and_relocate_orphaned_projects,
    _watch_dir_id_str,
)
from tests.conftest import TEST_SERVER_INSTANCE_ID
from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


def test_watch_dir_id_str_normalizes_uuid_to_same_string_as_config() -> None:
    u = UUID("550e8400-e29b-41d4-a716-446655440000")
    s = "550e8400-e29b-41d4-a716-446655440000"
    assert _watch_dir_id_str(u) == _watch_dir_id_str(s)
    assert _watch_dir_id_str(s) in {s}
    assert _watch_dir_id_str(u) in {s}


def test_watch_dir_id_str_empty_for_none() -> None:
    assert _watch_dir_id_str(None) == ""


def _write_projectid(project_dir: Path, project_id: str) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "projectid").write_text(
        json.dumps({"id": project_id, "description": "test"}, indent=4) + "\n",
        encoding="utf-8",
    )


def test_segment_root_resolves_via_watch_dir_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Watch-relative segment must not resolve against daemon CWD."""
    watch = tmp_path / "watch_root"
    project_dir = watch / "probe_project"
    pid = str(uuid.uuid4())
    wid = str(uuid.uuid4())
    _write_projectid(project_dir, pid)

    db = sqlite_inprocess_database_client(tmp_path / "segment_resolve.db")
    sid = TEST_SERVER_INSTANCE_ID
    db.insert("watch_dirs", {"server_instance_id": sid, "id": wid, "name": "data"})
    db.insert(
        "watch_dir_paths",
        {
            "server_instance_id": sid,
            "watch_dir_id": wid,
            "absolute_path": str(watch.resolve()),
        },
    )
    row = {
        "id": pid,
        "root_path": "probe_project",
        "watch_dir_id": wid,
        "name": "probe_project",
    }

    fake_cwd = tmp_path / "server_cwd"
    fake_cwd.mkdir()
    monkeypatch.chdir(fake_cwd)

    try:
        resolved = _resolve_project_row_absolute_path(row, db, require_exists=False)
        assert resolved is not None
        assert resolved.resolve() == project_dir.resolve()
    finally:
        db.disconnect()


def test_orphan_verify_skips_segment_project_under_config_watch_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Segment storage under config watch dir must not trigger orphan relocation."""
    watch = tmp_path / "watch_root"
    project_dir = watch / "probe_project"
    pid = str(uuid.uuid4())
    wid = str(uuid.uuid4())
    _write_projectid(project_dir, pid)

    db = sqlite_inprocess_database_client(tmp_path / "orphan_skip.db")
    sid = TEST_SERVER_INSTANCE_ID
    db.insert("watch_dirs", {"server_instance_id": sid, "id": wid, "name": "data"})
    db.insert(
        "watch_dir_paths",
        {
            "server_instance_id": sid,
            "watch_dir_id": wid,
            "absolute_path": str(watch.resolve()),
        },
    )
    db.insert(
        "projects",
        {
            "id": pid,
            "server_instance_id": sid,
            "root_path": "probe_project",
            "name": "probe_project",
            "watch_dir_id": wid,
        },
    )

    relocate = MagicMock(return_value=True)
    db.relocate_project_root_after_disk_move = relocate  # type: ignore[method-assign]

    fake_cwd = tmp_path / "server_cwd"
    fake_cwd.mkdir()
    monkeypatch.chdir(fake_cwd)

    try:
        _verify_and_relocate_orphaned_projects(
            db,
            {wid: watch.resolve()},
            "datetime('now')",
        )
        relocate.assert_not_called()
    finally:
        db.disconnect()
