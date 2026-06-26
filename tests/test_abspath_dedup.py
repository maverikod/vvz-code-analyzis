"""
Tests for absolute-path deduplication in files table and worker path convention.

Duplicate relative/absolute rows are merged by the file watcher (_deduplicate_absolute_paths).
The indexer and vectorizer process canonical rows (including normalized absolute paths in
files.path); they do not hard-skip absolute paths.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import multiprocessing
import uuid
from pathlib import Path
from typing import Iterator, cast
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_client.client import DatabaseClient

from code_analysis.core.file_watcher_pkg.multi_project_worker_scan import (
    _deduplicate_absolute_paths,
)
from code_analysis.core.indexing_worker_pkg import IndexingWorker
from code_analysis.core.indexing_worker_pkg.processing import process_cycle
from code_analysis.core.vectorization_worker_pkg.chunking import (
    _request_chunking_for_files,
)

from tests.sqlite_in_process_legacy_facade import SqliteLegacyRpcFacade
from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


@pytest.fixture
def dedup_db(tmp_path: Path) -> Iterator[SqliteLegacyRpcFacade]:
    """Return dedup db."""
    client = sqlite_inprocess_database_client(
        tmp_path / "dedup.db", backup_dir=tmp_path / "backups"
    )
    facade = SqliteLegacyRpcFacade(client)
    try:
        yield facade
    finally:
        facade.close()


def _insert_project(db: SqliteLegacyRpcFacade, root: Path, project_id: str) -> None:
    """Return insert project."""
    db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) "
        "VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(root.resolve()), "t"),
    )


def test_dedup_pair_keeps_earlier(
    dedup_db: SqliteLegacyRpcFacade, tmp_path: Path
) -> None:
    """Relative row has earlier updated_at; absolute duplicate is removed."""
    watch = tmp_path / "watch"
    root = watch / "proj"
    root.mkdir(parents=True)
    pid = str(uuid.uuid4())
    _insert_project(dedup_db, root, pid)
    rel = "src/a.py"
    abs_path = str((root / rel).resolve())
    fid_rel = str(uuid.uuid4())
    fid_abs = str(uuid.uuid4())

    dedup_db._execute(
        "INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, "
        "has_docstring, needs_chunking, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 1, 0, 0, 0, julianday('2019-01-01'), julianday('2019-01-01'))",
        (fid_rel, pid, rel, rel),
    )
    dedup_db._execute(
        "INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, "
        "has_docstring, needs_chunking, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 1, 0, 0, 0, julianday('2020-01-01'), julianday('2020-06-01'))",
        (fid_abs, pid, abs_path, rel),
    )

    n = _deduplicate_absolute_paths(dedup_db, watch)
    assert n == 1

    rows = dedup_db._fetchall(
        "SELECT id, path FROM files WHERE project_id = ? "
        "AND (deleted IS NULL OR deleted = 0) ORDER BY path",
        (pid,),
    )
    assert len(rows) == 1
    assert rows[0]["path"] == rel


def test_dedup_pair_keeps_abs_if_earlier(
    dedup_db: SqliteLegacyRpcFacade, tmp_path: Path
) -> None:
    """Absolute row is canonical (earlier updated_at); relative duplicate removed."""
    watch = tmp_path / "watch"
    root = watch / "proj"
    root.mkdir(parents=True)
    pid = str(uuid.uuid4())
    _insert_project(dedup_db, root, pid)
    rel = "lib/b.py"
    abs_path = str((root / rel).resolve())
    fid_rel = str(uuid.uuid4())
    fid_abs = str(uuid.uuid4())

    dedup_db._execute(
        "INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, "
        "has_docstring, needs_chunking, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 1, 0, 0, 0, julianday('2020-01-01'), julianday('2020-06-01'))",
        (fid_rel, pid, rel, rel),
    )
    dedup_db._execute(
        "INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, "
        "has_docstring, needs_chunking, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 1, 0, 0, 0, julianday('2019-01-01'), julianday('2019-01-01'))",
        (fid_abs, pid, abs_path, rel),
    )

    n = _deduplicate_absolute_paths(dedup_db, watch)
    assert n == 1

    rows = dedup_db._fetchall(
        "SELECT path FROM files WHERE project_id = ? "
        "AND (deleted IS NULL OR deleted = 0)",
        (pid,),
    )
    assert len(rows) == 1
    assert rows[0]["path"] == rel


def test_dedup_lone_abs_fixed(dedup_db: SqliteLegacyRpcFacade, tmp_path: Path) -> None:
    """Verify test dedup lone abs fixed."""
    watch = tmp_path / "watch"
    root = watch / "solo"
    root.mkdir(parents=True)
    pid = str(uuid.uuid4())
    _insert_project(dedup_db, root, pid)
    rel = "only.py"
    abs_path = str((root / rel).resolve())
    fid = str(uuid.uuid4())
    dedup_db._execute(
        "INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, "
        "has_docstring, needs_chunking, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 1, 0, 0, 0, julianday('now'), julianday('now'))",
        (fid, pid, abs_path, rel),
    )

    assert _deduplicate_absolute_paths(dedup_db, watch) == 1
    row = dedup_db._fetchone(
        "SELECT path, relative_path FROM files WHERE project_id = ?", (pid,)
    )
    assert row is not None
    assert row["path"] == rel
    assert row["relative_path"] == rel


def test_dedup_outside_root_skipped(
    dedup_db: SqliteLegacyRpcFacade, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify test dedup outside root skipped."""
    watch = tmp_path / "watch"
    root = watch / "proj"
    root.mkdir(parents=True)
    pid = str(uuid.uuid4())
    _insert_project(dedup_db, root, pid)
    fid = str(uuid.uuid4())
    dedup_db._execute(
        "INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, "
        "has_docstring, needs_chunking, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 1, 0, 0, 0, julianday('now'), julianday('now'))",
        (fid, pid, "/etc/hosts", None),
    )

    caplog.set_level(
        "WARNING",
        logger="code_analysis.core.file_watcher_pkg.multi_project_worker_scan",
    )
    n = _deduplicate_absolute_paths(dedup_db, watch)
    assert n == 0
    assert "[ABSPATH_DEDUP]" in caplog.text
    assert "outside project root" in caplog.text


