"""
Watcher vs indexer project-scoped coordination (Step 25).

Uses test-only temp projects and SQLite via DatabaseClient + in-process RPC;
optional PostgreSQL parity when CODE_ANALYSIS_POSTGRES_TEST_DSN is set. Never uses vast_srv.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Iterator, Tuple

import pytest

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.transient import is_structured_retryable_error
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.drivers.postgres_run import (
    _adapt_sqlite_dml_for_postgres,
)
from code_analysis.core.file_watcher_pkg.multi_project_worker_scan import scan_watch_dir
from code_analysis.core.file_watcher_pkg.multi_project_worker_specs import WatchDirSpec
from code_analysis.core.file_watcher_pkg.processor import FileChangeProcessor, FileDelta
from code_analysis.core.file_watcher_pkg.processor_delta import compute_delta
from code_analysis.core.file_watcher_pkg.scanner import scan_directory
from code_analysis.core.path_normalization import NormalizedPath, normalize_file_path
from code_analysis.core.worker_project_activity import (
    get_project_activity,
    release_project_activity,
    try_acquire_project_activity,
)

from tests.sqlite_inprocess_database import sqlite_inprocess_database_client

# Project A = busy; project B = free (UUID v4-form strings for projectid files)
PA = "11111111-1111-4111-8111-1111111111a1"
PB = "22222222-2222-4222-8222-2222222222b2"

_LOG_PROC = "code_analysis.core.file_watcher_pkg.processor_queue"

_PG_ENV = "CODE_ANALYSIS_POSTGRES_TEST_DSN"


def _row_count(db: DatabaseClient, sql: str, params: Tuple[Any, ...] = ()) -> int:
    r = db.execute(sql, params)
    data = r.get("data", []) if isinstance(r, dict) else []
    if not data:
        return 0
    v = list(data[0].values())[0]
    return int(v)


def _file_cols_snapshot(
    db: DatabaseClient, project_id: str
) -> Tuple[int, int, int, int]:
    n_files = _row_count(
        db, "SELECT COUNT(*) AS c FROM files WHERE project_id = ?", (project_id,)
    )
    n_chunks = _row_count(
        db,
        "SELECT COUNT(*) AS c FROM code_chunks c JOIN files f ON f.id = c.file_id "
        "WHERE f.project_id = ?",
        (project_id,),
    )
    n_idx = _row_count(
        db,
        "SELECT COUNT(*) AS c FROM files WHERE project_id = ? AND needs_chunking = 1",
        (project_id,),
    )
    n_vec = 0
    if _row_count(db, "SELECT 1 AS c FROM sqlite_master WHERE name='file_vectors'") > 0:
        n_vec = _row_count(
            db,
            "SELECT COUNT(*) AS c FROM file_vectors v JOIN files f ON f.id = v.file_id "
            "WHERE f.project_id = ?",
            (project_id,),
        )
    return n_files, n_chunks, n_idx, n_vec


@pytest.fixture
def coord_client(tmp_path: Path) -> Iterator[DatabaseClient]:
    db_path = tmp_path / "wic.db"
    backup_dir = tmp_path / "backups"
    original = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    db = None
    try:
        db = sqlite_inprocess_database_client(db_path, backup_dir=backup_dir)
        yield db
    finally:
        if db is not None:
            db.disconnect()
        if original is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original


def _insert_project(client: DatabaseClient, root: Path, pid: str) -> None:
    client.execute(
        "INSERT OR REPLACE INTO projects (id, root_path, name, updated_at) "
        "VALUES (?, ?, ?, julianday('now'))",
        (pid, str(root.resolve()), root.name),
    )


def _create_projectid(root: Path, pid: str) -> None:
    (root / "projectid").write_text(
        json.dumps({"id": pid, "description": "wic test"}), encoding="utf-8"
    )


# --- Group 1: same-project mutation exclusion ---


def test_indexer_skips_project_owned_by_watcher(
    coord_client: DatabaseClient, tmp_path: Path
) -> None:
    """Indexer path does not mutate A while watcher holds a non-expired lease."""
    root = tmp_path
    proot = root / "pidx"
    proot.mkdir(parents=True, exist_ok=True)
    _insert_project(coord_client, proot, PA)
    # Seed one file row for A
    fpath = (proot / "x.py").resolve()
    fpath.write_text("# x", encoding="utf-8")
    mtime = fpath.stat().st_mtime
    coord_client.execute(
        "INSERT INTO files (path, lines, last_modified, has_docstring, project_id, "
        "created_at, updated_at) VALUES (?, 1, ?, 0, ?, julianday('now'), julianday('now'))",
        (str(fpath), mtime, PA),
    )
    before = _file_cols_snapshot(coord_client, PA)

    assert try_acquire_project_activity(
        coord_client, PA, "watcher", "w1", "watcher_staging", 300.0
    )
    # Simulate core indexing loop: would skip before SELECT batch
    assert not try_acquire_project_activity(
        coord_client, PA, "indexer", "i1", "indexer_processing", 120.0
    )
    # No indexer mutation: counts unchanged
    after = _file_cols_snapshot(coord_client, PA)
    assert after == before
    assert get_project_activity(coord_client, PA) is not None
    assert release_project_activity(coord_client, PA, "watcher", "w1")


def test_watcher_skips_project_owned_by_indexer(
    coord_client: DatabaseClient, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Watcher queue skips A when indexer holds the lease; DB unchanged for A."""
    root = tmp_path / "pwa"
    root.mkdir()
    _insert_project(coord_client, root, PA)
    fpath = (root / "only.py").resolve()
    fpath.write_text("v1", encoding="utf-8")
    mtime = fpath.stat().st_mtime
    n_before = _row_count(
        coord_client, "SELECT COUNT(*) AS c FROM files WHERE project_id = ?", (PA,)
    )

    assert try_acquire_project_activity(
        coord_client, PA, "indexer", "ix0", "indexer_processing", 300.0
    )
    try:
        proc = FileChangeProcessor(coord_client, [root.resolve()])
        delta = {
            PA: FileDelta(
                new_files=[("only.py", mtime, 2)],
                changed_files=[],
                deleted_files=[],
            )
        }
        with caplog.at_level(logging.INFO, logger=_LOG_PROC):
            stats = proc.queue_changes(
                root,
                delta,
                watcher_coord={
                    "database": coord_client,
                    "owner_id": "watcher-test-1",
                    "lease_ttl": 120.0,
                },
            )
        # Skipped: errors account for work units
        assert stats.get("errors", 0) >= 1
        n_after = _row_count(
            coord_client, "SELECT COUNT(*) AS c FROM files WHERE project_id = ?", (PA,)
        )
        assert n_after == n_before
        text = caplog.text
        assert (
            f"[WORKER_COORD] watcher skip project_id={PA}" in text
            or "watcher skip" in text
        )
    finally:
        release_project_activity(coord_client, PA, "indexer", "ix0")


