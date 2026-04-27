"""
Project-cycle stage behavior (Step 0 re-embed, Step 1 chunking, Step 2 FAISS/vector_id).

Mocks cover step-11 scenarios: Step 0 empty or failure must not skip Step 1;
per-project isolation; ordered processing across projects.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker
from code_analysis.core.vectorization_worker_pkg import VectorizationWorker
from code_analysis.core.vectorization_worker_pkg.processing_cycle_projects import (
    process_projects_in_cycle,
)


def _worker(tmp_path: Path, db_path: Path) -> VectorizationWorker:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        '{"database": {"type": "sqlite", "config": {"path": "%s"}}}' % db_path
    )
    return VectorizationWorker(
        db_path=db_path,
        faiss_dir=tmp_path / "faiss",
        vector_dim=384,
        config_path=str(cfg),
        svo_client_manager=None,
        max_files_per_pass=10,
        batch_size=5,
    )


def _seed_docstring_file(db: CodeDatabase, tmp_path: Path, project_id: str) -> int:
    mod = tmp_path / "mod.py"
    mod.write_text(
        '"""Module docstring long enough for chunking minimum length rules."""\n'
        "x = 1\n",
        encoding="utf-8",
    )
    file_id = db.add_file(
        path=str(mod.resolve()),
        lines=len(mod.read_text(encoding="utf-8").splitlines()),
        last_modified=mod.stat().st_mtime,
        has_docstring=True,
        project_id=project_id,
    )
    db._execute("UPDATE files SET needs_chunking = 1 WHERE id = ?", (file_id,))
    db._commit()
    return int(file_id)


@pytest.mark.asyncio
async def test_step0_empty_result_step1_still_runs(tmp_path: Path) -> None:
    """Step 0 returns no work; Step 1 chunking query and request still run."""
    db_path = tmp_path / "cycle_stages_a.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    project_id = db.get_or_create_project(root_path=str(tmp_path), name="p_a")
    _seed_docstring_file(db, tmp_path, project_id)

    worker = _worker(tmp_path, db_path)
    worker._stop_event = MagicMock()
    worker._stop_event.is_set.return_value = False

    req = AsyncMock(return_value=1)
    with patch(
        "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
        "process_chunks_missing_embedding_params",
        new_callable=AsyncMock,
        return_value=(0, 0),
    ), patch(
        "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
        "process_embedding_ready_chunks",
        new_callable=AsyncMock,
        return_value=(0, 0),
    ), patch.object(worker, "_request_chunking_for_files", req):
        await process_projects_in_cycle(
            worker,
            db,
            [
                {
                    "project_id": project_id,
                    "root_path": str(tmp_path),
                    "pending_count": 1,
                }
            ],
            cycle_id="c1",
            cycle_count=1,
            chunks_total_at_start=1,
            total_processed=0,
            total_errors=0,
        )

    req.assert_awaited_once()
    args, _ = req.await_args
    assert args[0] is db
    rows = args[1]
    assert len(rows) >= 1
    assert rows[0].get("project_id") == project_id
    db.close()


@pytest.mark.asyncio
async def test_step0_exception_logged_step1_continues(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Step 0 raises; log names stage + project_id; Step 1 chunking still invoked."""
    import logging

    caplog.set_level(logging.ERROR)
    db_path = tmp_path / "cycle_stages_b.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    project_id = db.get_or_create_project(root_path=str(tmp_path), name="p_b")
    _seed_docstring_file(db, tmp_path, project_id)

    worker = _worker(tmp_path, db_path)
    worker._stop_event = MagicMock()
    worker._stop_event.is_set.return_value = False

    req = AsyncMock(return_value=1)
    with patch(
        "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
        "process_chunks_missing_embedding_params",
        new_callable=AsyncMock,
        side_effect=RuntimeError("simulated step0 failure"),
    ), patch(
        "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
        "process_embedding_ready_chunks",
        new_callable=AsyncMock,
        return_value=(0, 0),
    ), patch.object(worker, "_request_chunking_for_files", req):
        await process_projects_in_cycle(
            worker,
            db,
            [
                {
                    "project_id": project_id,
                    "root_path": str(tmp_path),
                    "pending_count": 1,
                }
            ],
            cycle_id="c2",
            cycle_count=1,
            chunks_total_at_start=1,
            total_processed=0,
            total_errors=0,
        )

    req.assert_awaited_once()
    err_text = caplog.text
    assert "[PROJECT_CYCLE STEP 0]" in err_text
    assert "existing chunks embedding params failed" in err_text
    assert project_id in err_text
    db.close()


