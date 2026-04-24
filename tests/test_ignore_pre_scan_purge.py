"""Tests for pre-scan ignore purge (DB-only) and logical-write batch."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

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
) -> tuple[int, Path]:
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

    temp_db._execute(
        "INSERT INTO code_duplicates (project_id, duplicate_hash, similarity) VALUES (?, ?, ?)",
        (pid, "h1", 1.0),
    )
    temp_db._commit()
    dup_row = temp_db._fetchone(
        "SELECT id FROM code_duplicates WHERE project_id = ?", (pid,)
    )
    assert dup_row
    dup_id = int(dup_row["id"])
    temp_db._execute(
        "INSERT INTO duplicate_occurrences (duplicate_id, file_id, start_line, end_line) "
        "VALUES (?, ?, ?, ?)",
        (dup_id, fid, 1, 1),
    )
    temp_db._execute(
        "INSERT INTO comprehensive_analysis_results "
        "(file_id, project_id, file_mtime, results_json, summary_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (fid, pid, 1.0, "{}", "{}"),
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
    ops = build_ignore_purge_sql_batch("proj-1", [1, 2, 3])
    assert ops[0][0].startswith("DROP TABLE IF EXISTS")
    assert "CREATE TEMP TABLE" in ops[1][0]
    assert any("duplicate_occurrences" in x[0] for x in ops)
    assert any("DELETE FROM files WHERE id IN" in x[0] for x in ops)


def test_build_ignore_purge_batch_skips_fts_when_disabled():
    ops = build_ignore_purge_sql_batch("proj-1", [1], include_code_content_fts=False)
    assert not any("code_content_fts" in x[0] for x in ops)


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