def test_mutating_command_owner_blocks_watcher_and_indexer(
    coord_client: DatabaseClient,
) -> None:
    assert try_acquire_project_activity(
        coord_client, PA, "command", "c1", "command_mutation", 200.0
    )
    try:
        assert not try_acquire_project_activity(
            coord_client, PA, "watcher", "w1", "watcher_staging", 60.0
        )
        assert not try_acquire_project_activity(
            coord_client, PA, "indexer", "i1", "indexer_processing", 60.0
        )
    finally:
        release_project_activity(coord_client, PA, "command", "c1")


# --- Group 2: different projects ---


def test_watcher_owned_project_does_not_block_indexer_on_other_project(
    coord_client: DatabaseClient, tmp_path: Path
) -> None:
    a_root = tmp_path / "ar"
    b_root = tmp_path / "broot"
    a_root.mkdir(parents=True, exist_ok=True)
    b_root.mkdir(parents=True, exist_ok=True)
    coord_client.execute("DELETE FROM projects WHERE id IN (?, ?)", (PA, PB))
    _insert_project(coord_client, a_root, PA)
    _insert_project(coord_client, b_root, PB)
    try_acquire_project_activity(
        coord_client, PA, "watcher", "w1", "watcher_staging", 120.0
    )
    assert try_acquire_project_activity(
        coord_client, PB, "indexer", "i1", "indexer_processing", 60.0
    )
    coord_client.execute(
        "INSERT INTO files (path, lines, last_modified, has_docstring, project_id, "
        "created_at, updated_at) VALUES (?, 1, 1.0, 0, ?, julianday('now'), julianday('now'))",
        (str(b_root / "b_only.py"), PB),
    )
    assert (
        _row_count(
            coord_client, "SELECT COUNT(*) AS c FROM files WHERE project_id = ?", (PA,)
        )
        == 0
    )
    assert (
        _row_count(
            coord_client, "SELECT COUNT(*) AS c FROM files WHERE project_id = ?", (PB,)
        )
        == 1
    )
    release_project_activity(coord_client, PA, "watcher", "w1")
    release_project_activity(coord_client, PB, "indexer", "i1")


