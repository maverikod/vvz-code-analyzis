"""
restore_backup_file must refresh DB entities after restoring bytes from old_code.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import types
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.backup_mcp_commands.restore_backup_file import (
    RestoreBackupFileMCPCommand,
)
from code_analysis.core.backup_manager import BackupManager
from code_analysis.core.database.files.update import (
    update_file_data as update_file_data_fn,
)
from code_analysis.core.path_normalization import normalize_path_simple

from tests.sqlite_in_process_legacy_facade import SqliteLegacyRpcFacade
from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


@pytest.fixture
def isolated_db(tmp_path: Path):
    """Prod-like DDL (:func:`~tests.sqlite_inprocess_database.sqlite_inprocess_database_client`)
    plus legacy facade over :class:`~code_analysis.core.database_client.client.DatabaseClient`.
    """
    client = sqlite_inprocess_database_client(
        tmp_path / "test.db", backup_dir=tmp_path / "backups"
    )
    facade = SqliteLegacyRpcFacade(client)
    try:
        yield facade, tmp_path
    finally:
        facade.close()


def _index_file(
    db,
    project_id: str,
    project_root: Path,
    rel_path: str,
    source_code: str,
) -> str:
    """Write disk file and populate entities via unified update_file_data."""
    path = project_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source_code, encoding="utf-8")
    lines_count = len(source_code.splitlines())
    stripped = source_code.lstrip()
    has_docstring = stripped.startswith('"""') or stripped.startswith("'''")
    file_id_raw = db.add_file(
        path=str(path.resolve()),
        lines=lines_count,
        last_modified=path.stat().st_mtime,
        has_docstring=has_docstring,
        project_id=project_id,
    )
    abs_p = normalize_path_simple(str(path.resolve()))
    db._execute(
        "UPDATE files SET last_modified = 0 WHERE id = ? AND project_id = ?",
        (file_id_raw, project_id),
    )
    update_file_data = types.MethodType(update_file_data_fn, db)
    result = update_file_data(
        file_path=str(path.resolve()),
        project_id=project_id,
        root_dir=project_root,
    )
    assert result.get("success"), result
    row = db._fetchone(
        "SELECT id FROM files WHERE path = ? AND project_id = ? "
        "AND (deleted IS NULL OR deleted = 0)",
        (abs_p, project_id),
    )
    assert row is not None
    return str(row["id"])


@pytest.mark.asyncio
async def test_restore_backup_refreshes_function_entities(isolated_db) -> None:
    """After restore, functions table matches restored source, not pre-restore DB state."""
    db, tmp_path = isolated_db
    project_id = str(uuid.uuid4())
    db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path), tmp_path.name),
    )
    db._commit()
    (tmp_path / "projectid").write_text(
        json.dumps({"id": project_id, "description": "test"}),
        encoding="utf-8",
    )

    v1 = "def foo():\n    return 1\n"
    v2 = "def bar():\n    return 2\n"
    rel = "mod.py"

    _index_file(db, project_id, tmp_path, rel, v1)
    backup_mgr = BackupManager(tmp_path)
    bu = backup_mgr.create_backup(
        tmp_path / rel,
        command="test",
        comment="snapshot v1",
    )
    assert bu

    _index_file(db, project_id, tmp_path, rel, v2)
    norm = normalize_path_simple(str((tmp_path / rel).resolve()))
    rows = db._fetchall(
        "SELECT name FROM functions WHERE file_id = (SELECT id FROM files WHERE path = ? AND project_id = ?)",
        (norm, project_id),
    )
    names = [r["name"] for r in rows]
    assert "bar" in names
    assert "foo" not in names

    # Restore opens an outer driver transaction then runs update_file_data_atomic_batch
    # (own logical write). SQLite + in-process RPC can hit SQLITE_BUSY; the batch path
    # ignores transaction_id, so drop the outer txn for this test-only DB handle.
    cmd = RestoreBackupFileMCPCommand()
    ot_begin = db.begin_transaction
    ot_commit = db.commit_transaction
    ot_rollback = db.rollback_transaction
    db.begin_transaction = lambda: None
    db.commit_transaction = lambda transaction_id=None: None
    db.rollback_transaction = lambda transaction_id=None: None
    try:
        with (
            patch.object(
                RestoreBackupFileMCPCommand,
                "_open_database_from_config",
                return_value=db,
            ),
            patch.object(
                RestoreBackupFileMCPCommand,
                "_resolve_project_root",
                return_value=tmp_path,
            ),
        ):
            result = await cmd.execute(
                project_id=project_id,
                file_path=rel,
                backup_uuid=bu,
            )
    finally:
        db.begin_transaction = ot_begin
        db.commit_transaction = ot_commit
        db.rollback_transaction = ot_rollback

    assert getattr(result, "data", None) is not None
    assert (tmp_path / rel).read_text(encoding="utf-8") == v1

    rows2 = db._fetchall(
        "SELECT name FROM functions WHERE file_id = (SELECT id FROM files WHERE path = ? AND project_id = ?)",
        (norm, project_id),
    )
    names2 = [r["name"] for r in rows2]
    assert "foo" in names2
    assert "bar" not in names2
