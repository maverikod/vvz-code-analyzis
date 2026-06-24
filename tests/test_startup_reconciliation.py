"""
Tests for the file-watcher startup DB/disk reconciliation.

Covers the four ordered steps:
  1. build watch_dir -> project -> project_id table
  2. duplicate-id detection -> server stop + fatal
  3. orphan project purge (id not on disk)
  4. per-project missing-file marking

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from code_analysis.core.file_watcher_pkg import startup_reconciliation as sr
from code_analysis.core.file_watcher_pkg.startup_reconciliation import (
    DiscoveredProjectRow,
    StartupReconciliationFatal,
    _build_discovery_table,
    _find_duplicate_ids,
    _mark_missing_files_for_project,
    _purge_orphan_projects,
    _request_server_stop,
    run_startup_reconciliation,
)
from code_analysis.core.file_watcher_pkg.multi_project_worker_specs import WatchDirSpec


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _make_project_dir(watch_dir: Path, name: str, project_id: str) -> Path:
    """Create watch_dir/<name>/ with a valid projectid file."""
    proj = watch_dir / name
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "projectid").write_text(
        json.dumps({"id": project_id, "description": f"{name} project"}),
        encoding="utf-8",
    )
    return proj


def _spec(watch_dir: Path) -> WatchDirSpec:
    return WatchDirSpec(watch_dir=watch_dir, watch_dir_id=str(uuid.uuid4()))


class FakeDB:
    """Minimal worker DB facade for reconciliation unit tests."""

    def __init__(
        self,
        projects: Optional[List[Dict[str, Any]]] = None,
        files_by_project: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> None:
        self.projects = projects or []
        self.files_by_project = files_by_project or {}
        self.deleted_file_ids: List[Any] = []

    def execute(self, sql: str, params: Any = None, priority: int = 0) -> Dict[str, Any]:
        s = " ".join(sql.split())
        if s.startswith("SELECT id, root_path, name, watch_dir_id FROM projects"):
            return {"data": list(self.projects)}
        if s.startswith("SELECT id, path, relative_path FROM files"):
            pid = params[0]
            return {"data": list(self.files_by_project.get(pid, []))}
        if s.startswith("UPDATE files SET deleted = 1"):
            self.deleted_file_ids.append(params[0])
            return {"affected_rows": 1}
        return {"data": []}


# --------------------------------------------------------------------------- #
# Step 1 + 2: table + duplicate detection
# --------------------------------------------------------------------------- #


def test_build_discovery_table_lists_projects(tmp_path: Path) -> None:
    wd = tmp_path / "watch"
    wd.mkdir()
    id_a, id_b = str(uuid.uuid4()), str(uuid.uuid4())
    _make_project_dir(wd, "proj_a", id_a)
    _make_project_dir(wd, "proj_b", id_b)

    rows, hard_errors = _build_discovery_table([_spec(wd)])

    assert hard_errors == []
    found = {(r.project_id) for r in rows}
    assert found == {id_a, id_b}
    assert all(r.watch_dir.endswith("watch") for r in rows)


def test_find_duplicate_ids_flags_same_id_two_paths() -> None:
    dup = str(uuid.uuid4())
    rows = [
        DiscoveredProjectRow("/w1", "/w1/a", dup),
        DiscoveredProjectRow("/w2", "/w2/b", dup),
        DiscoveredProjectRow("/w1", "/w1/c", str(uuid.uuid4())),
    ]
    dups = _find_duplicate_ids(rows)
    assert set(dups) == {dup}
    assert len(dups[dup]) == 2


def test_find_duplicate_ids_unique_is_empty() -> None:
    rows = [
        DiscoveredProjectRow("/w1", "/w1/a", str(uuid.uuid4())),
        DiscoveredProjectRow("/w1", "/w1/b", str(uuid.uuid4())),
    ]
    assert _find_duplicate_ids(rows) == {}


def test_request_server_stop_signals_given_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: List[tuple] = []
    monkeypatch.setattr(sr.os, "kill", lambda pid, sig: captured.append((pid, sig)))
    _request_server_stop(424242)
    assert captured == [(424242, sr.signal.SIGTERM)]


@pytest.mark.asyncio
async def test_reconciliation_aborts_and_stops_server_on_cross_dir_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wd1 = tmp_path / "w1"
    wd2 = tmp_path / "w2"
    wd1.mkdir()
    wd2.mkdir()
    dup = str(uuid.uuid4())
    _make_project_dir(wd1, "proj_a", dup)
    _make_project_dir(wd2, "proj_b", dup)

    killed: List[tuple] = []
    monkeypatch.setattr(sr.os, "kill", lambda pid, sig: killed.append((pid, sig)))

    db = FakeDB()  # must NOT be touched: abort happens before DB work
    with pytest.raises(StartupReconciliationFatal):
        await run_startup_reconciliation(
            db, [_spec(wd1), _spec(wd2)], server_pid=555
        )

    assert killed == [(555, sr.signal.SIGTERM)]
    assert db.deleted_file_ids == []


# --------------------------------------------------------------------------- #
# Step 3: orphan project purge
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_purge_orphan_projects_deletes_only_unknown_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    on_disk = str(uuid.uuid4())
    orphan = str(uuid.uuid4())
    db = FakeDB(
        projects=[
            {"id": on_disk, "root_path": "keep", "name": "keep", "watch_dir_id": "w"},
            {"id": orphan, "root_path": "gone", "name": "gone", "watch_dir_id": "w"},
        ]
    )

    cleared: List[str] = []

    async def _fake_clear(database: Any, project_id: str) -> None:
        cleared.append(project_id)

    monkeypatch.setattr(
        "code_analysis.commands.clear_project_data_impl._clear_project_data_impl",
        _fake_clear,
    )

    purged = await _purge_orphan_projects(db, {on_disk})

    assert cleared == [orphan]
    assert [p["project_id"] for p in purged] == [orphan]


# --------------------------------------------------------------------------- #
# Step 4: per-project missing-file marking
# --------------------------------------------------------------------------- #


def test_mark_missing_files_marks_only_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    present = root / "pkg" / "present.py"
    present.write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setattr(
        sr, "_resolve_project_row_absolute_path", lambda proj, db, require_exists=True: root
    )

    db = FakeDB(
        files_by_project={
            "p1": [
                {"id": 1, "path": "pkg/present.py", "relative_path": "pkg/present.py"},
                {"id": 2, "path": "pkg/missing.py", "relative_path": "pkg/missing.py"},
            ]
        }
    )

    marked = _mark_missing_files_for_project(db, {"id": "p1"}, "strftime('now')")

    assert marked == 1
    assert db.deleted_file_ids == [2]