def test_indexer_owned_project_does_not_block_watcher_on_other_project(
    coord_client: DatabaseClient, tmp_path: Path
) -> None:
    a_root = tmp_path / "a2"
    b_root = tmp_path / "b2"
    a_root.mkdir(parents=True, exist_ok=True)
    b_root.mkdir(parents=True, exist_ok=True)
    _create_projectid(b_root, PB)
    coord_client.execute("DELETE FROM projects WHERE id IN (?, ?)", (PA, PB))
    _insert_project(coord_client, a_root, PA)
    _insert_project(coord_client, b_root, PB)
    try_acquire_project_activity(
        coord_client, PA, "indexer", "ix1", "indexer_processing", 120.0
    )
    fpath = (b_root / "watched.py").resolve()
    fpath.write_text("x", encoding="utf-8")
    m = fpath.stat().st_mtime
    proc = FileChangeProcessor(coord_client, [b_root])
    d = {
        PB: FileDelta(
            new_files=[("watched.py", m, len(fpath.read_bytes()))],
            changed_files=[],
            deleted_files=[],
        )
    }
    st = proc.queue_changes(
        b_root,
        d,
        watcher_coord={
            "database": coord_client,
            "owner_id": "w2",
            "lease_ttl": 200.0,
        },
    )
    assert st.get("new_files", 0) >= 1
    assert (
        _row_count(
            coord_client, "SELECT COUNT(*) AS c FROM files WHERE project_id = ?", (PB,)
        )
        == 1
    )
    assert (
        _row_count(
            coord_client, "SELECT COUNT(*) AS c FROM files WHERE project_id = ?", (PA,)
        )
        == 0
    )
    release_project_activity(coord_client, PA, "indexer", "ix1")


def test_busy_project_does_not_stop_whole_watch_dir_cycle(
    coord_client: DatabaseClient, tmp_path: Path
) -> None:
    coord_client.execute("DELETE FROM files WHERE project_id IN (?, ?)", (PA, PB))
    watch = tmp_path / "wd"
    watch.mkdir(parents=True)
    pa = watch / "pa"
    pb = watch / "pb"
    pa.mkdir()
    pb.mkdir()
    _create_projectid(pa, PA)
    _create_projectid(pb, PB)
    (pa / "a.py").write_text("# a", encoding="utf-8")
    (pb / "b.py").write_text("# b", encoding="utf-8")
    _insert_project(coord_client, pa, PA)
    _insert_project(coord_client, pb, PB)
    # Indexer blocks A; watcher should still process B
    try_acquire_project_activity(
        coord_client, PA, "indexer", "idx-block", "indexer_processing", 500.0
    )
    locks = tmp_path / "locks"
    locks.mkdir()
    wd_id = str(uuid.uuid4())
    coord_client.execute(
        "INSERT OR REPLACE INTO watch_dirs (id, name, updated_at) VALUES (?, ?, julianday('now'))",
        (wd_id, "wic-test-wd"),
    )
    spec = WatchDirSpec(watch_dir=watch, watch_dir_id=wd_id, ignore_patterns=())
    proc = FileChangeProcessor(coord_client, [watch])
    stats = scan_watch_dir(
        spec, proc, coord_client, (), locks, 424242, config_path=None
    )
    # B should have been file-registered; A skipped for queue
    assert stats.get("errors", 0) == 0
    n_b = _row_count(
        coord_client, "SELECT COUNT(*) AS c FROM files WHERE project_id = ?", (PB,)
    )
    assert n_b >= 1
    n_a = _row_count(
        coord_client, "SELECT COUNT(*) AS c FROM files WHERE project_id = ?", (PA,)
    )
    # A may be 0 (skipped before queue) or unchanged if pre-existing
    assert n_a == 0
    release_project_activity(coord_client, PA, "indexer", "idx-block")


# --- Group 3: staging / paths / ignore (feasible slice) ---


