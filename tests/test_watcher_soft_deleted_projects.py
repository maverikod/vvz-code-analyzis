"""
Watcher skips disk-discovered project roots when ``projects.deleted`` is set.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Iterator

import pytest

from code_analysis.core.database import CodeDatabase
from code_analysis.core.file_watcher_pkg.watcher_soft_deleted_projects import (
    partition_discovered_projects_by_db_soft_delete,
)
from code_analysis.core.project_discovery import discover_projects_in_directory


@pytest.fixture
def coord_db(tmp_path: Path) -> Iterator[CodeDatabase]:
    db_path = tmp_path / "wsd.db"
    driver_config = {"type": "sqlite", "config": {"path": str(db_path)}}
    original = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    db = CodeDatabase(driver_config=driver_config)
    try:
        db.sync_schema()
        yield db
    finally:
        db.close()
        if original is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original


def _create_projectid(root: Path, pid: str) -> None:
    (root / "projectid").write_text(
        json.dumps({"id": pid, "description": "wsd test"}),
        encoding="utf-8",
    )


def test_partition_excludes_soft_deleted_project_by_id(coord_db: CodeDatabase, tmp_path: Path) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    proj_a = watch / "proj_a"
    proj_b = watch / "proj_b"
    proj_a.mkdir()
    proj_b.mkdir()
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    _create_projectid(proj_a, pid_a)
    _create_projectid(proj_b, pid_b)
    coord_db._execute(
        "INSERT INTO projects (id, root_path, name, comment, deleted, updated_at) "
        "VALUES (?, ?, ?, ?, 0, julianday('now'))",
        (pid_a, str(proj_a.resolve()), "proj_a", ""),
    )
    coord_db._execute(
        "INSERT INTO projects (id, root_path, name, comment, deleted, updated_at) "
        "VALUES (?, ?, ?, ?, 1, julianday('now'))",
        (pid_b, str(proj_b.resolve()), "proj_b", ""),
    )
    coord_db._commit()

    discovered = discover_projects_in_directory(watch)
    assert len(discovered) == 2
    active, excluded = partition_discovered_projects_by_db_soft_delete(coord_db, discovered)
    assert len(active) == 1
    assert active[0].project_id == pid_a
    assert proj_b.resolve() in excluded


def test_partition_excludes_by_root_path_when_deleted_flag_on_row(
    coord_db: CodeDatabase, tmp_path: Path
) -> None:
    """If ``root_path`` matches a soft-deleted row, skip even when projectid id differs."""
    watch = tmp_path / "watch2"
    watch.mkdir()
    proj = watch / "orphan"
    proj.mkdir()
    pid_file = str(uuid.uuid4())
    pid_db = str(uuid.uuid4())
    _create_projectid(proj, pid_file)
    coord_db._execute(
        "INSERT INTO projects (id, root_path, name, comment, deleted, updated_at) "
        "VALUES (?, ?, ?, ?, 1, julianday('now'))",
        (pid_db, str(proj.resolve()), "orphan", ""),
    )
    coord_db._commit()
    discovered = discover_projects_in_directory(watch)
    assert len(discovered) == 1
    active, excluded = partition_discovered_projects_by_db_soft_delete(coord_db, discovered)
    assert active == []
    assert proj.resolve() in excluded
