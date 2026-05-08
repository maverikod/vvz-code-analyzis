"""
Tests for atomic file data updates via logical write (DatabaseClient + RPC).

Exercises :func:`~code_analysis.core.database_client.file_data_batch.update_file_data_atomic_batch`,
which runs ``execute_logical_write_operation`` in one server-side transaction (replacing the
legacy :func:`~code_analysis.core.database.files.atomic.update_file_data_atomic` pairing with
the historical single-connection ``_in_transaction`` guard).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Iterator

import pytest

from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.file_data_batch import (
    update_file_data_atomic_batch,
)
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers

from tests.test_fixture_content import DEFAULT_TEST_FILE_CONTENT


@pytest.fixture
def ipc_client(tmp_path: Path) -> Iterator[DatabaseClient]:
    db_path = tmp_path / "test.db"
    driver = create_driver("sqlite", {"path": str(db_path)})
    handlers = RPCHandlers(driver)
    ipc = InProcessRpcClient(handlers)
    client = DatabaseClient(rpc_client=ipc)
    client.connect()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    client.sync_schema(get_schema_definition(), backup_dir=str(backup_dir))
    try:
        yield client
    finally:
        client.disconnect()


@pytest.fixture
def test_project(ipc_client: DatabaseClient, tmp_path: Path):
    project_id = str(uuid.uuid4())
    ipc_client.execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path), tmp_path.name),
    )
    return project_id


@pytest.fixture
def test_file(ipc_client: DatabaseClient, tmp_path: Path, test_project: str):
    file_path = tmp_path / "test_file.py"
    file_content = DEFAULT_TEST_FILE_CONTENT
    file_path.write_text(file_content, encoding="utf-8")
    file_mtime = os.path.getmtime(file_path)
    lines = len(file_content.splitlines())
    file_id = ipc_client.add_file(
        path=str(file_path),
        lines=lines,
        last_modified=file_mtime,
        has_docstring=True,
        project_id=test_project,
    )
    return file_id, file_path, test_project, tmp_path


def _fetchall(client: DatabaseClient, sql: str, params: tuple | None = None):
    r = client.execute(sql, params)
    return list(r.get("data") or [])


def _fetchone(client: DatabaseClient, sql: str, params: tuple | None = None):
    rows = _fetchall(client, sql, params)
    return rows[0] if rows else None


def test_update_file_data_batch_success(ipc_client: DatabaseClient, test_file):
    file_id, file_path, project_id, _root_dir = test_file
    new_source = '''"""
Updated test file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

class UpdatedClass:
    """Updated test class."""
    
    def new_method(self):
        """New method."""
        pass

def new_function():
    """New function."""
    pass
'''
    file_path.write_text(new_source, encoding="utf-8")
    mtime = os.path.getmtime(file_path)
    result = update_file_data_atomic_batch(
        ipc_client,
        file_id=file_id,
        project_id=project_id,
        source_code=new_source,
        file_path=str(file_path.resolve()),
        file_mtime=mtime,
    )
    assert result.get("success") is True, result
    classes = _fetchall(
        ipc_client, "SELECT name FROM classes WHERE file_id = ?", (file_id,)
    )
    names = [c["name"] for c in classes]
    assert "UpdatedClass" in names
    funcs = _fetchall(
        ipc_client, "SELECT name FROM functions WHERE file_id = ?", (file_id,)
    )
    assert "new_function" in [f["name"] for f in funcs]
    cst = _fetchone(
        ipc_client, "SELECT cst_code FROM cst_trees WHERE file_id = ?", (file_id,)
    )
    assert cst is not None
    assert new_source in (cst.get("cst_code") or "")


def test_update_file_data_batch_syntax_error(ipc_client: DatabaseClient, test_file):
    file_id, file_path, project_id, _root = test_file
    invalid_source = "def invalid_syntax("
    result = update_file_data_atomic_batch(
        ipc_client,
        file_id=file_id,
        project_id=project_id,
        source_code=invalid_source,
        file_path=str(file_path.resolve()),
        file_mtime=0.0,
    )
    assert result.get("success") is False
    assert "Syntax error" in (result.get("error") or "")


def test_update_file_data_batch_no_outer_transaction_required(
    ipc_client: DatabaseClient, test_file
):
    """Logical write is self-transacted; no outer ``_in_transaction`` guard."""
    file_id, file_path, project_id, _root = test_file
    new_source = "x = 1\n"
    file_path.write_text(new_source, encoding="utf-8")
    result = update_file_data_atomic_batch(
        ipc_client,
        file_id=file_id,
        project_id=project_id,
        source_code=new_source,
        file_path=str(file_path.resolve()),
        file_mtime=os.path.getmtime(file_path),
    )
    assert result.get("success") is True, result


def test_update_file_data_batch_clears_old_entities(
    ipc_client: DatabaseClient, test_file
):
    file_id, file_path, project_id, _root = test_file
    oc_id = str(uuid.uuid4())
    of_id = str(uuid.uuid4())
    ipc_client.execute(
        """
        INSERT INTO classes (id, file_id, name, line, docstring, bases, cst_node_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            oc_id,
            file_id,
            "OldClass",
            1,
            "d",
            "[]",
            "00000000-0000-4000-8000-000000000001",
        ),
    )
    ipc_client.execute(
        """
        INSERT INTO functions (id, file_id, name, line, args, docstring, cst_node_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            of_id,
            file_id,
            "old_function",
            10,
            "[]",
            "d",
            "00000000-0000-4000-8000-000000000002",
        ),
    )

    new_source = '''"""u."""
