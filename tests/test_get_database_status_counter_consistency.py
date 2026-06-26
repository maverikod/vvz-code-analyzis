"""Invariant tests for get_database_status file counters."""

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
    db_path = tmp_path / "status_counters.db"
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


def test_active_equals_indexed_plus_needing_indexing(
    tmp_path: Path, status_db_client
) -> None:
    """Over active, path-eligible files, indexed and needing_indexing partition _WHERE_FILES_INDEXED."""
    db, db_path = status_db_client
    project_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO projects (id, root_path, name, updated_at) "
        "VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path.resolve()), tmp_path.name),
    )

    def add_py(name: str, body: str) -> str:
        """Return add py."""
        p = tmp_path / name
        p.write_text(body, encoding="utf-8")
        return db.add_file(
            path=str(p.resolve()),
            lines=1,
            last_modified=os.path.getmtime(p),
            has_docstring=False,
            project_id=project_id,
        )

    # A: backlog — needs_chunking set, no AST
    add_py("a.py", "a = 1\n")
    # B: structurally indexed via AST, still flagged for chunking
    bid = add_py("b.py", "b = 2\n")
    db.execute(
        """
        INSERT INTO ast_trees (file_id, project_id, ast_json, ast_hash, file_mtime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (bid, project_id, "[]", "hb", 1.0),
    )
    # C: indexed by cleared needs_chunking, no AST row
    cid = add_py("c.py", "c = 3\n")
    # D: soft-deleted (excluded from indexed / needing_indexing, still in total if path ok)
    did = add_py("d.py", "d = 4\n")
    db.execute(
        "UPDATE files SET needs_chunking = 1 WHERE project_id = ?",
        (project_id,),
    )
    db.execute("UPDATE files SET needs_chunking = 0 WHERE id = ?", (cid,))
    db.execute("UPDATE files SET deleted = 1 WHERE id = ?", (did,))

    result = build_database_status_result(db, db_path, driver_type="sqlite")
    files = result["files"]
    assert files["active"] == files["indexed"] + files["needing_indexing"]
    assert files["indexed"] == 2  # b + c
    assert files["needing_indexing"] == 1  # a only
    assert files["active"] == 3  # a, b, c (not d)


def test_ast_indexed_file_with_chunks_is_chunked_not_needing_indexing(
    tmp_path: Path, status_db_client
) -> None:
    """AST satisfies structural index; chunks satisfy chunked counter."""
    db, db_path = status_db_client
    project_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO projects (id, root_path, name, updated_at) "
        "VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path.resolve()), tmp_path.name),
    )
    p = tmp_path / "chunked.py"
    p.write_text("z = 0\n", encoding="utf-8")
    fid = db.add_file(
        path=str(p.resolve()),
        lines=1,
        last_modified=os.path.getmtime(p),
        has_docstring=False,
        project_id=project_id,
    )
    db.execute(
        """
        INSERT INTO ast_trees (file_id, project_id, ast_json, ast_hash, file_mtime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (fid, project_id, "[]", "hz", float(os.path.getmtime(p))),
    )
    db.execute("UPDATE files SET needs_chunking = 1 WHERE id = ?", (fid,))
    chunk_uuid_str = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO code_chunks (
            file_id, project_id, chunk_uuid, chunk_type, chunk_text
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (fid, project_id, chunk_uuid_str, "DocBlock", "hello"),
    )
    result = build_database_status_result(db, db_path, driver_type="sqlite")
    files = result["files"]
    assert files["indexed"] == 1
    assert files["needing_indexing"] == 0
    assert files["chunked"] == 1
    assert files["active"] == files["indexed"] + files["needing_indexing"]
