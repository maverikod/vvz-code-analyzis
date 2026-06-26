"""Tests for relocating project root in DB when the project directory moves on disk."""

from __future__ import annotations

import os
import types
import uuid
from pathlib import Path

import pytest

from tests.sqlite_inprocess_database import sqlite_inprocess_database_client
from tests.sqlite_in_process_legacy_facade import SqliteLegacyRpcFacade
from code_analysis.core.database.projects import relocate_project_root_after_disk_move
from code_analysis.core.database_client.client import DatabaseClient


@pytest.fixture
def temp_db(tmp_path: Path) -> SqliteLegacyRpcFacade:
    """Return temp db."""
    db_path = tmp_path / "relocate.db"
    backup_dir = tmp_path / "backups"
    client = sqlite_inprocess_database_client(db_path, backup_dir=backup_dir)
    facade = SqliteLegacyRpcFacade(client)
    facade.relocate_project_root_after_disk_move = types.MethodType(
        relocate_project_root_after_disk_move, facade
    )
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    try:
        yield facade
    finally:
        facade.close()
        if original_env is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env


def test_relocate_updates_project_and_file_paths(
    temp_db: SqliteLegacyRpcFacade, tmp_path: Path
) -> None:
    """Verify test relocate updates project and file paths."""
    pid = str(uuid.uuid4())
    old_root = (tmp_path / "parent" / "myproj").resolve()
    new_root = (tmp_path / "myproj").resolve()
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    old_py = old_root / "src" / "app.py"
    old_py.parent.mkdir(parents=True)
    old_py.write_text("x=1\n", encoding="utf-8")

    file_id = str(uuid.uuid4())
    temp_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (pid, str(old_root), old_root.name),
    )
    temp_db._execute(
        "INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, "
        "has_docstring, deleted, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, julianday('now'))",
        (
            file_id,
            pid,
            "src/app.py",
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
    assert frow["path"] == "src/app.py"
    assert frow["relative_path"] == "src/app.py"


def test_relocate_noop_when_same_path(
    temp_db: SqliteLegacyRpcFacade, tmp_path: Path
) -> None:
    """Verify test relocate noop when same path."""
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
    temp_db: SqliteLegacyRpcFacade, tmp_path: Path
) -> None:
    """Verify test relocate false when new root taken."""
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


def test_database_client_relocate_same_id_new_path(tmp_path: Path) -> None:
    """DatabaseClient exposes relocate (file watcher); same UUID, path on disk moved."""
    db_path = tmp_path / "dc_relocate.db"
    client: DatabaseClient = sqlite_inprocess_database_client(db_path)
    try:
        pid = str(uuid.uuid4())
        old_root = (tmp_path / "parent" / "myproj").resolve()
        new_root = (tmp_path / "myproj").resolve()
        old_root.mkdir(parents=True)
        new_root.mkdir(parents=True)
        old_py = old_root / "src" / "app.py"
        old_py.parent.mkdir(parents=True)
        old_py.write_text("x=1\n", encoding="utf-8")

        file_id = str(uuid.uuid4())
        client.execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (pid, str(old_root), old_root.name),
        )
        client.execute(
            "INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, "
            "has_docstring, deleted, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, julianday('now'))",
            (
                file_id,
                pid,
                "src/app.py",
                "src/app.py",
                1,
                1.0,
                0,
            ),
        )

        assert client.relocate_project_root_after_disk_move(
            pid, str(old_root), str(new_root)
        )

        prow = client.execute(
            "SELECT root_path, name FROM projects WHERE id = ?", (pid,)
        )
        rows = prow.get("data", []) if isinstance(prow, dict) else []
        assert len(rows) == 1
        assert Path(rows[0]["root_path"]).resolve() == new_root
        assert rows[0]["name"] == new_root.name

        frow = client.execute(
            "SELECT path, relative_path FROM files WHERE project_id = ?", (pid,)
        )
        frows = frow.get("data", []) if isinstance(frow, dict) else []
        assert len(frows) == 1
        assert frows[0]["path"] == "src/app.py"
        assert frows[0]["relative_path"] == "src/app.py"
    finally:
        client.disconnect()
