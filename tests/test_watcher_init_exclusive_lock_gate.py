"""
Tests for the whole-project exclusive lock gate on the file watcher's
STARTUP path (bug 88f06abc gap, startup half): ``initialize_watch_dirs``
and its ``_verify_and_relocate_orphaned_projects`` helper each call
``relocate_project_root_after_disk_move`` on divergence without ever
checking ``project_exclusive_locks``, so server startup could race an
in-flight ``rename_project``/``emergency_unlock_project`` and violate the
whole-project-lock invariant - the same gap the periodic scan path had
before commit f41aba98 (see tests/test_watcher_scan_exclusive_lock_gate.py).

Both relocate call sites in ``multi_project_worker_init.py`` now check
``is_project_exclusively_locked`` immediately before relocating a given
project and skip/defer (never block, never error) when locked; the next
periodic scan relocates once the lock is released. All other startup
bookkeeping (watch_dir_id sync, project metadata refresh, new-project
insertion) is unaffected by the gate.

These tests exercise the real per-project discovery (real
``discover_projects_in_directory`` over real ``tmp_path`` project
directories with real ``projectid`` files) and stub out the surrounding
DB/relocate/soft-delete machinery, mirroring the sibling scan-path test's
approach.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from code_analysis.core.file_watcher_pkg import (
    multi_project_worker_init as init_mod,
)
from code_analysis.core.file_watcher_pkg import (
    watcher_soft_deleted_projects as soft_deleted_mod,
)
from code_analysis.core.file_watcher_pkg.multi_project_worker_specs import (
    WatchDirSpec,
)
from code_analysis.core.project_exclusive_lock import (
    acquire_project_exclusive_lock,
)

_LOCKED_ID = "33333333-3333-4333-8333-333333333333"
_UNLOCKED_ID = "44444444-4444-4444-8444-444444444444"


def _write_projectid(root: Path, project_id: str, description: str) -> None:
    """Write a ``projectid`` marker file so ``discover_projects_in_directory``
    picks ``root`` up as a real discovered project.

    Args:
        root: Project root directory (must already exist).
        project_id: UUID4 string identity for the project.
        description: Human-readable description stored in the marker.
    """
    (root / "projectid").write_text(
        json.dumps({"id": project_id, "description": description}),
        encoding="utf-8",
    )


def _make_two_projects(tmp_path: Path) -> Dict[str, Path]:
    """Build a real watch dir with one locked-id and one unlocked-id project.

    Args:
        tmp_path: Pytest tmp dir.

    Returns:
        Dict with ``watch_dir``, ``locked_root``, ``unlocked_root``.
    """
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    locked_root = watch_dir / "locked_proj"
    locked_root.mkdir()
    _write_projectid(locked_root, _LOCKED_ID, "locked test project")
    unlocked_root = watch_dir / "unlocked_proj"
    unlocked_root.mkdir()
    _write_projectid(unlocked_root, _UNLOCKED_ID, "unlocked test project")
    return {
        "watch_dir": watch_dir,
        "locked_root": locked_root,
        "unlocked_root": unlocked_root,
    }


class _RealLockDriver:
    """Minimal ``project_exclusive_locks`` backing store for the REAL lock module.

    Unlike ``_fake_is_locked_factory`` below (a string-keyed stub that
    replaces ``is_project_exclusively_locked`` entirely), this drives the
    REAL ``core.project_exclusive_lock`` functions end-to-end -- including
    their ``project_id`` type handling -- so a test using it exercises the
    exact bug f96faa07 failure mode: a raw ``uuid.UUID`` object reaching
    ``is_project_exclusively_locked`` must resolve the real lock row, not
    silently fail open.
    """

    def __init__(self) -> None:
        """Initialize the instance with an empty lock-row store."""
        self._rows: Dict[str, Dict[str, Any]] = {}

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the lock row for ``where["project_id"]`` if present."""
        assert table_name == "project_exclusive_locks"
        pid = str((where or {}).get("project_id") or "")
        row = self._rows.get(pid)
        return [dict(row)] if row else []

    def execute(
        self, sql: str, params: Optional[tuple] = None, transaction_id: Any = None
    ) -> Dict[str, Any]:
        """Emulate the two SQL statements the module issues."""
        if sql.startswith("INSERT INTO project_exclusive_locks"):
            project_id, locked_at, owner, reason = params  # type: ignore[misc]
            if project_id in self._rows:
                return {"affected_rows": 0}
            self._rows[project_id] = {
                "project_id": project_id,
                "locked_at": locked_at,
                "owner": owner,
                "reason": reason,
            }
            return {"affected_rows": 1}
        if sql.startswith("DELETE FROM project_exclusive_locks"):
            (project_id,) = params  # type: ignore[misc]
            existed = project_id in self._rows
            self._rows.pop(project_id, None)
            return {"affected_rows": 1 if existed else 0}
        raise AssertionError(f"unexpected SQL: {sql}")


