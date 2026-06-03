"""Tests for BaseMCPCommand._resolve_project_root with watch-relative storage."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from code_analysis.core.shared_database import set_shared_database
from code_analysis.core.exceptions import ValidationError
from tests.conftest import TEST_SERVER_INSTANCE_ID
from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


@pytest.fixture
def segment_project_db(tmp_path: Path):
    """Project with watch-relative root_path segment (production storage format)."""
    watch = tmp_path / "watch_root"
    project_dir = watch / "probe_project"
    project_dir.mkdir(parents=True)

    pid = str(uuid.uuid4())
    wid = str(uuid.uuid4())

    db = sqlite_inprocess_database_client(tmp_path / "resolve_root.db")
    sid = TEST_SERVER_INSTANCE_ID
    db.insert("watch_dirs", {"server_instance_id": sid, "id": wid, "name": "tools"})
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

    set_shared_database(db)
    try:
        yield pid, project_dir, db
    finally:
        db.disconnect()


def test_resolve_project_root_watch_relative_segment(
    segment_project_db,
) -> None:
    pid, expected_root, _db = segment_project_db
    root = BaseMCPCommand._resolve_project_root(pid)
    assert root.resolve() == expected_root.resolve()


def test_resolve_project_root_rejects_unresolvable_not_cwd(
    segment_project_db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid, _expected_root, db = segment_project_db
    sid = TEST_SERVER_INSTANCE_ID
    db.delete(
        "watch_dir_paths",
        where={
            "server_instance_id": sid,
            "watch_dir_id": db.select(
                "projects", where={"server_instance_id": sid, "id": pid}
            )[0]["watch_dir_id"],
        },
    )
    db.update(
        "projects",
        where={"server_instance_id": sid, "id": pid},
        data={"root_path": "probe_project", "name": "probe_project"},
    )

    fake_cwd = tmp_path / "server_cwd"
    fake_cwd.mkdir()
    monkeypatch.chdir(fake_cwd)

    with pytest.raises(ValidationError, match="Cannot resolve absolute project root"):
        BaseMCPCommand._resolve_project_root(pid)


def test_resolve_project_root_fallback_other_watch_dir_id(
    tmp_path: Path,
) -> None:
    """Project linked to watch_dir with null path resolves via another watch_dir row."""
    watch_linked = tmp_path / "linked_watch"
    watch_local = tmp_path / "local_watch"
    project_dir = watch_local / "probe_project"
    watch_linked.mkdir()
    watch_local.mkdir()
    project_dir.mkdir(parents=True)

    wid_linked = str(uuid.uuid4())
    wid_local = str(uuid.uuid4())
    pid = str(uuid.uuid4())

    db = sqlite_inprocess_database_client(tmp_path / "cross_watch.db")
    sid = TEST_SERVER_INSTANCE_ID
    db.insert(
        "watch_dirs", {"server_instance_id": sid, "id": wid_linked, "name": "tools"}
    )
    db.insert(
        "watch_dirs", {"server_instance_id": sid, "id": wid_local, "name": "tools"}
    )
    db.insert(
        "watch_dir_paths",
        {
            "server_instance_id": sid,
            "watch_dir_id": wid_linked,
            "absolute_path": str(watch_linked.resolve()),
        },
    )
    db.insert(
        "watch_dir_paths",
        {
            "server_instance_id": sid,
            "watch_dir_id": wid_local,
            "absolute_path": str(watch_local.resolve()),
        },
    )
    db.insert(
        "projects",
        {
            "id": pid,
            "server_instance_id": sid,
            "root_path": "probe_project",
            "name": "probe_project",
            "watch_dir_id": wid_linked,
        },
    )

    set_shared_database(db)
    try:
        root = BaseMCPCommand._resolve_project_root(pid)
        assert root.resolve() == project_dir.resolve()
    finally:
        db.disconnect()


def test_resolve_project_root_rejects_missing_watch_dir_on_disk(
    tmp_path: Path,
) -> None:
    """Watch path in DB that does not exist on disk is ignored."""
    missing_watch = tmp_path / "gone_watch"
    pid = str(uuid.uuid4())
    wid = str(uuid.uuid4())

    db = sqlite_inprocess_database_client(tmp_path / "missing_watch.db")
    sid = TEST_SERVER_INSTANCE_ID
    db.insert("watch_dirs", {"server_instance_id": sid, "id": wid, "name": "tools"})
    db.insert(
        "watch_dir_paths",
        {
            "server_instance_id": sid,
            "watch_dir_id": wid,
            "absolute_path": str(missing_watch.resolve()),
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

    set_shared_database(db)
    try:
        with pytest.raises(
            ValidationError, match="Cannot resolve absolute project root"
        ):
            BaseMCPCommand._resolve_project_root(pid)
    finally:
        db.disconnect()


def test_resolve_project_root_rejects_missing_project_folder_on_disk(
    tmp_path: Path,
) -> None:
    """Existing watch dir without the project child folder does not resolve."""
    watch = tmp_path / "watch_root"
    watch.mkdir()
    pid = str(uuid.uuid4())
    wid = str(uuid.uuid4())

    db = sqlite_inprocess_database_client(tmp_path / "missing_project.db")
    sid = TEST_SERVER_INSTANCE_ID
    db.insert("watch_dirs", {"server_instance_id": sid, "id": wid, "name": "tools"})
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

    set_shared_database(db)
    try:
        with pytest.raises(
            ValidationError, match="Cannot resolve absolute project root"
        ):
            BaseMCPCommand._resolve_project_root(pid)
    finally:
        db.disconnect()


def test_open_resolve_abs_path_uses_watch_dir_not_cwd(
    segment_project_db,
) -> None:
    pid, expected_root, _db = segment_project_db
    cmd = UniversalFileOpenCommand()
    resolved = cmd._resolve_abs_path(pid, "scripts/hello.py")
    assert resolved is not None
    assert resolved.resolve() == (expected_root / "scripts" / "hello.py").resolve()
