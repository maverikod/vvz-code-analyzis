"""
Regression: docstring chunking must run without SVO so code_chunks are populated.

Previously Step 1 in processing_cycle_projects was gated on svo_client_manager, and
process_chunks returned early without SVO — leaving chunk_count at zero forever.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_analysis.commands.update_indexes_analyzer import analyze_file
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


def _open_schema_client(db_path: Path) -> DatabaseClient:
    backup_dir = db_path.parent / "backups"
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


def _fetch_sql_one_row(client: DatabaseClient, sql: str, params: tuple) -> dict | None:
    r = client.execute(sql, params)
    rows = r.get("data") if isinstance(r, dict) else None
    if not rows:
        return None
    row = rows[0]
    return dict(row) if hasattr(row, "keys") else row


def _fetch_count(client: DatabaseClient, sql: str, params: tuple) -> int:
    row = _fetch_sql_one_row(client, sql, params)
    if not row:
        return 0
    key = "c" if "c" in row else next(iter(row))
    return int(row[key])


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
async def test_process_projects_step1_chunks_without_svo(tmp_path: Path) -> None:
    """One vectorization project cycle creates code_chunks when SVO is None."""
    db_path = tmp_path / "chunk_no_svo.db"
    db = _open_schema_client(db_path)
    try:
        project_id = str(uuid.uuid4())
        db.create_project(
            Project(id=project_id, root_path=str(tmp_path.resolve()), name="chunk_test")
        )
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
        db.execute(
            "UPDATE files SET needs_chunking = 0 WHERE id = ?",
            (file_id,),
        )

        cfg = tmp_path / "config.json"
        cfg.write_text(
            '{"database": {"type": "sqlite", "config": {"path": "%s"}}}' % db_path
        )

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

        assert (
            _fetch_count(
                db,
                "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
                (file_id,),
            )
            > 0
        )

        frow = _fetch_sql_one_row(
            db,
            "SELECT needs_chunking FROM files WHERE id = ?",
            (file_id,),
        )
        assert frow is not None
        assert frow.get("needs_chunking") in (0, None)
    finally:
        db.disconnect()


@pytest.mark.asyncio
async def test_regression_indexed_python_file_with_docstring_gets_code_chunks_row(
    tmp_path: Path,
) -> None:
    """
    Regression: file row has docstring metadata and needs_chunking=1, no chunks yet;
    one vectorization project cycle must insert into code_chunks (Step 1).
    """

    db_path = tmp_path / "chunk_regression.db"
    db = _open_schema_client(db_path)
    try:
        project_id = str(uuid.uuid4())
        db.create_project(
            Project(
                id=project_id,
                root_path=str(tmp_path.resolve()),
                name="chunk_regression",
            )
        )
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
        db.execute(
            "UPDATE files SET needs_chunking = 1 WHERE id = ?",
            (file_id,),
        )
        assert (
            _fetch_count(
                db,
                "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
                (file_id,),
            )
            == 0
        )

        cfg = tmp_path / "config.json"
        cfg.write_text(
            '{"database": {"type": "sqlite", "config": {"path": "%s"}}}' % db_path
        )

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

        assert (
            _fetch_count(
                db,
                "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
                (file_id,),
            )
            > 0
        )

        sample = _fetch_sql_one_row(
            db,
            "SELECT chunk_text, source_type FROM code_chunks WHERE file_id = ? LIMIT 1",
            (file_id,),
        )
        assert sample is not None
        st = (sample.get("source_type") or "").lower()
        assert "docstring" in st
        assert sample.get("chunk_text")
    finally:
        db.disconnect()


@pytest.mark.asyncio
async def test_analyze_file_mark_needs_chunking_clears_stale_chunks_by_path(
    tmp_path: Path,
) -> None:
    """analyze_file ends with mark_file_needs_chunking(absolute path) so stale chunks are removed."""

    db_path = tmp_path / "path_contract.db"
    db = _open_schema_client(db_path)
    try:
        project_id = str(uuid.uuid4())
        db.create_project(
            Project(id=project_id, root_path=str(tmp_path.resolve()), name="p")
        )
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
        db.execute(
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
        assert (
            _fetch_count(
                db,
                "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
                (file_id,),
            )
            == 1
        )

        analyze_file(
            database=db,
            file_path=py,
            project_id=project_id,
            root_path=tmp_path,
            force=True,
        )
        assert (
            _fetch_count(
                db,
                "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
                (file_id,),
            )
            == 0
        )
    finally:
        db.disconnect()