def _fake_is_locked_factory(calls: List[str]) -> Any:
    """Build a stub reporting only ``_LOCKED_ID`` as exclusively locked.

    Args:
        calls: List that records every ``project_id`` checked.

    Returns:
        A callable matching ``is_project_exclusively_locked``'s signature.
    """

    def _fake_is_locked(_db: Any, project_id: str) -> bool:
        """Report only ``_LOCKED_ID`` as exclusively locked."""
        calls.append(project_id)
        return project_id == _LOCKED_ID

    return _fake_is_locked


# ---------------------------------------------------------------------------
# Site 1: _verify_and_relocate_orphaned_projects (phase 3, ~L186)
# ---------------------------------------------------------------------------


def test_orphan_relocate_skips_locked_project_before_relocate(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A locked orphan project is skipped: relocate is never called for it."""
    paths = _make_two_projects(tmp_path)
    database = MagicMock()

    is_locked_calls: List[str] = []
    monkeypatch.setattr(
        init_mod,
        "is_project_exclusively_locked",
        _fake_is_locked_factory(is_locked_calls),
    )

    def _fake_get_all_projects(_db: Any) -> List[Dict[str, Any]]:
        """Two DB rows whose root_path is outside every config watch dir."""
        return [
            {"id": _LOCKED_ID, "root_path": "/orphan/locked"},
            {"id": _UNLOCKED_ID, "root_path": "/orphan/unlocked"},
        ]

    monkeypatch.setattr(init_mod, "get_all_projects", _fake_get_all_projects)
    # Force "could not be resolved" for both rows so the function treats
    # both as outside config and proceeds to search for a projectid match.
    monkeypatch.setattr(
        init_mod,
        "_resolve_project_row_absolute_path",
        lambda *_a, **_k: None,
    )

    relocate_mock = MagicMock(return_value=True)
    monkeypatch.setattr(
        init_mod, "relocate_project_root_after_disk_move", relocate_mock
    )

    init_mod._verify_and_relocate_orphaned_projects(
        database,
        {"wd-1": paths["watch_dir"]},
        "EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)",
    )

    assert _LOCKED_ID in is_locked_calls
    assert _UNLOCKED_ID in is_locked_calls
    relocated_ids = [c.args[1] for c in relocate_mock.call_args_list]
    assert _LOCKED_ID not in relocated_ids


def test_orphan_relocate_still_relocates_unlocked_project(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Sanity: an unlocked orphan project is still relocated as before the
    gate was added (the gate must not over-skip)."""
    paths = _make_two_projects(tmp_path)
    database = MagicMock()

    is_locked_calls: List[str] = []
    monkeypatch.setattr(
        init_mod,
        "is_project_exclusively_locked",
        _fake_is_locked_factory(is_locked_calls),
    )

    def _fake_get_all_projects(_db: Any) -> List[Dict[str, Any]]:
        """Two DB rows whose root_path is outside every config watch dir."""
        return [
            {"id": _LOCKED_ID, "root_path": "/orphan/locked"},
            {"id": _UNLOCKED_ID, "root_path": "/orphan/unlocked"},
        ]

    monkeypatch.setattr(init_mod, "get_all_projects", _fake_get_all_projects)
    monkeypatch.setattr(
        init_mod,
        "_resolve_project_row_absolute_path",
        lambda *_a, **_k: None,
    )

    relocate_mock = MagicMock(return_value=True)
    monkeypatch.setattr(
        init_mod, "relocate_project_root_after_disk_move", relocate_mock
    )

    init_mod._verify_and_relocate_orphaned_projects(
        database,
        {"wd-1": paths["watch_dir"]},
        "EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)",
    )

    relocated_ids = [c.args[1] for c in relocate_mock.call_args_list]
    assert _UNLOCKED_ID in relocated_ids


# ---------------------------------------------------------------------------
# Site 2: initialize_watch_dirs main per-watch-dir loop (~L349)
# ---------------------------------------------------------------------------


def test_initialize_watch_dirs_skips_locked_project_relocate(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A locked, already-registered, diverged project is skipped: relocate is
    never called for it, but other startup bookkeeping still runs."""
    paths = _make_two_projects(tmp_path)
    database = MagicMock()
    database.execute = MagicMock(return_value={"data": [], "affected_rows": 1})

    monkeypatch.setattr(init_mod, "get_server_instance_id", lambda: "srv-1")

    is_locked_calls: List[str] = []
    monkeypatch.setattr(
        init_mod,
        "is_project_exclusively_locked",
        _fake_is_locked_factory(is_locked_calls),
    )

    # Real discovery (project_discovery.discover_projects_in_directory) finds
    # both projects at their real tmp_path roots; the DB rows below report a
    # stale root so the divergence branch (-> relocate) is exercised for both.
    stale_path = tmp_path / "stale" / "old_location"

    def _fake_resolve(_proj: Any, _db: Any, *, require_exists: bool = False) -> Path:
        """Always report the same stale absolute root for the DB row."""
        return stale_path

    monkeypatch.setattr(
        init_mod, "_resolve_project_row_absolute_path", _fake_resolve
    )

    def _fake_get_project(_db: Any, project_id: str) -> Dict[str, Any]:
        """Existing project row with a stale root_path (forces divergence)."""
        return {
            "id": project_id,
            "root_path": str(stale_path),
            "name": "n",
            "comment": None,
            "watch_dir_id": None,
        }

    monkeypatch.setattr(init_mod, "get_project", _fake_get_project)
    monkeypatch.setattr(
        init_mod, "refresh_project_metadata_from_projectid", MagicMock()
    )
    # Phase 3 (_verify_and_relocate_orphaned_projects) is not under test here.
    monkeypatch.setattr(init_mod, "get_all_projects", lambda _db: [])
    # Soft-delete partition is unrelated to this gate; pass every discovered
    # project through unchanged instead of exercising its own DB calls.
    monkeypatch.setattr(
        soft_deleted_mod,
        "partition_discovered_projects_by_db_soft_delete",
        lambda _db, discovered: (discovered, set()),
    )

    relocate_mock = MagicMock(return_value=True)
    monkeypatch.setattr(
        init_mod, "relocate_project_root_after_disk_move", relocate_mock
    )

    spec = WatchDirSpec(watch_dir=paths["watch_dir"], watch_dir_id="wd-1")

    init_mod.initialize_watch_dirs(database, [spec])

    assert _LOCKED_ID in is_locked_calls
    assert _UNLOCKED_ID in is_locked_calls
    relocated_ids = [c.args[1] for c in relocate_mock.call_args_list]
    assert _LOCKED_ID not in relocated_ids


def test_initialize_watch_dirs_still_relocates_unlocked_project(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Sanity: an unlocked, diverged project is still relocated during
    startup init as before the gate was added (the gate must not over-skip).
    """
    paths = _make_two_projects(tmp_path)
    database = MagicMock()
    database.execute = MagicMock(return_value={"data": [], "affected_rows": 1})

    monkeypatch.setattr(init_mod, "get_server_instance_id", lambda: "srv-1")

    is_locked_calls: List[str] = []
    monkeypatch.setattr(
        init_mod,
        "is_project_exclusively_locked",
        _fake_is_locked_factory(is_locked_calls),
    )

    stale_path = tmp_path / "stale" / "old_location"

    def _fake_resolve(_proj: Any, _db: Any, *, require_exists: bool = False) -> Path:
        """Always report the same stale absolute root for the DB row."""
        return stale_path

    monkeypatch.setattr(
        init_mod, "_resolve_project_row_absolute_path", _fake_resolve
    )

    def _fake_get_project(_db: Any, project_id: str) -> Dict[str, Any]:
        """Existing project row with a stale root_path (forces divergence)."""
        return {
            "id": project_id,
            "root_path": str(stale_path),
            "name": "n",
            "comment": None,
            "watch_dir_id": None,
        }

    monkeypatch.setattr(init_mod, "get_project", _fake_get_project)
    monkeypatch.setattr(
        init_mod, "refresh_project_metadata_from_projectid", MagicMock()
    )
    monkeypatch.setattr(init_mod, "get_all_projects", lambda _db: [])
    monkeypatch.setattr(
        soft_deleted_mod,
        "partition_discovered_projects_by_db_soft_delete",
        lambda _db, discovered: (discovered, set()),
    )

    relocate_mock = MagicMock(return_value=True)
    monkeypatch.setattr(
        init_mod, "relocate_project_root_after_disk_move", relocate_mock
    )

    spec = WatchDirSpec(watch_dir=paths["watch_dir"], watch_dir_id="wd-1")

    init_mod.initialize_watch_dirs(database, [spec])

    relocated_ids = [c.args[1] for c in relocate_mock.call_args_list]
    assert _UNLOCKED_ID in relocated_ids


# ---------------------------------------------------------------------------
# bug f96faa07: real uuid.UUID row ids (as a PostgreSQL driver actually
# returns for a UUID column) must still be gated correctly. These tests use
# the REAL ``is_project_exclusively_locked`` (imported into ``init_mod`` at
# module load, NOT monkeypatched here) backed by ``_RealLockDriver``, unlike
# every test above which replaces the gate with a string-keyed stub -- that
# stub-based approach is exactly why this regression shipped undetected: it
# never exercised the real function's project_id type handling.
# ---------------------------------------------------------------------------


def test_orphan_relocate_skips_locked_project_with_real_uuid_row_id(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A get_all_projects row whose ``id`` is a real uuid.UUID (not a str) for
    an exclusively-locked project must still be skipped, not relocated.

    RED on 546e35cc / 1.6.80: ``multi_project_worker_init.py`` line ~151
    passed the raw ``uuid.UUID`` straight to ``is_project_exclusively_locked``,
    which internally raised on the ``isinstance(project_id, str)`` check and
    silently fail-opened to "not locked" -- so the locked project WAS
    relocated (gate no-op). GREEN after the caller coerces with ``str()`` and
    the lock module itself is made UUID-tolerant (defense in depth).
    """
    paths = _make_two_projects(tmp_path)
    database = _RealLockDriver()
    # Seed a REAL lock row via the production acquire function, exactly as
    # rename_project / emergency_unlock_project would.
    acquire_project_exclusive_lock(
        database, _LOCKED_ID, owner="rename_project:test", reason="mid-rename"
    )

    def _fake_get_all_projects(_db: Any) -> List[Dict[str, Any]]:
        """DB rows whose ``id`` is a raw uuid.UUID, as PostgreSQL returns it."""
        return [
            {"id": uuid.UUID(_LOCKED_ID), "root_path": "/orphan/locked"},
            {"id": uuid.UUID(_UNLOCKED_ID), "root_path": "/orphan/unlocked"},
        ]

    monkeypatch.setattr(init_mod, "get_all_projects", _fake_get_all_projects)
    # Force "could not be resolved" for both rows so the function treats
    # both as outside config and proceeds to search for a projectid match.
    monkeypatch.setattr(
        init_mod,
        "_resolve_project_row_absolute_path",
        lambda *_a, **_k: None,
    )

    relocate_mock = MagicMock(return_value=True)
    monkeypatch.setattr(
        init_mod, "relocate_project_root_after_disk_move", relocate_mock
    )

    init_mod._verify_and_relocate_orphaned_projects(
        database,
        {"wd-1": paths["watch_dir"]},
        "EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)",
    )

    relocated_ids = [str(c.args[1]) for c in relocate_mock.call_args_list]
    assert _LOCKED_ID not in relocated_ids, (
        "locked project (real uuid.UUID row id) was relocated -- the "
        "exclusive-lock gate silently no-op'd (bug f96faa07)"
    )
    assert _UNLOCKED_ID in relocated_ids, (
        "gate over-skipped: the unlocked project (real uuid.UUID row id) "
        "must still be relocated as before"
    )
