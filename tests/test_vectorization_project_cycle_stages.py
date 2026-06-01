"""
Project-cycle stage behavior (Step 0 re-embed, Step 1 chunking, Step 2 FAISS/vector_id).

Mocks cover step-11 scenarios: Step 0 empty or failure must not skip Step 1;
per-project isolation; ordered processing across projects.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_client.objects.project import Project
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers
from code_analysis.core.vectorization_worker_pkg import VectorizationWorker
from code_analysis.core.vectorization_worker_pkg.processing_cycle_projects import (
    process_projects_in_cycle,
)

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("faiss") is None,
    reason="faiss-cpu or faiss-gpu is required",
)

_CYCLE_DB_NAME = "cycle.db"


def _sqlite_full_schema_client(tmp_path: Path) -> DatabaseClient:
    db_path = tmp_path / _CYCLE_DB_NAME
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    driver = create_driver(
        "sqlite", {"path": str(db_path), "backup_dir": str(backup_dir)}
    )
    handlers = RPCHandlers(driver)
    ipc = InProcessRpcClient(handlers)
    client = DatabaseClient(rpc_client=ipc)
    client.connect()
    client.sync_schema(get_schema_definition(), backup_dir=str(backup_dir))
    return client


def _seed_docstring_file(db: DatabaseClient, tmp_path: Path, project_id: str) -> str:
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
    db.execute("UPDATE files SET needs_chunking = 1 WHERE id = ?", (file_id,))
    return str(file_id)


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


@pytest.fixture(autouse=True)
def _sqlite_worker_env():
    original = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    yield
    if original is None:
        os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
    else:
        os.environ["CODE_ANALYSIS_DB_WORKER"] = original


@pytest.mark.asyncio
async def test_step0_empty_result_step1_still_runs(tmp_path: Path) -> None:
    """Step 0 returns no work; Step 1 chunking query and request still run."""
    db = _sqlite_full_schema_client(tmp_path)
    db_path = tmp_path / _CYCLE_DB_NAME
    try:
        pid = str(uuid.uuid4())
        db.create_project(
            Project(id=pid, root_path=str(tmp_path.resolve()), name="p_a")
        )
        project_id = pid
        _seed_docstring_file(db, tmp_path, project_id)

        worker = _worker(tmp_path, db_path)
        worker._stop_event = MagicMock()
        worker._stop_event.is_set.return_value = False

        req = AsyncMock(return_value=1)
        with (
            patch(
                "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
                "process_chunks_missing_embedding_params",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
            patch(
                "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
                "process_embedding_ready_chunks",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
            patch.object(worker, "_request_chunking_for_files", req),
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
    finally:
        db.disconnect()


@pytest.mark.asyncio
async def test_step0_exception_logged_step1_continues(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Step 0 raises; log names stage + project_id; Step 1 chunking still invoked."""
    import logging

    caplog.set_level(logging.ERROR)
    db = _sqlite_full_schema_client(tmp_path)
    db_path = tmp_path / _CYCLE_DB_NAME
    try:
        pid = str(uuid.uuid4())
        db.create_project(
            Project(id=pid, root_path=str(tmp_path.resolve()), name="p_b")
        )
        project_id = pid
        _seed_docstring_file(db, tmp_path, project_id)

        worker = _worker(tmp_path, db_path)
        worker._stop_event = MagicMock()
        worker._stop_event.is_set.return_value = False

        req = AsyncMock(return_value=1)
        with (
            patch(
                "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
                "process_chunks_missing_embedding_params",
                new_callable=AsyncMock,
                side_effect=RuntimeError("simulated step0 failure"),
            ),
            patch(
                "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
                "process_embedding_ready_chunks",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
            patch.object(worker, "_request_chunking_for_files", req),
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
    finally:
        db.disconnect()


@pytest.mark.asyncio
async def test_step0_failure_on_first_project_does_not_block_second(
    tmp_path: Path,
) -> None:
    """Two projects: Step 0 fails for the first only; second still completes Step 0."""
    db = _sqlite_full_schema_client(tmp_path)
    db_path = tmp_path / _CYCLE_DB_NAME
    try:
        p1 = str(uuid.uuid4())
        p2 = str(uuid.uuid4())
        db.create_project(
            Project(id=p1, root_path=str((tmp_path / "a").resolve()), name="p1")
        )
        db.create_project(
            Project(id=p2, root_path=str((tmp_path / "b").resolve()), name="p2")
        )
        (tmp_path / "a").mkdir(exist_ok=True)
        (tmp_path / "b").mkdir(exist_ok=True)
        _seed_docstring_file(db, tmp_path / "a", p1)
        _seed_docstring_file(db, tmp_path / "b", p2)

        worker = _worker(tmp_path, db_path)
        worker._stop_event = MagicMock()
        worker._stop_event.is_set.return_value = False

        req = AsyncMock(return_value=1)
        with (
            patch(
                "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
                "process_chunks_missing_embedding_params",
                new_callable=AsyncMock,
                side_effect=[RuntimeError("first project step0"), (0, 0)],
            ),
            patch(
                "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
                "process_embedding_ready_chunks",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
            patch.object(worker, "_request_chunking_for_files", req),
        ):
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
    finally:
        db.disconnect()


@pytest.mark.asyncio
async def test_step1_failure_on_first_project_second_still_chunks(
    tmp_path: Path,
) -> None:
    """Later projects are not starved when an earlier project's Step 1 raises."""
    db = _sqlite_full_schema_client(tmp_path)
    db_path = tmp_path / _CYCLE_DB_NAME
    try:
        p1 = str(uuid.uuid4())
        p2 = str(uuid.uuid4())
        db.create_project(
            Project(id=p1, root_path=str((tmp_path / "c").resolve()), name="pc")
        )
        db.create_project(
            Project(id=p2, root_path=str((tmp_path / "d").resolve()), name="pd")
        )
        (tmp_path / "c").mkdir(exist_ok=True)
        (tmp_path / "d").mkdir(exist_ok=True)
        _seed_docstring_file(db, tmp_path / "c", p1)
        _seed_docstring_file(db, tmp_path / "d", p2)

        worker = _worker(tmp_path, db_path)
        worker._stop_event = MagicMock()
        worker._stop_event.is_set.return_value = False

        req = AsyncMock(side_effect=[RuntimeError("chunking failed"), 1])
        with (
            patch(
                "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
                "process_chunks_missing_embedding_params",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
            patch(
                "code_analysis.core.vectorization_worker_pkg.processing_cycle_projects."
                "process_embedding_ready_chunks",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
            patch.object(worker, "_request_chunking_for_files", req),
        ):
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
    finally:
        db.disconnect()


def _fetch_count(client: DatabaseClient, sql: str, params: tuple) -> int:
    r = client.execute(sql, params)
    rows = r.get("data") or []
    if not rows:
        return 0
    row = rows[0]
    d = dict(row) if hasattr(row, "keys") else row
    key = "c" if "c" in d else next(iter(d))
    return int(d[key])


@pytest.mark.asyncio
async def test_step1_creates_chunks_integration(tmp_path: Path) -> None:
    """Step 1 persists code_chunks for indexed docstring files (no Step 0 mocks)."""
    db = _sqlite_full_schema_client(tmp_path)
    db_path = tmp_path / _CYCLE_DB_NAME
    try:
        pid = str(uuid.uuid4())
        db.create_project(
            Project(id=pid, root_path=str(tmp_path.resolve()), name="p_e")
        )
        project_id = pid
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

        cnt = _fetch_count(
            db,
            "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
            (file_id,),
        )
        assert cnt > 0
    finally:
        db.disconnect()