def _make_indexer_mock_for_abspath(
    projects: list[dict],
    files_per_project: dict[str, list[dict]],
    batch_size: int,
) -> MagicMock:
    """Like tests.test_indexing_worker._make_mock_database plus root_path + execute_batch."""

    def execute(sql: str, params=None, transaction_id=None, **kwargs):
        """Execute the command."""
        sql_lower = sql.strip().lower()
        if "project_activity_locks" in sql_lower:
            return {"affected_rows": 1}
        if "select 1" in sql_lower:
            return {"data": [{"1": 1}]}
        if "count(*)" in sql_lower and "files" in sql_lower:
            total = sum(
                len(files_per_project.get(p["project_id"], [])) for p in projects
            )
            return {"data": [{"count": total}]}
        if "inner join projects" in sql_lower and "group by" in sql_lower:
            return {"data": projects}
        if "select id, path, project_id" in sql_lower and params:
            project_id = str(params[0]) if params and params[0] is not None else ""
            limit = params[1] if len(params) > 1 else batch_size
            files = list(files_per_project.get(project_id) or [])
            if "updated_at desc" in sql_lower:

                def _sort_file_row(row: dict) -> tuple:
                    """Return sort file row."""
                    raw = row.get("updated_at", 0)
                    try:
                        ufv = float(raw)
                    except TypeError, ValueError:
                        ufv = 0.0
                    rid = row.get("id")
                    sid = str(rid) if rid is not None else ""
                    return (ufv, sid)

                files.sort(key=_sort_file_row, reverse=True)
            return {"data": files[:limit]}
        if "select root_path from projects" in sql_lower and params:
            return {"data": [{"root_path": "/tmp/proj-root"}]}
        return {"data": []}

    mock = MagicMock()
    mock.execute = execute
    mock.execute_batch = MagicMock()
    mock.select = MagicMock(return_value=[])
    mock.index_file = MagicMock(return_value={"success": True})
    mock.connect = MagicMock()
    mock.disconnect = MagicMock()
    return mock


@pytest.mark.asyncio
async def test_indexer_processes_abspath(tmp_path: Path) -> None:
    """Normalized absolute path in files.path: indexer calls index_file (no hard-skip)."""
    batch_size = 5
    projects = [{"project_id": "proj-x"}]
    abs_path = "/tmp/proj-root/src/abs_only.py"
    files = [
        {
            "id": 99,
            "path": abs_path,
            "project_id": "proj-x",
            "updated_at": 2.0,
            "editing_pid": None,
        },
    ]
    mock_db = _make_indexer_mock_for_abspath(projects, {"proj-x": files}, batch_size)
    worker = IndexingWorker(
        db_path=tmp_path / "test.db",
        config_path=str(tmp_path / "config.json"),
        batch_size=batch_size,
        poll_interval=0,
    )
    worker._stop_event = multiprocessing.Event()

    with patch(
        "code_analysis.core.database_client.factory.create_worker_database_client",
        return_value=mock_db,
    ):

        async def run_then_stop():
            """Return run then stop."""
            await asyncio.sleep(0.35)
            worker._stop_event.set()

        stop_task = asyncio.create_task(run_then_stop())
        await process_cycle(worker, poll_interval=1)
        await stop_task

    mock_db.index_file.assert_called_once()
    call_args = mock_db.index_file.call_args
    assert call_args[0][0] == abs_path
    assert call_args[0][1] == "proj-x"


@pytest.mark.asyncio
async def test_vectorizer_resolves_abspath(dedup_db: SqliteLegacyRpcFacade) -> None:
    """Absolute path in files.path: vectorizer resolves path (no hard-skip)."""
    self = MagicMock()
    self._stop_event = MagicMock()
    self._stop_event.is_set.return_value = False
    self.svo_client_manager = None
    self.faiss_manager = None
    self.min_chunk_length = 30
    self.log_timing = False
    self.docs_markdown_embeddings_enabled = True
    self.chunk_set_overrides = None

    file_row = {
        "id": "f1",
        "project_id": "p1",
        "path": "/home/abs/c.py",
    }
    with patch(
        "code_analysis.core.vectorization_worker_pkg.chunking.resolve_indexed_file_path",
        return_value=None,
    ) as res_mock:
        n = await _request_chunking_for_files(
            self, cast(DatabaseClient, dedup_db), [file_row]
        )
    res_mock.assert_called_once_with(file_row)
    assert n == 0