@pytest.mark.asyncio
async def test_step0_failure_on_first_project_does_not_block_second(
    tmp_path: Path,
) -> None:
    """Two projects: Step 0 fails for the first only; second still completes Step 0."""
    db_path = tmp_path / "cycle_stages_c.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    p1 = db.get_or_create_project(root_path=str(tmp_path / "a"), name="p1")
    p2 = db.get_or_create_project(root_path=str(tmp_path / "b"), name="p2")
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "b").mkdir(exist_ok=True)
    _seed_docstring_file(db, tmp_path / "a", p1)
    _seed_docstring_file(db, tmp_path / "b", p2)

    worker = _worker(tmp_path, db_path)
    worker._stop_event = MagicMock()
    worker._stop_event.is_set.return_value = False

    req = AsyncMock(return_value=1)
    with patch(
        "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
        "process_chunks_missing_embedding_params",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("first project step0"), (0, 0)],
    ), patch(
        "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
        "process_embedding_ready_chunks",
        new_callable=AsyncMock,
        return_value=(0, 0),
    ), patch.object(worker, "_request_chunking_for_files", req):
        await process_projects_in_cycle(
            worker,
            db,
            [
                {
                    "project_id": p1,
                    "root_path": str(tmp_path / "a"),
                    "pending_count": 1,
                },
                {
                    "project_id": p2,
                    "root_path": str(tmp_path / "b"),
                    "pending_count": 1,
                },
            ],
            cycle_id="c3",
            cycle_count=1,
            chunks_total_at_start=2,
            total_processed=0,
            total_errors=0,
        )

    assert req.await_count == 2
    db.close()


@pytest.mark.asyncio
async def test_step1_failure_on_first_project_second_still_chunks(
    tmp_path: Path,
) -> None:
    """Later projects are not starved when an earlier project's Step 1 raises."""
    db_path = tmp_path / "cycle_stages_d.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    p1 = db.get_or_create_project(root_path=str(tmp_path / "c"), name="pc")
    p2 = db.get_or_create_project(root_path=str(tmp_path / "d"), name="pd")
    (tmp_path / "c").mkdir(exist_ok=True)
    (tmp_path / "d").mkdir(exist_ok=True)
    _seed_docstring_file(db, tmp_path / "c", p1)
    _seed_docstring_file(db, tmp_path / "d", p2)

    worker = _worker(tmp_path, db_path)
    worker._stop_event = MagicMock()
    worker._stop_event.is_set.return_value = False

    req = AsyncMock(side_effect=[RuntimeError("chunking failed"), 1])
    with patch(
        "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
        "process_chunks_missing_embedding_params",
        new_callable=AsyncMock,
        return_value=(0, 0),
    ), patch(
        "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
        "process_embedding_ready_chunks",
        new_callable=AsyncMock,
        return_value=(0, 0),
    ), patch.object(worker, "_request_chunking_for_files", req):
        await process_projects_in_cycle(
            worker,
            db,
            [
                {
                    "project_id": p1,
                    "root_path": str(tmp_path / "c"),
                    "pending_count": 1,
                },
                {
                    "project_id": p2,
                    "root_path": str(tmp_path / "d"),
                    "pending_count": 1,
                },
            ],
            cycle_id="c4",
            cycle_count=1,
            chunks_total_at_start=2,
            total_processed=0,
            total_errors=0,
        )

    assert req.await_count == 2
    db.close()


@pytest.mark.asyncio
async def test_step1_creates_chunks_integration(tmp_path: Path) -> None:
    """Step 1 persists code_chunks for indexed docstring files (no Step 0 mocks)."""
    db_path = tmp_path / "cycle_stages_e.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    project_id = db.get_or_create_project(root_path=str(tmp_path), name="p_e")
    file_id = _seed_docstring_file(db, tmp_path, project_id)

    worker = _worker(tmp_path, db_path)
    worker._stop_event = MagicMock()
    worker._stop_event.is_set.return_value = False

    with patch(
        "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
        "process_embedding_ready_chunks",
        new_callable=AsyncMock,
        return_value=(0, 0),
    ):
        await process_projects_in_cycle(
            worker,
            db,
            [
                {
                    "project_id": project_id,
                    "root_path": str(tmp_path),
                    "pending_count": 1,
                }
            ],
            cycle_id="c5",
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
    db.close()
