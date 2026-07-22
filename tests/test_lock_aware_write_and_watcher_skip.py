"""
Tests for lock-aware write primitives and the file-watcher skip on locked files.

Covers the Code Analysis Server primitives the editor depends on:

- S1: atomic register-before-write for a new file (``register_file_row_for_new_content``)
  and rollback of the registered row when the write fails.
- S2: advisory-lease parity — a file locked through the session path reports the same
  ``project_file_lock_status`` as a file created-and-locked through the transfer-save path.
- S3: the file watcher skips every processing branch for advisory-locked paths, on both
  the engine-agnostic delta path and the PostgreSQL bulk-sync path.
- S4: releasing the lock is idempotent and lets the watcher resume the path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from code_analysis.commands.project_file_transfer_by_id_commands import (
    _rollback_registered_file_row,
)
from code_analysis.core.client_sessions import (
    acquire_session_advisory_write_lease,
    ensure_client_session_tables,
    release_session_advisory_write_lease,
)
from code_analysis.core.file_disk_registration import (
    register_file_row_for_new_content,
)
from code_analysis.core.file_lock import (
    acquire_persistent_file_lock,
    file_lock,
    release_persistent_file_lock,
)
from code_analysis.core.file_identity import relative_path_for_project
from code_analysis.core.file_watcher_pkg.processor_delta import FileDelta
from code_analysis.core.file_watcher_pkg.processor_queue import (
    _filter_delta_locked_paths,
)
from code_analysis.core.file_watcher_pkg.watcher_bulk_sync import (
    build_watcher_bulk_sync_program,
)
from code_analysis.core.file_watcher_pkg.watcher_disk_manifest import (
    WatcherDiskFileRow,
)
from code_analysis.core.runtime_lock_sessions import (
    acquire_file_advisory_lease,
    ensure_runtime_lock_tables,
    get_file_advisory_lock_status,
    list_locked_file_paths,
    register_runtime_session,
    release_file_advisory_lease,
)

PROJECT_ID = "proj"


class FakeDatabase:
    """In-memory SQLite database double exposing the client surface used here."""

    def __init__(self, root: Path, driver_type: Optional[str] = None) -> None:
        """Create tables and register a single project rooted at ``root``."""
        self.root = root
        self._driver_type = driver_type
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.execute("PRAGMA foreign_keys = ON")
        self.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, root_path TEXT NOT NULL)"
        )
        self.execute("""
            CREATE TABLE files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                path TEXT NOT NULL,
                relative_path TEXT,
                lines INTEGER,
                last_modified REAL,
                has_docstring INTEGER DEFAULT 0,
                deleted INTEGER DEFAULT 0
            )
            """)
        self.execute(
            "INSERT INTO projects (id, root_path) VALUES (?, ?)",
            (PROJECT_ID, str(root)),
        )

    def execute(self, sql: str, params: tuple | None = None, **_: object) -> dict:
        """Run one SQL statement and return a client-style result dict.

        Production SQL (``sql_portable``) now unconditionally emits PostgreSQL Julian-day
        syntax (SQLite support was removed); translate the two fragments this double
        actually encounters into SQLite equivalents before executing against the
        in-memory SQLite backing.
        """
        sql = sql.replace(
            "EXTRACT(JULIAN FROM (CURRENT_TIMESTAMP - INTERVAL '1 day'))",
            "julianday('now', '-1 day')",
        ).replace(
            "EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)",
            "julianday('now')",
        )
        cur = self.conn.execute(sql, params or ())
        if sql.lstrip().upper().startswith(("SELECT", "PRAGMA")):
            return {"data": [dict(row) for row in cur.fetchall()]}
        self.conn.commit()
        return {
            "data": [],
            "affected_rows": cur.rowcount,
            "lastrowid": cur.lastrowid,
        }

    def begin_transaction(self) -> str:
        """Return a dummy transaction id (statements auto-commit)."""
        return "tx"

    def commit_transaction(self, _tid: str) -> None:
        """No-op commit (statements already auto-committed)."""

    def rollback_transaction(self, _tid: str) -> None:
        """No-op rollback hook for the client surface."""

    def get_project(self, project_id: str) -> Optional[SimpleNamespace]:
        """Return the project row as an attribute namespace, or None."""
        rows = self.execute("SELECT * FROM projects WHERE id = ?", (project_id,))[
            "data"
        ]
        return SimpleNamespace(**rows[0]) if rows else None

    def add_file(
        self,
        path: str,
        lines: int,
        last_modified: float,
        has_docstring: bool,
        project_id: str,
    ) -> None:
        """Insert a files row, storing the project-relative POSIX path."""
        rel = relative_path_for_project(path, self.root)
        self.execute(
            "INSERT INTO files "
            "(project_id, path, relative_path, lines, last_modified, has_docstring) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, rel, rel, lines, last_modified, 1 if has_docstring else 0),
        )

    def get_file_by_path(
        self, path: str, project_id: str, include_deleted: bool = False
    ) -> Optional[dict]:
        """Resolve an absolute path to its files row, or None."""
        rel = relative_path_for_project(path, self.root)
        sql = (
            "SELECT * FROM files WHERE project_id = ? "
            "AND (path = ? OR relative_path = ?)"
        )
        if not include_deleted:
            sql += " AND (deleted = 0 OR deleted IS NULL)"
        rows = self.execute(sql, (project_id, rel, rel))["data"]
        return rows[0] if rows else None

    def get_file_by_id(self, file_id: Any) -> Optional[dict]:
        """Return the files row for ``file_id``, or None."""
        rows = self.execute("SELECT * FROM files WHERE id = ?", (file_id,))["data"]
        return rows[0] if rows else None

    def purge_file_ids_cascade(
        self,
        project_id: str,
        file_ids: Any,
        *,
        operation_name: str = "purge",
    ) -> None:
        """Hard-delete files rows by id (cascade dependents would follow in prod)."""
        for fid in file_ids:
            self.execute(
                "DELETE FROM files WHERE project_id = ? AND id = ?",
                (project_id, fid),
            )


def _make_db(tmp_path: Path, driver_type: Optional[str] = None) -> Any:
    """Build a FakeDatabase with the runtime-lock tables ensured."""
    db = FakeDatabase(tmp_path, driver_type=driver_type)
    ensure_runtime_lock_tables(db)
    return db


def test_register_before_write_then_rollback(tmp_path: Path) -> None:
    """S1: a new file is registered before its bytes exist, and rolls back cleanly."""
    db = _make_db(tmp_path)
    abs_path = tmp_path / "pkg" / "new_module.py"
    content = '"""Doc."""\n\nx = 1\n'

    assert not abs_path.exists()
    row = register_file_row_for_new_content(db, PROJECT_ID, abs_path, content)
    assert row is not None and row.get("id") is not None
    # Registered purely from content — the bytes are not on disk yet.
    assert not abs_path.exists()
    assert db.get_file_by_id(row["id"]) is not None

    _rollback_registered_file_row(db, PROJECT_ID, str(row["id"]))
    assert db.get_file_by_id(row["id"]) is None


def test_lock_status_parity_and_listing(tmp_path: Path) -> None:
    """S2: an exclusive lease reports fully_locked and appears in the locked set."""
    db = _make_db(tmp_path)
    session = register_runtime_session(db, role="pytest")
    acquire_file_advisory_lease(
        db,
        session_id=session.session_id,
        project_id=PROJECT_ID,
        file_path="pkg/mod.py",
        lock_mode="full",
    )

    status = get_file_advisory_lock_status(
        db, project_id=PROJECT_ID, file_path="pkg/mod.py"
    )
    assert status["lock_status"] == "fully_locked"
    assert "pkg/mod.py" in list_locked_file_paths(db, PROJECT_ID)


def test_session_open_lease_acquire_and_release(tmp_path: Path) -> None:
    """S2/S4: the session helper records an advisory lease and releases it idempotently."""
    db = _make_db(tmp_path)
    ensure_client_session_tables(db)
    session_id = "11111111-1111-4111-8111-111111111111"
    db.execute(
        "INSERT INTO client_sessions (session_id, comment) VALUES (?, ?)",
        (session_id, "pytest"),
    )
    abs_path = tmp_path / "edited.py"
    db.add_file(str(abs_path), 1, 0.0, False, PROJECT_ID)
    file_row = db.get_file_by_path(str(abs_path), PROJECT_ID)
    assert file_row is not None
    file_id = str(file_row["id"])

    lease = acquire_session_advisory_write_lease(
        db, session_id=session_id, project_id=PROJECT_ID, file_id=file_id
    )
    assert lease is not None
    status = get_file_advisory_lock_status(
        db, project_id=PROJECT_ID, file_path="edited.py"
    )
    assert status["lock_status"] == "fully_locked"
    assert "edited.py" in list_locked_file_paths(db, PROJECT_ID)

    # First release removes the lease; a second release is a no-op (idempotent).
    assert release_session_advisory_write_lease(
        db, session_id=session_id, project_id=PROJECT_ID, file_id=file_id
    )
    assert (
        release_session_advisory_write_lease(
            db, session_id=session_id, project_id=PROJECT_ID, file_id=file_id
        )
        is False
    )
    assert list_locked_file_paths(db, PROJECT_ID) == set()


def test_inner_save_lock_reuses_held_persistent_lock(tmp_path: Path) -> None:
    """Single-owner: an inner file_lock under a held persistent lock must not block.

    The create/update command holds the persistent lock for the path; the byte
    write it invokes takes file_lock on the same path. Without single-owner reuse
    this self-conflicts (same process, exclusive flock) and dead-waits.
    """
    target = tmp_path / "owned.py"
    target.write_text("x = 1\n", encoding="utf-8")

    owner = acquire_persistent_file_lock(
        target,
        mode="full",
        database=None,
        project_id="p",
        file_path="owned.py",
        session_id="sess-1",
    )
    try:
        start = time.monotonic()
        with file_lock(target, mode="full"):
            pass
        # Reused as a no-op: returns immediately instead of blocking on the owner.
        assert time.monotonic() - start < 1.0
        # The owner's lock is untouched by the inner no-op release.
        assert not owner.released
    finally:
        release_persistent_file_lock(
            session_id="sess-1",
            project_id="p",
            file_path="owned.py",
            database=None,
            force=True,
        )


def test_filter_delta_skips_locked_on_every_branch() -> None:
    """S3: locked paths are dropped from new, changed, deleted and ignore-purge lists."""
    delta = FileDelta(
        new_files=[("locked.py", 1.0, 10), ("free_new.py", 1.0, 10)],
        changed_files=[("locked.py", 2.0, 20), ("free_changed.py", 2.0, 20)],
        deleted_files=["locked.py", "free_deleted.py"],
        ignore_purge_paths=["locked.py", "free_ignored.py"],
    )
    filtered = _filter_delta_locked_paths(delta, {"locked.py"})

    assert [p for p, _, _ in filtered.new_files] == ["free_new.py"]
    assert [p for p, _, _ in filtered.changed_files] == ["free_changed.py"]
    assert filtered.deleted_files == ["free_deleted.py"]
    assert filtered.ignore_purge_paths == ["free_ignored.py"]


def test_locked_set_then_resume_after_release(tmp_path: Path) -> None:
    """S4: after release the path leaves the locked set and is no longer filtered."""
    db = _make_db(tmp_path)
    session = register_runtime_session(db, role="pytest")
    acquire_file_advisory_lease(
        db,
        session_id=session.session_id,
        project_id=PROJECT_ID,
        file_path="watched.py",
        lock_mode="full",
    )
    assert list_locked_file_paths(db, PROJECT_ID) == {"watched.py"}

    release_file_advisory_lease(
        db,
        session_id=session.session_id,
        project_id=PROJECT_ID,
        file_path="watched.py",
        lock_mode="full",
        force=True,
    )
    assert list_locked_file_paths(db, PROJECT_ID) == set()

    delta = FileDelta(
        new_files=[("watched.py", 1.0, 5)],
        changed_files=[],
        deleted_files=[],
    )
    resumed = _filter_delta_locked_paths(delta, list_locked_file_paths(db, PROJECT_ID))
    assert [p for p, _, _ in resumed.new_files] == ["watched.py"]


def _bulk_program_statements(program: Any) -> list[str]:
    """Flatten a logical-write program into its SQL statement strings."""
    statements: list[str] = []
    for batch in program.get("batches", []):
        for sql, _params in batch:
            statements.append(sql)
    return statements


def test_bulk_sync_program_filters_locked_paths_postgres(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """S3 (PostgreSQL): bulk sync deletes locked rows from the sync table, untouched otherwise."""
    db: Any = FakeDatabase(tmp_path, driver_type="postgres")
    disk_rows = [
        WatcherDiskFileRow(
            relative_path="pkg/mod.py",
            last_modified=1.0,
            lines=3,
            has_docstring=True,
            tree_checksum="abc",
        )
    ]

    program = build_watcher_bulk_sync_program(
        PROJECT_ID, "wd", disk_rows, db, locked_paths={"pkg/mod.py"}
    )
    lock_deletes = [
        (sql, params)
        for batch in program["batches"]
        for sql, params in batch
        if "DELETE FROM" in sql and "watcher_sync" in sql and "relative_path IN" in sql
    ]
    assert len(lock_deletes) == 1
    assert lock_deletes[0][1] == ("pkg/mod.py",)
    # The disk manifest itself is never filtered (that would force a false delete).
    assert any(
        "INSERT INTO watcher_disk_raw" in s for s in _bulk_program_statements(program)
    )


def test_bulk_sync_program_without_locks_has_no_filter(tmp_path: Path) -> None:
    """S3 (PostgreSQL): no lock-filter statement is emitted when nothing is locked."""
    db: Any = FakeDatabase(tmp_path, driver_type="postgres")
    disk_rows = [
        WatcherDiskFileRow(
            relative_path="pkg/mod.py",
            last_modified=1.0,
            lines=3,
            has_docstring=False,
            tree_checksum="abc",
        )
    ]
    program = build_watcher_bulk_sync_program(
        PROJECT_ID, "wd", disk_rows, db, locked_paths=None
    )
    assert not [
        sql
        for sql in _bulk_program_statements(program)
        if "DELETE FROM" in sql and "watcher_sync" in sql and "relative_path IN" in sql
    ]
