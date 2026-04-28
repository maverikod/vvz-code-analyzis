"""Tests for pre-scan ignore purge (DB-only) and logical-write batch."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.core.database.base import CodeDatabase
from code_analysis.core.file_watcher_pkg.ignore_pre_scan_purge import (
    build_ignore_purge_sql_batch,
    collect_file_ids_to_purge_for_ignore_policy,
    list_non_ignored_code_files_under_root,
    run_pre_scan_ignore_purge_for_project,
)


@pytest.fixture
def temp_db(tmp_path):
    """CodeDatabase with full schema (sync_schema)."""
    db_path = tmp_path / "ignore_purge_test.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    driver_config = {
        "type": "sqlite",
        "config": {"path": str(db_path), "backup_dir": str(backup_dir)},
    }
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    db = CodeDatabase(driver_config)
    try:
        db.sync_schema()
        yield db
        db.close()
    finally:
        if original_env is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env
        if db_path.exists():
            try:
                db_path.unlink(missing_ok=True)
            except OSError:
                pass


def _insert_project(db: CodeDatabase, tmp_path: Path) -> str:
    pid = str(uuid.uuid4())
    db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (pid, str(tmp_path), tmp_path.name),
    )
    db._commit()
    return pid


def _insert_file_in_project(
    db: CodeDatabase, tmp_path: Path, project_id: str, rel_name: str
) -> tuple[str, Path]:
    fp = tmp_path / rel_name
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("# x\n", encoding="utf-8")
    mtime = os.path.getmtime(fp)
    fid = db.add_file(
        path=str(fp.resolve()),
        lines=1,
        last_modified=mtime,
        has_docstring=False,
        project_id=project_id,
    )
    return fid, fp


def test_collect_file_ids_respects_fnmatch_ignore(temp_db, tmp_path):
    patterns = ["**/purge_me_*.py"]
    pid = _insert_project(temp_db, tmp_path)
    _insert_file_in_project(temp_db, tmp_path, pid, "purge_me_x.py")
    _, fp_keep = _insert_file_in_project(temp_db, tmp_path, pid, "keep_me.py")
    assert fp_keep.name == "keep_me.py"
    ids = collect_file_ids_to_purge_for_ignore_policy(
        temp_db, pid, patterns, allowed_venv_py_files=None, ignore_exception_files=None
    )
    assert len(ids) == 1


def test_collect_file_ids_respects_ignore_exceptions(temp_db, tmp_path):
    patterns = ["**/exc_*.py"]
    pid = _insert_project(temp_db, tmp_path)
    _, fp_exc = _insert_file_in_project(temp_db, tmp_path, pid, "exc_keep.py")
    exc_set = {fp_exc.resolve()}
    ids = collect_file_ids_to_purge_for_ignore_policy(
        temp_db,
        pid,
        patterns,
        allowed_venv_py_files=None,
        ignore_exception_files=exc_set,
    )
    assert ids == []


def test_purge_removes_duplicate_occurrences_and_comprehensive(temp_db, tmp_path):
    patterns = ["**/zdup_*.py"]
    pid = _insert_project(temp_db, tmp_path)
    fid, _ = _insert_file_in_project(temp_db, tmp_path, pid, "zdup_one.py")

    dup_id = str(uuid.uuid4())
    temp_db._execute(
        "INSERT INTO code_duplicates (id, project_id, duplicate_hash, similarity) "
        "VALUES (?, ?, ?, ?)",
        (dup_id, pid, "h1", 1.0),
    )
    temp_db._commit()
    temp_db._execute(
        "INSERT INTO duplicate_occurrences (id, duplicate_id, file_id, start_line, end_line) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), dup_id, fid, 1, 1),
    )
    temp_db._execute(
        "INSERT INTO comprehensive_analysis_results "
        "(id, file_id, project_id, file_mtime, results_json, summary_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), fid, pid, 1.0, "{}", "{}"),
    )
    temp_db._commit()

    n = run_pre_scan_ignore_purge_for_project(
        temp_db,
        pid,
        patterns,
        allowed_venv_py_files=None,
        ignore_exception_files=None,
        config_path=None,
    )
    assert n == 1

    occ = temp_db._fetchone(
        "SELECT COUNT(*) AS c FROM duplicate_occurrences WHERE file_id = ?", (fid,)
    )
    assert int(occ["c"]) == 0
    car = temp_db._fetchone(
        "SELECT COUNT(*) AS c FROM comprehensive_analysis_results WHERE file_id = ?",
        (fid,),
    )
    assert int(car["c"]) == 0
    frow = temp_db._fetchone("SELECT id FROM files WHERE id = ?", (fid,))
    assert frow is None


def test_build_batch_starts_with_temp_table():
    ids = [
        "aaaaaaaa-bbbb-4ccc-dddd-000000000001",
        "aaaaaaaa-bbbb-4ccc-dddd-000000000002",
        "aaaaaaaa-bbbb-4ccc-dddd-000000000003",
    ]
    ops = build_ignore_purge_sql_batch("proj-1", ids)
    assert ops[0][0].startswith("DROP TABLE IF EXISTS")
    assert "CREATE TEMP TABLE" in ops[1][0]
    assert any("duplicate_occurrences" in x[0] for x in ops)
    assert any("DELETE FROM files WHERE id IN" in x[0] for x in ops)


def test_build_ignore_purge_batch_skips_fts_when_disabled():
    ops = build_ignore_purge_sql_batch(
        "proj-1",
        ["aaaaaaaa-bbbb-4ccc-dddd-000000000001"],
        include_code_content_fts=False,
    )
    assert not any("code_content_fts" in x[0] for x in ops)
    assert not any("rowid" in x[0] for x in ops)


def test_list_non_ignored_prunes_explicit_subtree(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    vis = root / "visible.py"
    vis.write_text("x=1\n", encoding="utf-8")
    subtree = root / "skip_sub"
    subtree.mkdir()
    (subtree / "secret.py").write_text("y=1\n", encoding="utf-8")
    patterns = ["**/skip_sub/**"]
    paths = list_non_ignored_code_files_under_root(root, patterns)
    names = {p.name for p in paths}
    assert "visible.py" in names
    assert "secret.py" not in names


def test_list_non_ignored_keeps_exception_pattern_inside_ignored_dir(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    keep = root / "src" / "generated" / "keep.py"
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_text("x=1\n", encoding="utf-8")
    blocked = keep.parent / "drop.py"
    blocked.write_text("x=2\n", encoding="utf-8")

    paths = list_non_ignored_code_files_under_root(
        root,
        ["**/src/generated/**"],
        ignore_exception_patterns=["**/src/generated/keep.py"],
    )
    as_set = {p.resolve() for p in paths}
    assert keep.resolve() in as_set
    assert blocked.resolve() not in as_set


def test_pre_scan_ignore_purge_respects_exception_and_keeps_file_on_disk(
    temp_db, tmp_path
):
    pid = _insert_project(temp_db, tmp_path)
    patterns = ["**/src/generated/**"]

    fid_a, path_a = _insert_file_in_project(temp_db, tmp_path, pid, "src/a.py")
    fid_b, path_b = _insert_file_in_project(
        temp_db, tmp_path, pid, "src/generated/b.py"
    )
    fid_keep, path_keep = _insert_file_in_project(
        temp_db, tmp_path, pid, "src/generated/keep.py"
    )

    n = run_pre_scan_ignore_purge_for_project(
        temp_db,
        pid,
        patterns,
        allowed_venv_py_files=None,
        ignore_exception_files={path_keep.resolve()},
        ignore_exception_patterns=["**/src/generated/keep.py"],
        config_path=None,
    )

    assert n == 1
    assert path_b.exists() is True
    assert temp_db._fetchone("SELECT id FROM files WHERE id = ?", (fid_b,)) is None
    assert temp_db._fetchone("SELECT id FROM files WHERE id = ?", (fid_a,)) is not None
    assert (
        temp_db._fetchone("SELECT id FROM files WHERE id = ?", (fid_keep,)) is not None
    )


def test_collect_file_ids_uses_relative_posix_pattern_policy(temp_db, tmp_path):
    pid = _insert_project(temp_db, tmp_path)
    fid_a, _ = _insert_file_in_project(temp_db, tmp_path, pid, "src/a.py")
    fid_b, _ = _insert_file_in_project(temp_db, tmp_path, pid, "src/generated/b.py")
    fid_keep, _ = _insert_file_in_project(
        temp_db, tmp_path, pid, "src/generated/keep.py"
    )
    ids = collect_file_ids_to_purge_for_ignore_policy(
        temp_db,
        pid,
        ["**/src/generated/**"],
        ignore_exception_patterns=["**/src/generated/keep.py"],
    )
    assert fid_b in ids
    assert fid_keep not in ids
    assert fid_a not in ids


def test_pre_scan_ignore_purge_rollback_on_mid_batch_error(temp_db, tmp_path):
    pid = _insert_project(temp_db, tmp_path)
    fid_b, _ = _insert_file_in_project(temp_db, tmp_path, pid, "src/generated/b.py")
    temp_db._execute(
        "INSERT INTO code_chunks (file_id, project_id, chunk_uuid, chunk_type, chunk_text, chunk_ordinal, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, julianday('now'))",
        (fid_b, pid, str(uuid.uuid4()), "DocBlock", "chunk", 0),
    )
    temp_db._commit()

    broken_program = {
        "batches": [
            [
                ("DELETE FROM code_chunks WHERE file_id = ?", (fid_b,)),
                ("THIS IS NOT SQL", ()),
                ("DELETE FROM files WHERE id = ?", (fid_b,)),
            ]
        ]
    }
    with patch(
        "code_analysis.core.file_watcher_pkg.ignore_pre_scan_purge.build_ignore_purge_logical_write_program",
        return_value=broken_program,
    ):
        with pytest.raises(Exception):
            run_pre_scan_ignore_purge_for_project(
                temp_db,
                pid,
                ["**/src/generated/**"],
                config_path=None,
            )

    file_row = temp_db._fetchone("SELECT id FROM files WHERE id = ?", (fid_b,))
    chunk_row = temp_db._fetchone(
        "SELECT COUNT(*) AS c FROM code_chunks WHERE file_id = ?",
        (fid_b,),
    )
    assert file_row is not None
    assert int(chunk_row["c"]) == 1
