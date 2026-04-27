"""
Regression: docstring chunking must run without SVO so code_chunks are populated.

Previously Step 1 in processing_cycle_projects was gated on svo_client_manager, and
process_chunks returned early without SVO — leaving chunk_count at zero forever.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker
from code_analysis.core.vectorization_worker_pkg import VectorizationWorker
from code_analysis.core.vectorization_worker_pkg.processing_cycle_projects import (
    process_projects_in_cycle,
)


@pytest.mark.asyncio
async def test_process_projects_step1_chunks_without_svo(tmp_path: Path) -> None:
    """One vectorization project cycle creates code_chunks when SVO is None."""
    db_path = tmp_path / "chunk_no_svo.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    project_id = db.get_or_create_project(root_path=str(tmp_path), name="chunk_test")
    mod = tmp_path / "mod.py"
    mod.write_text(
        '"""Module docstring long enough for chunking minimum length rules."""\n'
        "\n"
        "class C:\n"
        '    """Class docstring also long enough for minimum chunk length."""\n'
        "    pass\n",
        encoding="utf-8",
    )
    file_id = db.add_file(
        path=str(mod.resolve()),
        lines=len(mod.read_text(encoding="utf-8").splitlines()),
        last_modified=mod.stat().st_mtime,
        has_docstring=True,
        project_id=project_id,
    )
    db._execute(
        "UPDATE files SET needs_chunking = 0 WHERE id = ?",
        (file_id,),
    )
    db._commit()

    cfg = tmp_path / "config.json"
    cfg.write_text('{"database": {"type": "sqlite", "config": {"path": "%s"}}}' % db_path)

    worker = VectorizationWorker(
        db_path=db_path,
        faiss_dir=tmp_path / "faiss",
        vector_dim=384,
        config_path=str(cfg),
        svo_client_manager=None,
        max_files_per_pass=10,
        batch_size=5,
    )
    worker._stop_event = MagicMock()
    worker._stop_event.is_set.return_value = False

    projects = [
        {
            "project_id": project_id,
            "root_path": str(tmp_path),
            "pending_count": 1,
        }
    ]

    await process_projects_in_cycle(
        worker,
        db,
        projects,
        cycle_id="test-cycle",
        cycle_count=1,
        chunks_total_at_start=0,
        total_processed=0,
        total_errors=0,
    )

    row = db._fetchone(
        "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
        (file_id,),
    )
    assert row is not None and int(row["c"]) > 0

    frow = db._fetchone(
        "SELECT needs_chunking FROM files WHERE id = ?",
        (file_id,),
    )
    assert frow is not None
    assert frow.get("needs_chunking") in (0, None)

    db.close()


@pytest.mark.asyncio
async def test_regression_indexed_python_file_with_docstring_gets_code_chunks_row(
    tmp_path: Path,
) -> None:
    """
    Regression: file row has docstring metadata and needs_chunking=1, no chunks yet;
    one vectorization project cycle must insert into code_chunks (Step 1).
    """
    db_path = tmp_path / "chunk_regression.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    project_id = db.get_or_create_project(root_path=str(tmp_path), name="chunk_regression")
    mod = tmp_path / "indexed_mod.py"
    mod.write_text(
        '"""Module docstring long enough for chunking minimum length rules."""\n'
        "\n"
        "def foo():\n"
        '    """Function docstring also long enough for minimum chunk length."""\n'
        "    return 1\n",
        encoding="utf-8",
    )
    file_id = db.add_file(
        path=str(mod.resolve()),
        lines=len(mod.read_text(encoding="utf-8").splitlines()),
        last_modified=mod.stat().st_mtime,
        has_docstring=True,
        project_id=project_id,
    )
    db._execute(
        "UPDATE files SET needs_chunking = 1 WHERE id = ?",
        (file_id,),
    )
    db._commit()
    assert (
        int(
            db._fetchone(
                "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
                (file_id,),
            )["c"]
        )
        == 0
    )

    cfg = tmp_path / "config.json"
    cfg.write_text('{"database": {"type": "sqlite", "config": {"path": "%s"}}}' % db_path)

    worker = VectorizationWorker(
        db_path=db_path,
        faiss_dir=tmp_path / "faiss_reg",
        vector_dim=384,
        config_path=str(cfg),
        svo_client_manager=None,
        max_files_per_pass=10,
        batch_size=5,
    )
    worker._stop_event = MagicMock()
    worker._stop_event.is_set.return_value = False

    projects = [
        {
            "project_id": project_id,
            "root_path": str(tmp_path),
            "pending_count": 1,
        }
    ]

    await process_projects_in_cycle(
        worker,
        db,
        projects,
        cycle_id="regression-cycle",
        cycle_count=1,
        chunks_total_at_start=0,
        total_processed=0,
        total_errors=0,
    )

    row = db._fetchone(
        "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
        (file_id,),
    )
    assert row is not None and int(row["c"]) > 0

    sample = db._fetchone(
        "SELECT chunk_text, source_type FROM code_chunks WHERE file_id = ? LIMIT 1",
        (file_id,),
    )
    assert sample is not None
    st = (sample.get("source_type") or "").lower()
    assert "docstring" in st
    assert sample.get("chunk_text")

    db.close()


@pytest.mark.asyncio
async def test_analyze_file_mark_needs_chunking_clears_stale_chunks_by_path(
    tmp_path: Path,
) -> None:
    """analyze_file ends with mark_file_needs_chunking(absolute path) so stale chunks are removed."""
    db_path = tmp_path / "path_contract.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    project_id = db.get_or_create_project(root_path=str(tmp_path), name="p")
    (tmp_path / "projectid").write_text(
        '{"id": "' + project_id + '", "description": "p"}',
        encoding="utf-8",
    )
    py = tmp_path / "sub" / "x.py"
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_text(
        '"""Stale chunk test module docstring long enough."""\n\nx = 1\n',
        encoding="utf-8",
    )
    file_id = db.add_file(
        path=str(py.resolve()),
        lines=len(py.read_text(encoding="utf-8").splitlines()),
        last_modified=py.stat().st_mtime,
        has_docstring=True,
        project_id=project_id,
    )
    db._execute(
        "INSERT INTO code_chunks (file_id, project_id, chunk_uuid, chunk_type, "
        "chunk_text, chunk_ordinal) VALUES (?, ?, ?, ?, ?, ?)",
        (
            file_id,
            project_id,
            "00000000-0000-4000-8000-000000000001",
            "docstring",
            "stale placeholder chunk",
            1,
        ),
    )
    db._commit()
    assert (
        int(
            db._fetchone(
                "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
                (file_id,),
            )["c"]
        )
        == 1
    )

    from code_analysis.commands.update_indexes_analyzer import analyze_file

    analyze_file(
        database=db,
        file_path=py,
        project_id=project_id,
        root_path=tmp_path,
        force=True,
    )
    n_chunks = db._fetchone(
        "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
        (file_id,),
    )
    assert n_chunks is not None
    assert int(n_chunks["c"]) == 0
