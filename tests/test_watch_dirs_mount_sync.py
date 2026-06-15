"""Tests for mount-root watch directory synchronization."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from code_analysis.core.file_watcher_pkg.watch_dirs_mount_sync import (
    build_mark_watch_dir_absent_program,
    discover_uuid_watch_dirs,
    sync_watch_dirs_from_mount,
)
from code_analysis.core.watch_dir_settings import (
    DEFAULT_WATCH_DIR_IGNORE_PATTERNS,
    WATCH_DIR_SETTINGS_FILENAME,
    WatchDirSettings,
    ensure_watch_dir_settings,
    load_watch_dir_settings,
    write_watch_dir_settings,
)
from tests.conftest import TEST_SERVER_INSTANCE_ID
from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


def _row_count(client, sql: str, params: tuple = ()) -> int:
    rows = client.execute(sql, params)
    data = rows.get("data", []) if isinstance(rows, dict) else []
    if not data:
        return 0
    row = data[0]
    if isinstance(row, dict):
        return int(next(iter(row.values())))
    return int(row[0])


def _insert_watch_dir(client, wid: str, path: str, *, deleted: int = 0) -> None:
    from code_analysis.core.server_instance import get_server_instance_id

    sid = get_server_instance_id()
    client.execute(
        """
        INSERT INTO watch_dirs (server_instance_id, id, name, deleted, updated_at)
        VALUES (?, ?, ?, ?, julianday('now'))
        """,
        (sid, wid, wid, deleted),
    )
    client.execute(
        """
        INSERT INTO watch_dir_paths (server_instance_id, watch_dir_id, absolute_path, updated_at)
        VALUES (?, ?, ?, julianday('now'))
        """,
        (sid, wid, path),
    )


def _insert_project(
    client,
    *,
    project_id: str,
    watch_dir_id: str,
    deleted: int = 0,
) -> None:
    from code_analysis.core.server_instance import get_server_instance_id

    sid = get_server_instance_id()
    client.execute(
        """
        INSERT INTO projects (
            id, server_instance_id, root_path, name, watch_dir_id, deleted, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, julianday('now'))
        """,
        (
            project_id,
            sid,
            f"seg/{project_id}",
            "test-project",
            watch_dir_id,
            deleted,
        ),
    )


@pytest.fixture
def db_client(tmp_path: Path):
    client = sqlite_inprocess_database_client(tmp_path / "test.db")
    yield client
    client.disconnect()


def test_discover_uuid_dirs_ignores_non_uuid(tmp_path: Path) -> None:
    mount = tmp_path / "watched"
    mount.mkdir()
    wid = str(uuid.uuid4())
    (mount / wid).mkdir()
    (mount / "not-a-uuid").mkdir()
    (mount / "11111111-1111-1111-1111-111111111111").mkdir()

    found = discover_uuid_watch_dirs(mount)
    assert wid in found
    assert "not-a-uuid" not in found
    assert "11111111-1111-1111-1111-111111111111" not in found


def test_resolve_effective_watch_mount_root_native_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from code_analysis.core.file_watcher_pkg.watch_dirs_mount_sync import (
        resolve_effective_watch_mount_root,
    )
    from code_analysis.core.constants import CASMGR_NATIVE_HOST_WATCH_ROOT

    # Simulate config pointing at /watched while only tmp_path is writable.
    monkeypatch.setenv("CASMGR_WATCH_ROOT", str(tmp_path / "not-watched-root"))
    cfg = {"code_analysis": {"file_watcher": {"watch_mount_root": "/watched"}}}
    effective = resolve_effective_watch_mount_root(cfg)
    assert effective == Path(CASMGR_NATIVE_HOST_WATCH_ROOT)


def test_new_dir_inserts_db_and_creates_settings(db_client, tmp_path: Path) -> None:
    mount = tmp_path / "watched"
    mount.mkdir()
    wid = str(uuid.uuid4())
    watch_path = mount / wid
    watch_path.mkdir()

    specs = sync_watch_dirs_from_mount(db_client, mount)
    assert len(specs) == 1
    assert specs[0].watch_dir_id == wid

    settings_file = watch_path / WATCH_DIR_SETTINGS_FILENAME
    assert settings_file.is_file()
    loaded = json.loads(settings_file.read_text(encoding="utf-8"))
    assert loaded["deleted"] is False
    assert loaded["ignore_patterns"] == DEFAULT_WATCH_DIR_IGNORE_PATTERNS

    n = _row_count(
        db_client,
        "SELECT COUNT(*) AS c FROM watch_dirs WHERE id = ? AND deleted = 0",
        (wid,),
    )
    assert n == 1


def test_absent_dir_soft_deletes_watch_dir_and_projects(
    db_client, tmp_path: Path
) -> None:
    from code_analysis.core.server_instance import get_server_instance_id
    from code_analysis.core.file_watcher_pkg.watch_dirs_mount_sync import (
        _fetch_db_watch_dirs,
    )

    mount = tmp_path / "watched"
    mount.mkdir()
    wid = str(uuid.uuid4())
    canonical = str((mount / wid).resolve())
    _insert_watch_dir(db_client, wid, canonical, deleted=0)
    pid = str(uuid.uuid4())
    _insert_project(db_client, project_id=pid, watch_dir_id=wid, deleted=0)

    sid = get_server_instance_id()
    assert wid in _fetch_db_watch_dirs(db_client, sid)
    on_disk = discover_uuid_watch_dirs(mount)
    assert wid not in on_disk

    specs = sync_watch_dirs_from_mount(db_client, mount)
    assert specs == []

    assert (
        _row_count(
            db_client,
            "SELECT deleted AS c FROM watch_dirs WHERE id = ?",
            (wid,),
        )
        == 1
    )
    assert (
        _row_count(
            db_client,
            "SELECT deleted AS c FROM projects WHERE id = ?",
            (pid,),
        )
        == 1
    )


def test_mark_absent_program_includes_files_update() -> None:
    wid = str(uuid.uuid4())
    sid = TEST_SERVER_INSTANCE_ID
    program = build_mark_watch_dir_absent_program(wid, server_instance_id=sid)
    sqls = [pair[0] for batch in program["batches"] for pair in batch]
    assert any("UPDATE watch_dirs SET deleted = 1" in s for s in sqls)
    assert any("UPDATE projects SET deleted = 1" in s for s in sqls)
    assert any("UPDATE files SET deleted = 1" in s for s in sqls)


def test_reappear_clears_watch_dir_deleted_projects_stay_deleted(
    db_client, tmp_path: Path
) -> None:
    mount = tmp_path / "watched"
    mount.mkdir()
    wid = str(uuid.uuid4())
    watch_path = mount / wid
    canonical = str(watch_path.resolve())
    _insert_watch_dir(db_client, wid, canonical, deleted=1)
    pid = str(uuid.uuid4())
    _insert_project(db_client, project_id=pid, watch_dir_id=wid, deleted=1)

    watch_path.mkdir()
    write_watch_dir_settings(
        watch_path,
        WatchDirSettings(deleted=True, ignore_patterns=("**/custom/**",)),
    )

    specs = sync_watch_dirs_from_mount(db_client, mount)
    assert len(specs) == 1
    assert specs[0].ignore_patterns == ("**/custom/**",)

    settings = load_watch_dir_settings(watch_path)
    assert settings.deleted is False

    assert (
        _row_count(
            db_client,
            "SELECT deleted AS c FROM watch_dirs WHERE id = ?",
            (wid,),
        )
        == 0
    )
    assert (
        _row_count(
            db_client,
            "SELECT deleted AS c FROM projects WHERE id = ?",
            (pid,),
        )
        == 1
    )


def test_settings_round_trip_ignore_patterns(tmp_path: Path) -> None:
    watch_dir = tmp_path / "wd"
    watch_dir.mkdir()
    custom = ("**/only-this/**", "**/other/**")
    write_watch_dir_settings(
        watch_dir,
        WatchDirSettings(deleted=False, ignore_patterns=custom),
    )
    loaded = load_watch_dir_settings(watch_dir)
    assert loaded.ignore_patterns == custom

    ensured = ensure_watch_dir_settings(watch_dir)
    assert ensured.ignore_patterns == custom
