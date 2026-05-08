"""get_database_status aggregates exclude default ignored path segments (e.g. .venv)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from code_analysis.commands.worker_status_mcp_commands.get_database_status_build import (
    build_database_status_result,
)
from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers


@pytest.fixture
def status_db_client(tmp_path: Path):
    """DatabaseClient over in-process RPC with full schema."""
    db_path = tmp_path / "status_ignored.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    driver = create_driver(
        "sqlite", {"path": str(db_path), "backup_dir": str(backup_dir)}
    )
    handlers = RPCHandlers(driver)
    ipc = InProcessRpcClient(handlers)
    client = DatabaseClient(rpc_client=ipc)
    client.connect()
    try:
        client.sync_schema(get_schema_definition(), backup_dir=str(backup_dir))
        yield client, db_path
    finally:
        client.disconnect()
        if original_env is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env


def test_needing_indexing_count_excludes_dot_venv_path(
    tmp_path: Path, status_db_client
) -> None:
    """Structural backlog uses NOT(_WHERE_FILES_INDEXED), not needs_chunking=1 alone."""
    db, db_path = status_db_client
    project_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO projects (id, root_path, name, updated_at) "
        "VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path.resolve()), tmp_path.name),
    )
    good = tmp_path / "mod.py"
    good.write_text("x = 1\n", encoding="utf-8")
    good_id = db.add_file(
        path=str(good.resolve()),
        lines=1,
        last_modified=os.path.getmtime(good),
        has_docstring=False,
        project_id=project_id,
    )
    vdir = tmp_path / ".venv" / "lib" / "site-packages"
    vdir.mkdir(parents=True, exist_ok=True)
    vpy = vdir / "pkg.py"
    vpy.write_text("# v\n", encoding="utf-8")
    db.add_file(
        path=str(vpy.resolve()),
        lines=1,
        last_modified=os.path.getmtime(vpy),
        has_docstring=False,
        project_id=project_id,
    )
    db.execute(
        "UPDATE files SET needs_chunking = 1 WHERE project_id = ?",
        (project_id,),
    )
    db.execute(
        """
        INSERT INTO ast_trees (file_id, project_id, ast_json, ast_hash, file_mtime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (good_id, project_id, "[]", "fixturehash", os.path.getmtime(good)),
    )
    result = build_database_status_result(db, db_path, driver_type="sqlite")
    # Eligible file has AST → structurally indexed; .venv row excluded from aggregates.
    assert result["files"]["needing_indexing"] == 0
    assert result["files"]["indexed"] == 1
    sample = result["files"].get("needing_indexing_sample") or []
    assert all("/.venv/" not in (row.get("path") or "") for row in sample)


def test_needing_indexing_counts_eligible_file_without_structural_index(
    tmp_path: Path, status_db_client
) -> None:
    """Active normal file with no AST and no cleared needs_chunking counts as needing_indexing."""
    db, db_path = status_db_client
    project_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO projects (id, root_path, name, updated_at) "
        "VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path.resolve()), tmp_path.name),
    )
    good = tmp_path / "bare.py"
    good.write_text("y = 2\n", encoding="utf-8")
    db.add_file(
        path=str(good.resolve()),
        lines=1,
        last_modified=os.path.getmtime(good),
        has_docstring=False,
        project_id=project_id,
    )
    vdir = tmp_path / ".venv" / "lib" / "site-packages"
    vdir.mkdir(parents=True, exist_ok=True)
    vpy = vdir / "shadow.py"
    vpy.write_text("# v\n", encoding="utf-8")
    db.add_file(
        path=str(vpy.resolve()),
        lines=1,
        last_modified=os.path.getmtime(vpy),
        has_docstring=False,
        project_id=project_id,
    )
    db.execute(
        "UPDATE files SET needs_chunking = 1 WHERE project_id = ?",
        (project_id,),
    )
    result = build_database_status_result(db, db_path, driver_type="sqlite")
    assert result["files"]["needing_indexing"] == 1
    assert result["files"]["indexed"] == 0
    assert result["files"]["active"] == 1
