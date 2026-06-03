"""Tests for server_instance_id partition on watch_dirs and projects."""

from __future__ import annotations

import uuid
from pathlib import Path

from code_analysis.core.database import watch_dirs_partition as watch_dirs_partition_mod
from tests.conftest import TEST_SERVER_INSTANCE_ID
from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


def test_watch_dirs_partition_hides_other_instance_rows(tmp_path: Path) -> None:
    """Rows for another server_instance_id are invisible to current instance queries."""
    other_sid = str(uuid.uuid4())
    wid = str(uuid.uuid4())
    db = sqlite_inprocess_database_client(tmp_path / "partition.db")

    db.insert(
        "watch_dirs",
        {"server_instance_id": other_sid, "id": wid, "name": "other"},
    )
    db.insert(
        "watch_dir_paths",
        {
            "server_instance_id": other_sid,
            "watch_dir_id": wid,
            "absolute_path": "/tmp/other-watch",
        },
    )

    db.insert(
        "watch_dirs",
        {
            "server_instance_id": TEST_SERVER_INSTANCE_ID,
            "id": wid,
            "name": "mine",
        },
    )
    db.insert(
        "watch_dir_paths",
        {
            "server_instance_id": TEST_SERVER_INSTANCE_ID,
            "watch_dir_id": wid,
            "absolute_path": "/tmp/my-watch",
        },
    )

    sid = watch_dirs_partition_mod.current_server_instance_id()
    assert sid == TEST_SERVER_INSTANCE_ID

    rows = db.select(
        "watch_dirs",
        where={"server_instance_id": sid},
        columns=["id", "name"],
    )
    assert len(rows) == 1
    assert rows[0]["name"] == "mine"

    path_row = db.select(
        "watch_dir_paths",
        where={"server_instance_id": sid, "watch_dir_id": wid},
        columns=["absolute_path"],
    )
    assert path_row[0]["absolute_path"] == "/tmp/my-watch"
    db.disconnect()
