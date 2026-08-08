"""
Regression tests: a renamed project directory still resolves (bug 5da73265).

Every resolution strategy in ``resolve_project_root_absolute_str`` derived
candidate FOLDER NAMES from the ``projects`` row (``root_path`` / ``name``). An
out-of-band ``mv`` of the directory invalidated all of them at once, so every
DB-backed command died with "Cannot resolve absolute project root", quoting a
path that no longer existed -- while ``list_projects``, which scans disk and
reads each ``projectid``, happily reported the new location for the same id.
``repair_database`` could not help either: it needs the same broken resolution
before it starts.

The resolver now falls back to that same identity lookup and then heals the
stale row, so the desync repairs itself on first use.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from code_analysis.core.project_root_path import (
    find_project_root_by_projectid,
    resolve_project_root_absolute_str,
    resync_project_root_path_row,
)

_PROJECT_ID = "11111111-2222-4333-8444-555555555555"


class _StubDatabase:
    """Minimal stand-in exposing the bits the resolver touches."""

    def __init__(self, watch_dirs: List[str], row: Dict[str, Any]) -> None:
        """Store the watch dirs to enumerate and the single projects row."""
        self._watch_dirs = watch_dirs
        self.row = row
        self.executed: List[tuple] = []

    def select(self, table: str, where: Dict[str, Any] | None = None) -> List[Dict]:
        """Return the projects row; other tables are not read via select here."""
        if table == "projects":
            return [dict(self.row)]
        return []

    def _fetchall(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Serve watch_dir_paths rows the way the resolver actually reads them.

        ``fetch_all_watch_dir_absolute_paths`` prefers ``_fetchall`` with a
        server-instance-scoped SELECT; a stub that only offers ``select`` would
        silently return nothing and make these tests pass for the wrong reason.
        """
        if "watch_dir_paths" in sql:
            return [
                {"watch_dir_id": f"wd-{i}", "absolute_path": p}
                for i, p in enumerate(self._watch_dirs)
            ]
        return []

    def execute(self, sql: str, params: tuple = ()) -> None:
        """Record UPDATEs so a test can assert the row was healed."""
        self.executed.append((sql, params))
        if sql.strip().upper().startswith("UPDATE PROJECTS") and len(params) >= 2:
            self.row["root_path"] = params[0]
            self.row["name"] = params[1]


def _make_project_dir(parent: Path, folder: str, project_id: str) -> Path:
    """Create a project directory carrying a ``projectid`` file."""
    root = parent / folder
    root.mkdir(parents=True)
    (root / "projectid").write_text(
        json.dumps({"id": project_id, "description": "fixture"}), encoding="utf-8"
    )
    return root


def test_find_project_root_by_projectid_locates_a_renamed_directory(
    tmp_path: Path,
) -> None:
    """Identity lookup finds the folder regardless of what it is called now."""
    watch = tmp_path / "watch"
    watch.mkdir()
    _make_project_dir(watch, "some-other-project", "99999999-9999-4999-8999-999999999999")
    renamed = _make_project_dir(watch, "renamed-after-the-fact", _PROJECT_ID)
    db = _StubDatabase([str(watch)], {"id": _PROJECT_ID, "root_path": "old-name"})

    found = find_project_root_by_projectid(db, _PROJECT_ID)

    assert found == str(renamed.resolve())


def test_find_project_root_by_projectid_returns_empty_when_absent(
    tmp_path: Path,
) -> None:
    """No directory carries this id, so nothing is guessed."""
    watch = tmp_path / "watch"
    watch.mkdir()
    _make_project_dir(watch, "unrelated", "99999999-9999-4999-8999-999999999999")
    db = _StubDatabase([str(watch)], {"id": _PROJECT_ID, "root_path": "old-name"})

    assert find_project_root_by_projectid(db, _PROJECT_ID) == ""


def test_resolver_recovers_after_an_out_of_band_rename(tmp_path: Path) -> None:
    """Bug 5da73265: the stored folder name is gone, the project still resolves."""
    watch = tmp_path / "watch"
    watch.mkdir()
    renamed = _make_project_dir(watch, "science-assistant", _PROJECT_ID)
    row = {
        "id": _PROJECT_ID,
        "root_path": "scientific_research_large_galaxy_smbh",
        "name": "scientific_research_large_galaxy_smbh",
        "watch_dir_id": "wd-0",
    }
    db = _StubDatabase([str(watch)], row)

    resolved = resolve_project_root_absolute_str(
        project_id=_PROJECT_ID,
        root_path_stored=row["root_path"],
        watch_dir_id="wd-0",
        project_name=row["name"],
        database=db,
        require_exists=True,
    )

    assert resolved == str(renamed.resolve())


def test_resolver_heals_the_stale_row_so_the_next_call_is_direct(
    tmp_path: Path,
) -> None:
    """The discovery is written back: stored_root_path stops naming a dead path."""
    watch = tmp_path / "watch"
    watch.mkdir()
    _make_project_dir(watch, "science-assistant", _PROJECT_ID)
    row = {
        "id": _PROJECT_ID,
        "root_path": "old_name",
        "name": "old_name",
        "watch_dir_id": "wd-0",
    }
    db = _StubDatabase([str(watch)], row)

    resolve_project_root_absolute_str(
        project_id=_PROJECT_ID,
        root_path_stored=row["root_path"],
        watch_dir_id="wd-0",
        project_name=row["name"],
        database=db,
        require_exists=True,
    )

    assert any("UPDATE projects" in sql for sql, _ in db.executed), db.executed
    assert row["root_path"] == "science-assistant"
    assert row["name"] == "science-assistant"


def test_identity_fallback_is_not_used_when_the_path_need_not_exist(
    tmp_path: Path,
) -> None:
    """create/save-new flows must not be handed some other existing folder.

    ``require_exists=False`` means "resolve where this project WILL live", so
    searching the disk for an existing directory would answer a different
    question.
    """
    watch = tmp_path / "watch"
    watch.mkdir()
    _make_project_dir(watch, "already-there", _PROJECT_ID)
    db = _StubDatabase([str(watch)], {"id": _PROJECT_ID, "root_path": ""})

    resolved = resolve_project_root_absolute_str(
        project_id=_PROJECT_ID,
        root_path_stored="",
        watch_dir_id="wd-0",
        project_name=None,
        database=db,
        require_exists=False,
    )

    assert resolved == ""
    assert not db.executed


def test_resync_failure_never_propagates(tmp_path: Path) -> None:
    """A failed bookkeeping UPDATE must not break the caller's command."""
    watch = tmp_path / "watch"
    watch.mkdir()
    renamed = _make_project_dir(watch, "renamed", _PROJECT_ID)

    class _BrokenDatabase(_StubDatabase):
        def execute(self, sql: str, params: tuple = ()) -> None:
            raise RuntimeError("read-only replica")

    db = _BrokenDatabase([str(watch)], {"id": _PROJECT_ID, "root_path": "old"})

    assert resync_project_root_path_row(db, _PROJECT_ID, str(renamed)) is False

    resolved = resolve_project_root_absolute_str(
        project_id=_PROJECT_ID,
        root_path_stored="old",
        watch_dir_id="wd-0",
        project_name="old",
        database=db,
        require_exists=True,
    )
    assert resolved == str(renamed.resolve())
