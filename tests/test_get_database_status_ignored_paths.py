"""get_database_status aggregates exclude default ignored path segments (e.g. .venv)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from code_analysis.commands.worker_status_mcp_commands.get_database_status_build import (
    build_database_status_result,
)
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker


def test_needing_indexing_count_excludes_dot_venv_path(tmp_path: Path) -> None:
    """Structural backlog uses NOT(_WHERE_FILES_INDEXED), not needs_chunking=1 alone."""
    db_path = tmp_path / "status.db"
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
    db._execute(
        "UPDATE files SET needs_chunking = 1 WHERE project_id = ?",
        (project_id,),
    )
    db._execute(
        """
        INSERT INTO ast_trees (file_id, project_id, ast_json, ast_hash, file_mtime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (good_id, project_id, "[]", "fixturehash", os.path.getmtime(good)),
    )
    db._commit()
    try:
        result = build_database_status_result(
            db, db_path, driver_type="sqlite"
        )
        # Eligible file has AST → structurally indexed; .venv row excluded from aggregates.
        assert result["files"]["needing_indexing"] == 0
        assert result["files"]["indexed"] == 1
        sample = result["files"].get("needing_chunking_sample") or []
        assert all("/.venv/" not in (row.get("path") or "") for row in sample)
    finally:
        db.close()


def test_needing_indexing_counts_eligible_file_without_structural_index(
    tmp_path: Path,
) -> None:
    """Active normal file with no AST and no cleared needs_chunking counts as needing_indexing."""
    db_path = tmp_path / "status2.db"
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
    db._execute(
        "UPDATE files SET needs_chunking = 1 WHERE project_id = ?",
        (project_id,),
    )
    db._commit()
    try:
        result = build_database_status_result(db, db_path, driver_type="sqlite")
        assert result["files"]["needing_indexing"] == 1
        assert result["files"]["indexed"] == 0
        assert result["files"]["active"] == 1
    finally:
        db.close()
