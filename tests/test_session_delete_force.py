"""
session_delete force flag: locks and subordinate sessions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest

from code_analysis.core.client_sessions import (
    SessionHasAdvisoryLocksError,
    SessionHasLocksError,
    SessionHasSubordinatesError,
    create_client_session,
    delete_client_session,
    get_client_session,
    is_session_valid,
    open_session_file,
)
from code_analysis.core.runtime_lock_sessions import (
    acquire_file_advisory_lease,
    ensure_client_lock_session,
)
from code_analysis.core.subordinate_sessions import (
    create_subordinate_session,
)
from tests.sqlite_in_process_legacy_facade import make_sqlite_in_process_legacy_facade

SERVER_UUID = "880e8400-e29b-41d4-a716-446655440003"


def _insert_project_and_file(
    facade, conn_path: Path, *, root_path: str = "/tmp/p"
) -> tuple[str, str]:
    """Return insert project and file."""
    import sqlite3

    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(conn_path))
    conn.execute(
        "INSERT INTO projects (id, root_path, name) VALUES (?, ?, ?)",
        (project_id, root_path, "p"),
    )
    conn.execute(
        "INSERT INTO files (id, project_id, path, relative_path) VALUES (?, ?, ?, ?)",
        (file_id, project_id, f"{root_path.rstrip('/')}/a.py", "a.py"),
    )
    conn.commit()
    conn.close()
    return project_id, file_id


def test_delete_without_force_fails_on_subordinates() -> None:
    """Verify test delete without force fails on subordinates."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        facade, client = make_sqlite_in_process_legacy_facade(root)
        try:
            parent = create_client_session(facade, comment="parent")
            create_subordinate_session(
                facade,
                parent_session_id=str(parent["session_id"]),
                server_uuid=SERVER_UUID,
                comment="link",
            )
            with pytest.raises(SessionHasSubordinatesError):
                delete_client_session(facade, str(parent["session_id"]), force=False)
            assert is_session_valid(facade, str(parent["session_id"]))
        finally:
            client.disconnect()


def test_delete_without_force_fails_on_locks() -> None:
    """Verify test delete without force fails on locks."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        facade, client = make_sqlite_in_process_legacy_facade(root)
        try:
            project_id, file_id = _insert_project_and_file(facade, root / "test.db")
            session = create_client_session(facade, comment="s")
            sid = str(session["session_id"])
            open_session_file(facade, sid, project_id, file_id)
            with pytest.raises(SessionHasLocksError):
                delete_client_session(facade, sid, force=False)
            assert is_session_valid(facade, sid)
        finally:
            client.disconnect()


def test_delete_with_force_removes_links_and_parent() -> None:
    """Verify test delete with force removes links and parent."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        facade, client = make_sqlite_in_process_legacy_facade(root)
        try:
            project_id, file_id = _insert_project_and_file(facade, root / "test.db")
            parent = create_client_session(facade, comment="parent")
            parent_id = str(parent["session_id"])
            open_session_file(facade, parent_id, project_id, file_id)
            create_subordinate_session(
                facade,
                parent_session_id=parent_id,
                server_uuid=SERVER_UUID,
                comment="link",
            )
            result = delete_client_session(facade, parent_id, force=True)
            assert result["deleted"] is True
            assert result["released_lock_count"] == 1
            assert result["released_subordinate_count"] == 1
            assert get_client_session(facade, parent_id) is None
        finally:
            client.disconnect()


def test_delete_without_force_fails_on_advisory_locks() -> None:
    """Verify test delete without force fails on advisory locks."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        project_root = root / "proj"
        project_root.mkdir()
        (project_root / "a.py").write_text("# test\n", encoding="utf-8")
        facade, client = make_sqlite_in_process_legacy_facade(root)
        try:
            project_id, file_id = _insert_project_and_file(
                facade, root / "test.db", root_path=str(project_root)
            )
            session = create_client_session(facade, comment="adv")
            sid = str(session["session_id"])
            ensure_client_lock_session(facade, sid)
            acquire_file_advisory_lease(
                facade,
                session_id=sid,
                project_id=project_id,
                file_path="a.py",
                lock_mode="full",
            )
            with pytest.raises(SessionHasAdvisoryLocksError):
                delete_client_session(facade, sid, force=False)
            assert is_session_valid(facade, sid)
        finally:
            client.disconnect()


def test_delete_with_force_releases_advisory_locks() -> None:
    """Verify test delete with force releases advisory locks."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        project_root = root / "proj"
        project_root.mkdir()
        (project_root / "a.py").write_text("# test\n", encoding="utf-8")
        facade, client = make_sqlite_in_process_legacy_facade(root)
        try:
            project_id, _file_id = _insert_project_and_file(
                facade, root / "test.db", root_path=str(project_root)
            )
            session = create_client_session(facade, comment="adv")
            sid = str(session["session_id"])
            ensure_client_lock_session(facade, sid)
            acquire_file_advisory_lease(
                facade,
                session_id=sid,
                project_id=project_id,
                file_path="a.py",
                lock_mode="full",
            )
            result = delete_client_session(facade, sid, force=True)
            assert result["deleted"] is True
            assert result["released_advisory_lease_count"] >= 1
            assert get_client_session(facade, sid) is None
        finally:
            client.disconnect()


def test_delete_without_force_succeeds_when_clean() -> None:
    """Verify test delete without force succeeds when clean."""
    with tempfile.TemporaryDirectory() as td:
        facade, client = make_sqlite_in_process_legacy_facade(Path(td))
        try:
            session = create_client_session(facade, comment="solo")
            sid = str(session["session_id"])
            result = delete_client_session(facade, sid, force=False)
            assert result["released_subordinate_count"] == 0
            assert get_client_session(facade, sid) is None
        finally:
            client.disconnect()
