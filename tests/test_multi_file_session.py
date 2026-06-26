"""Multi-file universal_file session and session_open_file lock tests."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.sessions.session_open_file_command import (
    SessionOpenFileCommand,
)
from code_analysis.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from code_analysis.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from code_analysis.core.client_sessions import (
    FileLockedByOtherSessionError,
    open_session_file,
    ensure_client_session_tables,
)

PROJECT = "cafebabe-cafe-4caf-babe-cafebabecafe"


def _db_for(tmp: Path) -> MagicMock:
    """Return db for."""
    m = MagicMock()
    row = {
        "id": PROJECT,
        "root_path": str(tmp.resolve()),
        "watch_dir_id": None,
        "name": "test-project",
    }
    m.select.return_value = [row]
    p = MagicMock()
    p.root_path = str(tmp.resolve())
    m.get_project.return_value = p
    return m


def _ensure_project_root(tmp: Path) -> None:
    """Return ensure project root."""
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(json.dumps({"id": PROJECT}) + "\n", encoding="utf-8")


def _sqlite_facade(conn: sqlite3.Connection):
    """Return sqlite facade."""

    class Facade:
        """Represent Facade."""

        def execute(self, sql, params=(), **kw):
            """Execute the command."""
            cur = conn.execute(sql, params)
            if sql.strip().upper().startswith("SELECT"):
                return {"data": [dict(r) for r in cur.fetchall()]}
            conn.commit()
            return {"affected_rows": cur.rowcount, "data": []}

        def begin_transaction(self):
            """Return begin transaction."""
            return "t1"

        def commit_transaction(self, tid):
            """Return commit transaction."""
            return None

        def rollback_transaction(self, tid):
            """Return rollback transaction."""
            return None

    return Facade()


def test_open_session_file_allows_multiple_files_one_session() -> None:
    """Verify test open session file allows multiple files one session."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        conn = sqlite3.connect(str(tmp / "x.db"))
        conn.row_factory = sqlite3.Row
        ensure_client_session_tables(conn)
        project_id = str(uuid.uuid4())
        file1 = str(uuid.uuid4())
        file2 = str(uuid.uuid4())
        conn.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, root_path TEXT, name TEXT)"
        )
        conn.execute(
            "CREATE TABLE files (id TEXT PRIMARY KEY, project_id TEXT, path TEXT, relative_path TEXT)"
        )
        conn.execute(
            "INSERT INTO projects VALUES (?, ?, ?)", (project_id, "/tmp/p", "p")
        )
        conn.execute(
            "INSERT INTO files VALUES (?, ?, ?, ?)",
            (file1, project_id, "/tmp/p/a.py", "a.py"),
        )
        conn.execute(
            "INSERT INTO files VALUES (?, ?, ?, ?)",
            (file2, project_id, "/tmp/p/b.py", "b.py"),
        )
        conn.commit()

        facade = _sqlite_facade(conn)
        sid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO client_sessions (session_id, comment) VALUES (?, ?)",
            (sid, "multi"),
        )
        conn.commit()
        r1 = open_session_file(facade, sid, project_id, file1)
        r2 = open_session_file(facade, sid, project_id, file2)
        assert r1["acquired"] is True
        assert r2["acquired"] is True
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM session_file_locks WHERE session_id = ?",
            (sid,),
        ).fetchone()["c"]
        assert count == 2