def test_filesystem_scan_groups_staged_delta_per_project(
    coord_client: DatabaseClient, tmp_path: Path
) -> None:
    """Scanned file dict keys drive per-project_id deltas (candidate sets)."""
    p1 = tmp_path / "p1"
    p2 = tmp_path / "p2"
    p1.mkdir()
    p2.mkdir()
    id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
    _create_projectid(p1, id1)
    _create_projectid(p2, id2)
    f1 = p1 / "a.py"
    f2 = p2 / "b.py"
    f1.write_text("1", encoding="utf-8")
    f2.write_text("2", encoding="utf-8")
    scanned = scan_directory(tmp_path, [tmp_path])
    dmap = compute_delta(coord_client, [tmp_path.resolve()], tmp_path, scanned)
    assert set(dmap.keys()) == {id1, id2}
    assert len(dmap[id1].new_files) >= 1
    assert len(dmap[id2].new_files) >= 1


def test_project_relative_path_is_posix_style(tmp_path: Path) -> None:
    pr = tmp_path / "pr"
    pr.mkdir()
    _create_projectid(pr, PA)
    fp = pr / "sub" / "f.py"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("x", encoding="utf-8")
    n = normalize_file_path(fp, watch_dirs=[tmp_path], project_root=pr)
    assert isinstance(n, NormalizedPath)
    assert (
        n.relative_path == "sub/f.py"
        or n.relative_path.replace("\\", "/") == "sub/f.py"
    )