class NewClass:
    """N."""
    pass

def new_function():
    """N."""
    pass
'''
    file_path.write_text(new_source, encoding="utf-8")
    mtime = os.path.getmtime(file_path)
    result = update_file_data_atomic_batch(
        ipc_client,
        file_id=file_id,
        project_id=project_id,
        source_code=new_source,
        file_path=str(file_path.resolve()),
        file_mtime=mtime,
    )
    assert result.get("success") is True, result
    assert (
        _fetchone(ipc_client, "SELECT id FROM classes WHERE id = ?", (oc_id,)) is None
    )
    assert (
        _fetchone(ipc_client, "SELECT id FROM functions WHERE id = ?", (of_id,)) is None
    )
    assert (
        _fetchone(
            ipc_client,
            "SELECT name FROM classes WHERE file_id = ? AND name = ?",
            (file_id, "NewClass"),
        )
        is not None
    )


def test_add_file_revives_soft_deleted_row_same_path(
    ipc_client: DatabaseClient, tmp_path: Path, test_project: str
) -> None:
    """UNIQUE(project_id, path) still holds for deleted=1; add_file must UPDATE not INSERT."""
    file_path = tmp_path / "tombstone_probe.py"
    file_path.write_text("x = 1\n", encoding="utf-8")
    abs_path = str(file_path.resolve())
    mtime = os.path.getmtime(file_path)
    pid = test_project
    fid1 = ipc_client.add_file(
        path=abs_path,
        lines=1,
        last_modified=mtime,
        has_docstring=False,
        project_id=pid,
    )
    ipc_client.execute("UPDATE files SET deleted = 1 WHERE id = ?", (fid1,))
    assert ipc_client.get_file_by_path(abs_path, pid, include_deleted=False) is None
    rows_deleted = _fetchall(
        ipc_client,
        "SELECT id FROM files WHERE project_id = ? AND path = ?",
        (pid, "tombstone_probe.py"),
    )
    assert len(rows_deleted) == 1
    fid2 = ipc_client.add_file(
        path=abs_path,
        lines=2,
        last_modified=mtime + 1.0,
        has_docstring=False,
        project_id=pid,
    )
    assert str(fid2) == str(fid1)
    row = _fetchone(
        ipc_client,
        "SELECT id, deleted, lines FROM files WHERE project_id = ? AND path = ?",
        (pid, "tombstone_probe.py"),
    )
    assert row is not None
    assert int(row.get("deleted") or 0) == 0
    assert int(row["lines"]) == 2
    dup_count = _fetchone(
        ipc_client,
        "SELECT COUNT(*) AS c FROM files WHERE project_id = ? AND path = ?",
        (pid, "tombstone_probe.py"),
    )
    assert int(dup_count["c"]) == 1
