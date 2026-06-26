"""Tests for runtime file locks and advisory project lock commands."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from code_analysis.commands.project_file_advisory_lock_batch_command import (
    ProjectFileAdvisoryLockBatchCommand,
)
from code_analysis.core.client_sessions import ensure_client_session_tables
from code_analysis.core.file_lock import (
    acquire_persistent_file_lock,
    release_persistent_file_lock,
)
from code_analysis.core.runtime_lock_sessions import (
    acquire_file_advisory_lease,
    ensure_runtime_lock_tables,
    get_file_advisory_lock_status,
    register_runtime_session,
    release_file_advisory_lease,
)


class FakeDatabase:
    """Represent FakeDatabase."""

    def __init__(self, root: Path) -> None:
        """Initialize the instance."""
        self.root = root
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.execute("PRAGMA foreign_keys = ON")
        self.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, root_path TEXT NOT NULL)"
        )
        self.execute("""
            CREATE TABLE files (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                path TEXT NOT NULL,
                relative_path TEXT,
                deleted INTEGER DEFAULT 0
            )
            """)
        self.execute(
            "INSERT INTO projects (id, root_path) VALUES (?, ?)",
            ("proj", str(root)),
        )

    def execute(self, sql: str, params: tuple | None = None, **_: object) -> dict:
        """Execute the command."""
        cur = self.conn.execute(sql, params or ())
        if sql.lstrip().upper().startswith(("SELECT", "PRAGMA")):
            return {"data": [dict(row) for row in cur.fetchall()]}
        self.conn.commit()
        return {"data": [], "affected_rows": cur.rowcount}

    def select(
        self, table_name: str, where: dict | None = None, **_: object
    ) -> list[dict[str, Any]]:
        """Return select."""
        sql = f"SELECT * FROM {table_name}"
        params: list[object] = []
        if where:
            sql += " WHERE " + " AND ".join(f"{key} = ?" for key in where)
            params.extend(where.values())
        return cast(list[dict[str, Any]], self.execute(sql, tuple(params))["data"])

    def get_project(self, project_id: str) -> SimpleNamespace | None:
        """Return get project."""
        rows = self.execute("SELECT * FROM projects WHERE id = ?", (project_id,))[
            "data"
        ]
        if not rows:
            return None
        return SimpleNamespace(**rows[0])

    def get_file_by_path(
        self, path: str, project_id: str, include_deleted: bool = False
    ) -> dict | None:
        """Return get file by path."""
        rel = str(Path(path).resolve().relative_to(self.root.resolve())).replace(
            "\\", "/"
        )
        sql = "SELECT * FROM files WHERE project_id = ? AND (path = ? OR relative_path = ?)"
        params: tuple[object, ...] = (project_id, rel, rel)
        if not include_deleted:
            sql += " AND (deleted = 0 OR deleted IS NULL)"
        rows = self.execute(sql, params)["data"]
        return rows[0] if rows else None


def test_runtime_session_and_lease_refcount(tmp_path: Path) -> None:
    """Verify test runtime session and lease refcount."""
    db = FakeDatabase(tmp_path)
    ensure_runtime_lock_tables(db)
    session = register_runtime_session(db, role="pytest")

    first = acquire_file_advisory_lease(
        db,
        session_id=session.session_id,
        project_id="proj",
        file_path="a.py",
        lock_mode="full",
    )
    second = acquire_file_advisory_lease(
        db,
        session_id=session.session_id,
        project_id="proj",
        file_path="a.py",
        lock_mode="full",
    )
    assert first["refcount"] == 1
    assert second["refcount"] == 2

    release_file_advisory_lease(
        db,
        session_id=session.session_id,
        project_id="proj",
        file_path="a.py",
        lock_mode="full",
    )
    rows = db.execute("SELECT refcount FROM file_advisory_lock_leases")["data"]
    assert rows == [{"refcount": 1}]

    release_file_advisory_lease(
        db,
        session_id=session.session_id,
        project_id="proj",
        file_path="a.py",
        lock_mode="full",
    )
    assert db.execute("SELECT * FROM file_advisory_lock_leases")["data"] == []


def test_get_file_advisory_lock_status_aggregates(tmp_path: Path) -> None:
    """Verify test get file advisory lock status aggregates."""
    db = FakeDatabase(tmp_path)
    ensure_runtime_lock_tables(db)

    assert (
        get_file_advisory_lock_status(db, project_id="proj", file_path="x.py")[
            "lock_status"
        ]
        == "free"
    )

    session = register_runtime_session(db, role="pytest")
    acquire_file_advisory_lease(
        db,
        session_id=session.session_id,
        project_id="proj",
        file_path="x.py",
        lock_mode="block_write",
    )
    st = get_file_advisory_lock_status(db, project_id="proj", file_path="x.py")
    assert st["lock_status"] == "write_locked"
    assert st["leases"]["shared_total_refcount"] == 1
    assert st["leases"]["exclusive_total_refcount"] == 0

    release_file_advisory_lease(
        db,
        session_id=session.session_id,
        project_id="proj",
        file_path="x.py",
        lock_mode="block_write",
        force=True,
    )
    acquire_file_advisory_lease(
        db,
        session_id=session.session_id,
        project_id="proj",
        file_path="x.py",
        lock_mode="full",
    )
    st2 = get_file_advisory_lock_status(db, project_id="proj", file_path="x.py")
    assert st2["lock_status"] == "fully_locked"
    assert st2["leases"]["exclusive_total_refcount"] == 1


def test_batch_lock_partial_errors_and_idempotent_unlock(tmp_path: Path) -> None:
    """Verify test batch lock partial errors and idempotent unlock."""
    db = FakeDatabase(tmp_path)
    ensure_client_session_tables(db.conn)
    target = tmp_path / "ok.py"
    target.write_text("print('ok')\n", encoding="utf-8")
    db.execute(
        "INSERT INTO files (id, project_id, path, relative_path, deleted) VALUES (?, ?, ?, ?, 0)",
        ("file-ok", "proj", "ok.py", "ok.py"),
    )
    session = register_runtime_session(db, role="pytest")
    cmd = ProjectFileAdvisoryLockBatchCommand()

    ok_item = {
        "session_id": session.session_id,
        "project_id": "proj",
        "file_path": "ok.py",
        "action": "lock",
        "lock_mode": "block_write",
    }
    missing_item = {
        "session_id": session.session_id,
        "project_id": "proj",
        "file_path": "missing.py",
        "action": "lock",
        "lock_mode": "full",
    }
    unlock_item = {
        "session_id": session.session_id,
        "project_id": "proj",
        "file_path": "missing.py",
        "action": "unlock",
    }
    ok = cmd._execute_item(
        db,
        {"index": 0, **ok_item},
        ok_item,
        current_session_id=session.session_id,
        allow_foreign_session=False,
        timeout_seconds=1.0,
    )
    missing = cmd._execute_item(
        db,
        {"index": 1, **missing_item},
        missing_item,
        current_session_id=session.session_id,
        allow_foreign_session=False,
        timeout_seconds=1.0,
    )
    unlocked_missing = cmd._execute_item(
        db,
        {"index": 2, **unlock_item},
        unlock_item,
        current_session_id=session.session_id,
        allow_foreign_session=False,
        timeout_seconds=1.0,
    )

    assert ok["ok"] is True
    assert missing["ok"] is False
    assert missing["code"] == "FILE_NOT_FOUND"
    assert unlocked_missing["ok"] is True
    release_persistent_file_lock(
        session_id=session.session_id,
        project_id="proj",
        file_path="ok.py",
        database=db,
        force=True,
    )


def test_persistent_file_lock_records_lease(tmp_path: Path) -> None:
    """Verify test persistent file lock records lease."""
    db = FakeDatabase(tmp_path)
    target = tmp_path / "held.py"
    target.write_text("x = 1\n", encoding="utf-8")
    session = register_runtime_session(db, role="pytest")
    handle = acquire_persistent_file_lock(
        target,
        mode="full",
        database=db,
        project_id="proj",
        file_path="held.py",
        session_id=session.session_id,
        timeout=1.0,
    )
    try:
        rows = db.execute("SELECT * FROM file_advisory_lock_leases")["data"]
        assert len(rows) == 1
        assert rows[0]["session_id"] == session.session_id
    finally:
        handle.release(force_lease=True)
    assert db.execute("SELECT * FROM file_advisory_lock_leases")["data"] == []