def test_queue_batch_rejects_path_outside_project_root(
    coord_client: DatabaseClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    proot = tmp_path / "pout"
    proot.mkdir()
    _create_projectid(proot, PA)
    _insert_project(coord_client, proot, PA)
    outside = (tmp_path / "outside.py").resolve()
    outside.write_text("z", encoding="utf-8")
    m = outside.stat().st_mtime
    proc = FileChangeProcessor(coord_client, [proot])
    d = {
        PA: FileDelta(
            new_files=[(str(outside), m, 1)], changed_files=[], deleted_files=[]
        )
    }
    with caplog.at_level(logging.WARNING, logger=_LOG_PROC):
        st = proc.queue_changes(
            proot,
            d,
            watcher_coord={
                "database": coord_client,
                "owner_id": "ow",
                "lease_ttl": 200.0,
            },
        )
    assert "outside project root" in caplog.text or st.get("errors", 0) >= 1


def test_ignore_patterns_exclude_before_db_mutation(
    coord_client: DatabaseClient,
    tmp_path: Path,
) -> None:
    """Watch-dir ignore removes paths from the scan; no DB row for ignored .tmp."""
    pr = tmp_path / "ign"
    pr.mkdir()
    _create_projectid(pr, PA)
    _insert_project(coord_client, pr, PA)
    (pr / "keep.py").write_text("1", encoding="utf-8")
    (pr / "x.tmp").write_text("2", encoding="utf-8")
    scanned = scan_directory(
        tmp_path,
        [tmp_path],
        ignore_patterns=["*.tmp"],
        immediate_project_roots={pr.resolve()},
    )
    assert all(not str(p).endswith(".tmp") for p in scanned.keys())
    dmap = compute_delta(coord_client, [tmp_path.resolve()], tmp_path, scanned)
    empty = FileDelta(new_files=[], changed_files=[], deleted_files=[])
    paths = {x[0] for x in dmap.get(PA, empty).new_files}
    assert not any("x.tmp" in p for p in paths)


def test_stale_project_removed_from_queue_when_skipped_in_cycle(
    coord_client: DatabaseClient,
    tmp_path: Path,
) -> None:
    """When A is skipped, delta must not be queued for A (isolation from prior cycle)."""
    watch = tmp_path / "w2"
    watch.mkdir()
    pa = watch / "s1"
    pa.mkdir()
    _create_projectid(pa, PA)
    (pa / "f.py").write_text("u", encoding="utf-8")
    coord_client.execute("DELETE FROM files WHERE project_id = ?", (PA,))
    _insert_project(coord_client, pa, PA)
    try_acquire_project_activity(
        coord_client, PA, "indexer", "bl", "indexer_processing", 300.0
    )
    locks = tmp_path / "lk"
    locks.mkdir()
    spec = WatchDirSpec(watch_dir=watch, watch_dir_id=str(uuid.uuid4()))
    proc = FileChangeProcessor(coord_client, [watch])
    scan_watch_dir(spec, proc, coord_client, (), locks, 43, config_path=None)
    n = _row_count(
        coord_client, "SELECT COUNT(*) AS c FROM files WHERE project_id = ?", (PA,)
    )
    assert n == 0
    release_project_activity(coord_client, PA, "indexer", "bl")


# --- Group 4: watcher write ordering (integration on SQLite) ---


def test_watcher_order_inserts_before_updates_and_unmatched_unchanged(
    coord_client: DatabaseClient,
    tmp_path: Path,
) -> None:
    pr = tmp_path / "ord"
    pr.mkdir()
    _create_projectid(pr, PA)
    _insert_project(coord_client, pr, PA)
    old = (pr / "old.py").resolve()
    old.write_text("same", encoding="utf-8")
    m_old = old.stat().st_mtime
    coord_client.execute(
        "INSERT INTO files (path, lines, last_modified, has_docstring, project_id, "
        "created_at, updated_at, needs_chunking) VALUES (?, 1, ?, 0, ?, "
        "julianday('now'), julianday('now'), 0)",
        ("old.py", m_old, PA),
    )
    newp = (pr / "new.py").resolve()
    newp.write_text("n", encoding="utf-8")
    m_new = newp.stat().st_mtime
    # Touch old to same mtime path: compute_delta should not list as changed
    proc = FileChangeProcessor(coord_client, [pr])
    scanned = {
        str(newp.resolve()): {
            "path": newp,
            "mtime": m_new,
            "size": 1,
            "project_id": PA,
            "project_root": pr.resolve(),
        },
        str(old.resolve()): {
            "path": old,
            "mtime": m_old,
            "size": 4,
            "project_id": PA,
            "project_root": pr.resolve(),
        },
    }
    dmap = compute_delta(coord_client, [pr.resolve()], pr, scanned)
    fd = dmap[PA]
    new_paths = {t[0] for t in fd.new_files}
    assert "new.py" in new_paths
    assert not fd.changed_files
    assert not fd.deleted_files


# --- Group 5: idempotency and retry contract ---


def test_double_queue_same_new_file_does_not_duplicate_row(
    coord_client: DatabaseClient,
    tmp_path: Path,
) -> None:
    pr = tmp_path / "idp"
    pr.mkdir()
    _create_projectid(pr, PA)
    _insert_project(coord_client, pr, PA)
    fp = (pr / "d.py").resolve()
    fp.write_text("q", encoding="utf-8")
    m = fp.stat().st_mtime
    proc = FileChangeProcessor(coord_client, [pr])
    d = {PA: FileDelta(new_files=[("d.py", m, 1)], changed_files=[], deleted_files=[])}
    st1 = proc.queue_changes(
        pr,
        d,
        watcher_coord={"database": coord_client, "owner_id": "o1", "lease_ttl": 200.0},
    )
    st2 = proc.queue_changes(
        pr,
        d,
        watcher_coord={"database": coord_client, "owner_id": "o1", "lease_ttl": 200.0},
    )
    assert st1.get("new_files", 0) >= 1
    c = _row_count(
        coord_client,
        "SELECT COUNT(*) AS c FROM files WHERE project_id = ? AND path = ?",
        (PA, "d.py"),
    )
    assert c == 1
    # Second run: ON CONFLICT DO NOTHING — still one row
    assert c == 1


def test_rerun_watcher_does_not_delete_active_file(
    coord_client: DatabaseClient,
    tmp_path: Path,
) -> None:
    pr = tmp_path / "r1"
    pr.mkdir()
    _create_projectid(pr, PA)
    _insert_project(coord_client, pr, PA)
    fp = (pr / "keep.py").resolve()
    fp.write_text("k", encoding="utf-8")
    m = fp.stat().st_mtime
    proc = FileChangeProcessor(coord_client, [pr])
    d = {
        PA: FileDelta(new_files=[("keep.py", m, 1)], changed_files=[], deleted_files=[])
    }
    proc.queue_changes(
        pr,
        d,
        watcher_coord={"database": coord_client, "owner_id": "o2", "lease_ttl": 200.0},
    )
    proc.queue_changes(
        pr,
        d,
        watcher_coord={"database": coord_client, "owner_id": "o2", "lease_ttl": 200.0},
    )
    n_del = _row_count(
        coord_client,
        "SELECT COUNT(*) AS c FROM files WHERE project_id = ? AND deleted = 1",
        (PA,),
    )
    assert n_del == 0


def test_unknown_commit_outcome_is_not_treated_as_safe_logical_retry() -> None:
    assert (
        is_structured_retryable_error(
            {"retryable": True, "commit_outcome_unknown": True}
        )
        is False
    )


# --- Group 6: backend equivalence (optional Postgres) ---


def test_sqlite_code_database_lock_acquire_and_release_round_trip(
    coord_client: DatabaseClient,
) -> None:
    assert try_acquire_project_activity(
        coord_client, "w6-sql", "watcher", "w1", "watcher_staging", 30.0
    )
    assert release_project_activity(coord_client, "w6-sql", "watcher", "w1")
    assert get_project_activity(coord_client, "w6-sql") is None


@pytest.mark.skipif(
    not os.environ.get(_PG_ENV),
    reason=f"PostgreSQL DSN not set ({_PG_ENV})",
)
def test_postgres_try_acquire_lock_if_dsn_configured() -> None:
    """When a test Postgres URL exists, the same try_acquire contract applies."""
    dsn = os.environ[_PG_ENV].strip()
    d = create_driver("postgres", {"dsn": dsn})
    try:
        pid = f"pg-wic-{uuid.uuid4().hex[:12]}"
        assert try_acquire_project_activity(
            d, pid, "watcher", "w1", "watcher_staging", 30.0
        )
        assert release_project_activity(d, pid, "watcher", "w1")
    finally:
        d.disconnect()


def test_postgres_adapter_rewrites_julianday() -> None:
    out = _adapt_sqlite_dml_for_postgres(
        "UPDATE t SET x = 1, updated_at = julianday('now') WHERE id = ?"
    )
    assert "julianday" not in out.lower()
    assert "EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)" in out


# --- Group 7: auto-created project / no watcher daemon indexing ---


def test_watcher_scan_source_has_no_update_indexes_thread() -> None:
    here = Path(__file__).resolve().parent.parent
    src = here / "code_analysis/core/file_watcher_pkg/multi_project_worker_scan.py"
    text = src.read_text(encoding="utf-8")
    assert "UpdateIndexesMCPCommand" not in text
    assert "threading" not in text
    assert "Thread(" not in text


def test_auto_indexing_not_allowed_owner() -> None:
    from code_analysis.core import worker_project_activity as wpa

    assert "auto_indexing" not in wpa.ALLOWED_OWNER_TYPES


def test_watcher_log_documents_normal_indexer_path_for_new_projects() -> None:
    here = Path(__file__).resolve().parent.parent
    p = here / "code_analysis/core/file_watcher_pkg/multi_project_worker_scan.py"
    t = p.read_text(encoding="utf-8")
    assert "normal indexer" in t
    assert "auto_indexing" in t  # "no ... auto_indexing" log line


# --- Logging: WORKER_COORD ---


def test_indexer_skip_message_in_indexing_worker_source() -> None:
    here = Path(__file__).resolve().parent.parent
    p = here / "code_analysis/core/indexing_worker_pkg/processing.py"
    t = p.read_text(encoding="utf-8")
    assert "[WORKER_COORD] indexer skip" in t
    assert "indexer_processing" in t


def test_watcher_skip_log_uses_work_coord_prefix(
    coord_client: DatabaseClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = tmp_path / "wsk"
    root.mkdir()
    _create_projectid(root, PA)
    _insert_project(coord_client, root, PA)
    fp = root / "x.py"
    fp.write_text("#\n", encoding="utf-8")
    m = fp.stat().st_mtime
    try_acquire_project_activity(
        coord_client, PA, "indexer", "ix", "indexer_processing", 60.0
    )
    try:
        proc = FileChangeProcessor(coord_client, [root])
        d = {
            PA: FileDelta(
                new_files=[("x.py", m, 1)],
                changed_files=[],
                deleted_files=[],
            )
        }
        with caplog.at_level(logging.INFO, logger=_LOG_PROC):
            st = proc.queue_changes(
                root,
                d,
                watcher_coord={
                    "database": coord_client,
                    "owner_id": "w",
                    "lease_ttl": 60.0,
                },
            )
        assert st.get("errors", 0) >= 1
        assert "[WORKER_COORD] watcher skip" in caplog.text
        assert f"project_id={PA}" in caplog.text
    finally:
        release_project_activity(coord_client, PA, "indexer", "ix")
