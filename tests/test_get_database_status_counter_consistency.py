"""Invariant tests for get_database_status file counters."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from code_analysis.commands.worker_status_mcp_commands.get_database_status_build import (
    build_database_status_result,
)
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker


def test_active_equals_indexed_plus_needing_indexing(tmp_path: Path) -> None:
    """Over active, path-eligible files, indexed and needing_indexing partition _WHERE_FILES_INDEXED."""
    db_path = tmp_path / "consistency.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    project_id = str(uuid.uuid4())
    db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(tmp_path.resolve()), tmp_path.name),
    )

    def add_py(name: str, body: str) -> int:
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
    db._execute(
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
    db._execute(
        "UPDATE files SET needs_chunking = 1 WHERE project_id = ?",
        (project_id,),
    )
    db._execute("UPDATE files SET needs_chunking = 0 WHERE id = ?", (cid,))
    db._execute("UPDATE files SET deleted = 1 WHERE id = ?", (did,))

    db._commit()
    try:
        result = build_database_status_result(db, db_path, driver_type="sqlite")
        files = result["files"]
        assert files["active"] == files["indexed"] + files["needing_indexing"]
        assert files["indexed"] == 2  # b + c
        assert files["needing_indexing"] == 1  # a only
        assert files["active"] == 3  # a, b, c (not d)
    finally:
        db.close()


def test_ast_indexed_file_with_chunks_is_chunked_not_needing_indexing(
    tmp_path: Path,
) -> None:
    """AST satisfies structural index; chunks satisfy chunked counter."""
    db_path = tmp_path / "chunked.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    project_id = str(uuid.uuid4())
    db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
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
    db._execute(
        """
        INSERT INTO ast_trees (file_id, project_id, ast_json, ast_hash, file_mtime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (fid, project_id, "[]", "hz", float(os.path.getmtime(p))),
    )
    db._execute("UPDATE files SET needs_chunking = 1 WHERE id = ?", (fid,))
    chunk_uuid = str(uuid.uuid4())
    db._execute(
        """
        INSERT INTO code_chunks (
            file_id, project_id, chunk_uuid, chunk_type, chunk_text
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (fid, project_id, chunk_uuid, "DocBlock", "hello"),
    )
    db._commit()
    try:
        result = build_database_status_result(db, db_path, driver_type="sqlite")
        files = result["files"]
        assert files["indexed"] == 1
        assert files["needing_indexing"] == 0
        assert files["chunked"] == 1
        assert files["active"] == files["indexed"] + files["needing_indexing"]
    finally:
        db.close()
