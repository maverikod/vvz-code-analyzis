"""
Tests for projects.processing_paused: schema, discovery SQL, and Project model.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from code_analysis.core.database_client.objects.project import Project
from code_analysis.core.indexing_worker_pkg.processing import (
    INDEXING_PROJECT_DISCOVERY_SQL,
)
from code_analysis.core.vectorization_worker_pkg.processing_cycle import (
    PROJECTS_PENDING_SQL,
)


def test_project_model_processing_paused_roundtrip() -> None:
    p = Project(
        id="550e8400-e29b-41d4-a716-446655440000",
        root_path="/tmp/r",
        processing_paused=True,
    )
    row = p.to_db_row()
    assert row.get("processing_paused") == 1
    q = Project.from_dict(
        {
            "id": p.id,
            "root_path": p.root_path,
            "processing_paused": 0,
        }
    )
    assert q.processing_paused is False


def test_vectorization_projects_sql_filters_processing_paused() -> None:
    assert "processing_paused" in PROJECTS_PENDING_SQL


def test_indexing_discovery_sql_filters_processing_paused() -> None:
    assert "processing_paused" in INDEXING_PROJECT_DISCOVERY_SQL
    assert "INNER JOIN projects" in INDEXING_PROJECT_DISCOVERY_SQL


def test_projects_table_has_processing_paused_after_sync_schema(tmp_path: Path) -> None:
    from code_analysis.core.database import CodeDatabase

    db_path = tmp_path / "pp.db"
    db = CodeDatabase({"type": "sqlite", "config": {"path": str(db_path)}})
    try:
        db.sync_schema()
        info = db._get_table_info("projects")
        names = {col["name"] for col in info}
        assert "processing_paused" in names
    finally:
        db.close()


def test_indexing_discovery_returns_no_projects_when_paused(tmp_path: Path) -> None:
    """When processing_paused=1, discovery must not return that project_id."""
    orig = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    try:
        from code_analysis.core.database import CodeDatabase
    except ImportError:
        pytest.skip("CodeDatabase not available")
    db_path = tmp_path / "disc.db"
    root = tmp_path / "proj_root"
    root.mkdir()
    py_file = root / "x.py"
    py_file.write_text("x = 1\n", encoding="utf-8")

    db = CodeDatabase({"type": "sqlite", "config": {"path": str(db_path)}})
    try:
        db.sync_schema()
        project_id = db.get_or_create_project(root_path=str(root), name="pp_t")
        import time

        file_id = db.add_file(
            path=str(py_file),
            lines=1,
            last_modified=time.time(),
            has_docstring=False,
            project_id=project_id,
        )
        db._execute(
            "UPDATE files SET needs_chunking = 1 WHERE id = ?",
            (file_id,),
        )
        db._execute(
            "UPDATE projects SET processing_paused = 1 WHERE id = ?",
            (project_id,),
        )
        db._commit()
        rows = db._fetchall(INDEXING_PROJECT_DISCOVERY_SQL, ())
        ids = [r["project_id"] for r in rows] if rows else []
        assert project_id not in ids

        db._execute(
            "UPDATE projects SET processing_paused = 0 WHERE id = ?",
            (project_id,),
        )
        db._commit()
        rows2 = db._fetchall(INDEXING_PROJECT_DISCOVERY_SQL, ())
        ids2 = [r["project_id"] for r in rows2] if rows2 else []
        assert project_id in ids2
    finally:
        db.close()
        if orig is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = orig
