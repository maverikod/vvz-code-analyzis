"""
restore_backup_file must refresh DB entities after restoring bytes from old_code.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.backup_mcp_commands.restore_backup_file import (
    RestoreBackupFileMCPCommand,
)
from code_analysis.core.backup_manager import BackupManager
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database_client.file_data_batch import (
    update_file_data_atomic_batch,
)
from code_analysis.core.database_client.objects.base import BaseObject
from code_analysis.core.path_normalization import normalize_path_simple


@pytest.fixture
def isolated_db(tmp_path: Path):
    """In-process SQLite DB with schema."""
    db_path = tmp_path / "test.db"
    driver_config = {
        "type": "sqlite",
        "config": {"path": str(db_path)},
    }
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    db = CodeDatabase(driver_config=driver_config)
    db._create_schema()
    try:
        yield db, tmp_path
    finally:
        db.close()
        if original_env is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env


def _index_file(
    db: CodeDatabase,
    project_id: str,
    project_root: Path,
    rel_path: str,
    source_code: str,
) -> int:
    """Write file and run update_file_data_atomic_batch (same pipeline as replace_file_lines)."""
    path = project_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source_code, encoding="utf-8")
    mtime = path.stat().st_mtime
    lines_count = len(source_code.splitlines())
    stripped = source_code.lstrip()
    has_docstring = stripped.startswith('"""') or stripped.startswith("'''")
    file_id = db.add_file(
        path=str(path.resolve()),
        lines=lines_count,
        last_modified=mtime,
        has_docstring=has_docstring,
        project_id=project_id,
    )
    last_modified = datetime.fromtimestamp(path.stat().st_mtime)
    file_mtime = BaseObject._to_timestamp(last_modified) or 0.0
    transaction_id = db.begin_transaction()
    try:
        update_result = update_file_data_atomic_batch(
            database=db,
            file_id=file_id,
            project_id=project_id,
            source_code=source_code,
            file_path=str(path.resolve()),
            file_mtime=file_mtime,
            transaction_id=transaction_id,
        )
        db.commit_transaction(transaction_id)
    except Exception:
        db.rollback_transaction(transaction_id)
        raise
    assert update_result.get("success"), update_result
    return int(file_id)


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

    cmd = RestoreBackupFileMCPCommand()
    with patch.object(
        RestoreBackupFileMCPCommand,
        "_open_database_from_config",
        return_value=db,
    ), patch.object(
        RestoreBackupFileMCPCommand,
        "_resolve_project_root",
        return_value=tmp_path,
    ):
        result = await cmd.execute(
            project_id=project_id,
            file_path=rel,
            backup_uuid=bu,
        )

    assert getattr(result, "data", None) is not None
    assert (tmp_path / rel).read_text(encoding="utf-8") == v1

    rows2 = db._fetchall(
        "SELECT name FROM functions WHERE file_id = (SELECT id FROM files WHERE path = ? AND project_id = ?)",
        (norm, project_id),
    )
    names2 = [r["name"] for r in rows2]
    assert "foo" in names2
    assert "bar" not in names2