def test_open_session_file_rejects_other_session_holder() -> None:
    """Verify test open session file rejects other session holder."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        conn = sqlite3.connect(str(tmp / "x.db"))
        conn.row_factory = sqlite3.Row
        ensure_client_session_tables(conn)
        project_id = str(uuid.uuid4())
        file_id = str(uuid.uuid4())
        conn.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, root_path TEXT, name TEXT)"
        )
        conn.execute(
            "CREATE TABLE files (id TEXT PRIMARY KEY, project_id TEXT, path TEXT, relative_path TEXT)"
        )
        conn.execute(
            "INSERT INTO projects VALUES (?, ?, ?)", (project_id, "/tmp/p", "p")
        )
        conn.execute(
            "INSERT INTO files VALUES (?, ?, ?, ?)",
            (file_id, project_id, "/tmp/p/a.py", "a.py"),
        )
        conn.commit()

        facade = _sqlite_facade(conn)
        s1 = str(uuid.uuid4())
        s2 = str(uuid.uuid4())
        conn.executemany(
            "INSERT INTO client_sessions (session_id, comment) VALUES (?, ?)",
            [(s1, "one"), (s2, "two")],
        )
        conn.commit()
        open_session_file(facade, s1, project_id, file_id)
        with pytest.raises(FileLockedByOtherSessionError):
            open_session_file(facade, s2, project_id, file_id)


@pytest.mark.asyncio
async def test_universal_file_open_multi_file_same_session_id(tmp_path: Path) -> None:
    """Verify test universal file open multi file same session id."""
    _ensure_project_root(tmp_path)
    rel_a = "src/a.txt"
    rel_b = "src/b.txt"
    (tmp_path / "src").mkdir()
    (tmp_path / rel_a).write_text("alpha\n", encoding="utf-8")
    (tmp_path / rel_b).write_text("beta\n", encoding="utf-8")
    cfg = {"registration": {"instance_uuid": "u"}, "security": {"policy": "disabled"}}
    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
        ),
        patch.object(BaseMCPCommand, "_get_raw_config", return_value=cfg),
    ):
        opener = UniversalFileOpenCommand()
        first = await opener.execute(
            **opener.validate_params({"project_id": PROJECT, "file_path": rel_a})
        )
        assert isinstance(first, SuccessResult)
        sid = first.data["session_id"]
        second = await opener.execute(
            **opener.validate_params(
                {
                    "project_id": PROJECT,
                    "file_path": rel_b,
                    "session_id": sid,
                }
            )
        )
        assert isinstance(second, SuccessResult)
        assert second.data["session_id"] == sid

        closer = UniversalFileCloseCommand()
        close_a = await closer.execute(
            project_id=PROJECT, session_id=sid, file_path=rel_a
        )
        close_b = await closer.execute(
            project_id=PROJECT, session_id=sid, file_path=rel_b
        )
        assert isinstance(close_a, SuccessResult)
        assert isinstance(close_b, SuccessResult)


@pytest.mark.asyncio
async def test_session_open_file_command_returns_file_locked() -> None:
    """Verify test session open file command returns file locked."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        conn = sqlite3.connect(str(tmp / "x.db"))
        conn.row_factory = sqlite3.Row
        ensure_client_session_tables(conn)
        project_id = str(uuid.uuid4())
        file_id = str(uuid.uuid4())
        conn.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, root_path TEXT, name TEXT)"
        )
        conn.execute(
            "CREATE TABLE files (id TEXT PRIMARY KEY, project_id TEXT, path TEXT, relative_path TEXT)"
        )
        conn.execute(
            "INSERT INTO projects VALUES (?, ?, ?)", (project_id, "/tmp/p", "p")
        )
        conn.execute(
            "INSERT INTO files VALUES (?, ?, ?, ?)",
            (file_id, project_id, "/tmp/p/a.py", "a.py"),
        )
        conn.commit()

        facade = _sqlite_facade(conn)
        holder = str(uuid.uuid4())
        other = str(uuid.uuid4())
        conn.executemany(
            "INSERT INTO client_sessions (session_id, comment) VALUES (?, ?)",
            [(holder, "holder"), (other, "other")],
        )
        conn.commit()
        open_session_file(facade, holder, project_id, file_id)

        db = MagicMock()
        db.execute = facade.execute
        cfg = {
            "registration": {"instance_uuid": "u"},
            "security": {"policy": "disabled"},
        }
        with (
            patch.object(BaseMCPCommand, "_open_database_from_config", return_value=db),
            patch.object(BaseMCPCommand, "_get_raw_config", return_value=cfg),
        ):
            cmd = SessionOpenFileCommand()
            result = await cmd.execute(
                session_id=other, project_id=project_id, file_id=file_id
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "FILE_LOCKED"
