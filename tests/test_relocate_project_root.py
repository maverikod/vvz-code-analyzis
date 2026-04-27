"""Tests for relocating project root in DB when the project directory moves on disk."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from code_analysis.core.database.base import CodeDatabase


@pytest.fixture
def temp_db(tmp_path: Path) -> CodeDatabase:
    db_path = tmp_path / "relocate.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    driver_config = {
        "type": "sqlite",
        "config": {"path": str(db_path), "backup_dir": str(backup_dir)},
    }
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    db = CodeDatabase(driver_config)
    try:
        db.sync_schema()
        yield db
        db.close()
    finally:
        if original_env is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env


def test_relocate_updates_project_and_file_paths(
    temp_db: CodeDatabase, tmp_path: Path
) -> None:
    pid = str(uuid.uuid4())
    old_root = (tmp_path / "parent" / "myproj").resolve()
    new_root = (tmp_path / "myproj").resolve()
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    old_py = old_root / "src" / "app.py"
    old_py.parent.mkdir(parents=True)
    old_py.write_text("x=1\n", encoding="utf-8")

    temp_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (pid, str(old_root), old_root.name),
    )
    temp_db._execute(
        "INSERT INTO files (project_id, path, relative_path, lines, last_modified, "
        "has_docstring, deleted, updated_at) VALUES (?, ?, ?, ?, ?, ?, 0, julianday('now'))",
        (
            pid,
            str(old_py.resolve()),
            "src/app.py",
            1,
            1.0,
            0,
        ),
    )
    temp_db._commit()

    assert temp_db.relocate_project_root_after_disk_move(
        pid, str(old_root), str(new_root)
    )

    row = temp_db._fetchone("SELECT root_path, name FROM projects WHERE id = ?", (pid,))
    assert row is not None
    assert Path(row["root_path"]).resolve() == new_root
    assert row["name"] == new_root.name

    frow = temp_db._fetchone(
        "SELECT path, relative_path FROM files WHERE project_id = ?", (pid,)
    )
    assert frow is not None
    assert Path(frow["path"]).resolve() == (new_root / "src" / "app.py").resolve()
    assert frow["relative_path"] == "src/app.py"


def test_relocate_noop_when_same_path(temp_db: CodeDatabase, tmp_path: Path) -> None:
    pid = str(uuid.uuid4())
    root = (tmp_path / "r").resolve()
    root.mkdir()
    temp_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (pid, str(root), root.name),
    )
    temp_db._commit()
    assert temp_db.relocate_project_root_after_disk_move(pid, str(root), str(root))


def test_relocate_false_when_new_root_taken(
    temp_db: CodeDatabase, tmp_path: Path
) -> None:
    a = str(uuid.uuid4())
    b = str(uuid.uuid4())
    r1 = (tmp_path / "p1").resolve()
    r2 = (tmp_path / "p2").resolve()
    r1.mkdir()
    r2.mkdir()
    temp_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (a, str(r1), r1.name),
    )
    temp_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (b, str(r2), r2.name),
    )
    temp_db._commit()
    assert not temp_db.relocate_project_root_after_disk_move(a, str(r1), str(r2))
