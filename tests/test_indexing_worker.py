"""
Unit tests for indexing worker: process_cycle calls index_file for needs_chunking=1,
respects batch size and project order.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.indexing_worker_pkg import IndexingWorker
from code_analysis.core.indexing_worker_pkg.processing import process_cycle


def _make_mock_database(
    projects: list[dict],
    files_per_project: dict[str, list[dict]],
    batch_size: int,
) -> MagicMock:
    """Build a mock DatabaseClient that returns given projects and file batches."""
    call_count = [0]  # mutable to share across invocations

    def execute(sql: str, params):
        call_count[0] += 1
        sql_lower = sql.strip().lower()
        if "select 1" in sql_lower:
            return None
        if "count(*)" in sql_lower and "files" in sql_lower:
            total = sum(
                len(files_per_project.get(p["project_id"], [])) for p in projects
            )
            return {"data": [{"count": total}]}
        if "distinct project_id" in sql_lower:
            return {"data": projects}
        if "select id, path, project_id" in sql_lower and params:
            project_id = params[0] if params else None
            limit = params[1] if len(params) > 1 else batch_size
            files = (files_per_project.get(project_id) or [])[:limit]
            return {"data": files}
        return None

    mock_index_file = MagicMock(return_value={"success": True})

    mock = MagicMock()
    mock.execute = execute
    mock.index_file = mock_index_file
    mock.connect = MagicMock()
    mock.disconnect = MagicMock()
    return mock


@pytest.mark.asyncio
async def test_process_cycle_calls_index_file_for_files_with_needs_chunking(tmp_path):
    """Process cycle discovers projects with needs_chunking=1 and calls index_file per file."""
    socket_path = str(tmp_path / "test.sock")
    batch_size = 5
    projects = [{"project_id": "proj-a"}]
    files = [
        {"id": 1, "path": "/repo/proj-a/src/foo.py", "project_id": "proj-a"},
        {"id": 2, "path": "/repo/proj-a/src/bar.py", "project_id": "proj-a"},
    ]
    files_per_project = {"proj-a": files}

    mock_db = _make_mock_database(projects, files_per_project, batch_size)
    worker = IndexingWorker(
        db_path=tmp_path / "test.db",
        socket_path=socket_path,
        batch_size=batch_size,
        poll_interval=0,
    )
    worker._stop_event = threading.Event()

    with patch(
        "code_analysis.core.database_client.client.DatabaseClient",
        return_value=mock_db,
    ):

        async def run_then_stop():
            await asyncio.sleep(0.3)
            worker._stop_event.set()

        stop_task = asyncio.create_task(run_then_stop())
        result = await process_cycle(worker, poll_interval=1)
        await stop_task

    assert result["indexed"] == 2
    assert result["errors"] == 0
    assert mock_db.index_file.call_count == 2
    calls = [
        c[0] for c in mock_db.index_file.call_args_list
    ]  # (path, project_id) positional
    assert ("/repo/proj-a/src/foo.py", "proj-a") in calls
    assert ("/repo/proj-a/src/bar.py", "proj-a") in calls


@pytest.mark.asyncio
async def test_process_cycle_respects_batch_size(tmp_path):
    """Process cycle requests at most batch_size files per project per cycle."""
    socket_path = str(tmp_path / "test.sock")
    batch_size = 2
    projects = [{"project_id": "p1"}]
    # 3 files available; batch_size=2 so only first 2 should be requested
    files = [
        {"id": 1, "path": "/p1/a.py", "project_id": "p1"},
        {"id": 2, "path": "/p1/b.py", "project_id": "p1"},
        {"id": 3, "path": "/p1/c.py", "project_id": "p1"},
    ]
    files_per_project = {"p1": files}

    mock_db = _make_mock_database(projects, files_per_project, batch_size)
    worker = IndexingWorker(
        db_path=tmp_path / "test.db",
        socket_path=socket_path,
        batch_size=batch_size,
        poll_interval=0,
    )
    worker._stop_event = threading.Event()

    with patch(
        "code_analysis.core.database_client.client.DatabaseClient",
        return_value=mock_db,
    ):

        async def run_then_stop():
            await asyncio.sleep(0.3)
            worker._stop_event.set()

        stop_task = asyncio.create_task(run_then_stop())
        await process_cycle(worker, poll_interval=1)
        await stop_task

    # Should have been called with limit batch_size (2) so only 2 files in first cycle
    assert mock_db.index_file.call_count == 2
    paths = [c[0][0] for c in mock_db.index_file.call_args_list]
    assert "/p1/a.py" in paths
    assert "/p1/b.py" in paths


@pytest.mark.asyncio
async def test_process_cycle_respects_project_order(tmp_path):
    """Process cycle processes projects in discovery order (DISTINCT project_id)."""
    socket_path = str(tmp_path / "test.sock")
    batch_size = 1
    # Two projects; order of processing should follow list order
    projects = [
        {"project_id": "first"},
        {"project_id": "second"},
    ]
    files_per_project = {
        "first": [{"id": 1, "path": "/first/one.py", "project_id": "first"}],
        "second": [{"id": 2, "path": "/second/two.py", "project_id": "second"}],
    }

    mock_db = _make_mock_database(projects, files_per_project, batch_size)
    worker = IndexingWorker(
        db_path=tmp_path / "test.db",
        socket_path=socket_path,
        batch_size=batch_size,
        poll_interval=0,
    )
    worker._stop_event = threading.Event()

    with patch(
        "code_analysis.core.database_client.client.DatabaseClient",
        return_value=mock_db,
    ):

        async def run_then_stop():
            await asyncio.sleep(0.5)
            worker._stop_event.set()

        stop_task = asyncio.create_task(run_then_stop())
        await process_cycle(worker, poll_interval=1)
        await stop_task

    assert mock_db.index_file.call_count == 2
    order = [
        c[0][1] for c in mock_db.index_file.call_args_list
    ]  # project_id is second positional
    assert order == ["first", "second"]


# --- Integration test: one cycle with real driver and real file ---


@pytest.mark.asyncio
@pytest.mark.integration
async def test_indexing_worker_one_cycle_integration(tmp_path):
    """Integration: set needs_chunking=1, run one indexing cycle, assert code_content and needs_chunking=0.

    Uses real CodeDatabase for schema and data, RPC server with index_file handler, and one cycle
    of the indexing worker. Requires CODE_ANALYSIS_DB_WORKER=1 so CodeDatabase uses direct SQLite.
    """
    import os
    import threading
    import time

    from tests.test_fixture_content import DEFAULT_TEST_FILE_CONTENT

    db_path = tmp_path / "idx.db"
    socket_path = str(tmp_path / "idx.sock")
    py_file = tmp_path / "test_index.py"
    py_file.write_text(DEFAULT_TEST_FILE_CONTENT, encoding="utf-8")

    orig_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

    try:
        from code_analysis.core.database import CodeDatabase
        from code_analysis.core.database_driver_pkg.driver_factory import create_driver
        from code_analysis.core.database_driver_pkg.request_queue import RequestQueue
        from code_analysis.core.database_driver_pkg.rpc_server import RPCServer
        from code_analysis.core.database_client.client import DatabaseClient
    except ImportError as e:
        pytest.skip(f"Integration test requires full driver stack: {e}")

    try:
        # Create DB with full schema and one project + file with needs_chunking=1
        driver_config = {"type": "sqlite", "config": {"path": str(db_path)}}
        db = CodeDatabase(driver_config)
        project_id = db.get_or_create_project(root_path=str(tmp_path), name="idx_test")
        file_id = db.add_file(
            path=str(py_file),
            lines=len(DEFAULT_TEST_FILE_CONTENT.splitlines()),
            last_modified=os.path.getmtime(py_file),
            has_docstring=True,
            project_id=project_id,
        )
        db._execute("UPDATE files SET needs_chunking = 1 WHERE id = ?", (file_id,))
        db._commit()
        db.close()

        # Start RPC server (same DB path; handler has index_file)
        request_queue = RequestQueue()
        driver = create_driver("sqlite", {"path": str(db_path)})
        server = RPCServer(driver, request_queue, socket_path)
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        try:
            client = DatabaseClient(socket_path=socket_path)
            client.connect()

            worker = IndexingWorker(
                db_path=db_path,
                socket_path=socket_path,
                batch_size=5,
                poll_interval=0,
            )
            worker._stop_event = threading.Event()

            async def stop_after_one_cycle():
                await asyncio.sleep(2.0)
                worker._stop_event.set()

            stop_task = asyncio.create_task(stop_after_one_cycle())
            result = await process_cycle(worker, poll_interval=1)
            await stop_task

            assert (
                result["indexed"] >= 1
            ), f"Expected at least one file indexed, got {result}"
            assert result["errors"] == 0, f"Expected no errors, got {result}"

            # needs_chunking cleared for the file
            r = client.execute(
                "SELECT needs_chunking FROM files WHERE id = ?", (file_id,)
            )
            data = r.get("data", []) if isinstance(r, dict) else []
            assert len(data) == 1, f"Expected one file row, got {r}"
            assert (
                data[0].get("needs_chunking") == 0
            ), f"Expected needs_chunking=0, got {data[0]}"

            # code_content populated for the file
            r2 = client.execute(
                "SELECT COUNT(*) as c FROM code_content WHERE file_id = ?", (file_id,)
            )
            data2 = r2.get("data", []) if isinstance(r2, dict) else []
            assert len(data2) == 1
            assert (
                data2[0].get("c", 0) >= 1
            ), f"Expected at least one code_content row, got {data2[0]}"

            client.disconnect()
        finally:
            server.stop()
            driver.disconnect()
            time.sleep(0.1)
    finally:
        if orig_env is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = orig_env
