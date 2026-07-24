"""
Tests for the whole-project exclusive lock gate on the file watcher's periodic
scan (bug 88f06abc gap: ``scan_watch_dir`` discovered a project by its
``projectid`` UUID and could call ``relocate_project_root_after_disk_move`` on
divergence without ever checking ``project_exclusive_locks``, so the watcher
could race an in-flight ``rename_project`` and violate the whole-project-lock
invariant).

``scan_watch_dir`` now checks ``is_project_exclusively_locked`` for every
discovered project, before ``try_acquire_project_activity``'s own lease and
before any mutation of that project this cycle; a locked project is added to
``skipped_projects`` and skipped for the whole cycle (no relocate, no queueing),
mirroring the existing soft-deleted-project skip idiom.

These tests exercise the real per-project loop in ``scan_watch_dir`` (real
``discover_projects_in_directory`` over real ``tmp_path`` project directories
with real ``projectid`` files) and stub out the surrounding DB/relocate/queue
machinery, then cut the run short right after the loop (a controlled,
internally-caught exception from a monkeypatched ``merge_watch_ignore_patterns``)
so the heavy disk-scan/bulk-sync half of the function never has to be modeled.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from code_analysis.core.file_watcher_pkg import multi_project_worker_scan as scan_mod
from code_analysis.core.file_watcher_pkg.multi_project_worker_specs import (
    WatchDirSpec,
)

_LOCKED_ID = "11111111-1111-4111-8111-111111111111"
_UNLOCKED_ID = "22222222-2222-4222-8222-222222222222"

_CUTOFF_MARKER = "test-cutoff-after-per-project-loop"


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


@pytest.fixture
def _scan_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    """Build a real two-project watch dir plus the stubs ``scan_watch_dir``
    needs to run its per-project loop without touching a real database or the
    (irrelevant, heavier) disk-scan/bulk-sync half of the function.

    Returns:
        Dict of test handles: ``watch_dir``, ``spec``, ``database``,
        ``locked_root``, ``unlocked_root``, ``is_locked_calls``,
        ``get_project_calls``, ``relocate_mock``.
    """
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()

    locked_root = watch_dir / "locked_proj"
    locked_root.mkdir()
    _write_projectid(locked_root, _LOCKED_ID, "locked test project")

    unlocked_root = watch_dir / "unlocked_proj"
    unlocked_root.mkdir()
    _write_projectid(unlocked_root, _UNLOCKED_ID, "unlocked test project")

    database = MagicMock()
    database.execute = MagicMock(return_value={"data": [], "affected_rows": 1})

    is_locked_calls: list[str] = []

    def _fake_is_locked(db: Any, project_id: str) -> bool:
        """Report only ``_LOCKED_ID`` as exclusively locked."""
        is_locked_calls.append(project_id)
        return project_id == _LOCKED_ID

    monkeypatch.setattr(scan_mod, "is_project_exclusively_locked", _fake_is_locked)

    # Bypass DB-backed soft-delete partitioning entirely (unrelated to this gate).
    monkeypatch.setattr(
        scan_mod,
        "partition_discovered_projects_by_db_soft_delete",
        lambda db, discovered: (discovered, set()),
    )

    # try_acquire_project_activity / release_project_activity are the watcher's
    # OWN short lease (unrelated table, see project_exclusive_lock.py module
    # docstring) - stub them so a project that passes the new lock gate can
    # proceed through the rest of the per-project block deterministically.
    try_acquire_mock = MagicMock(return_value=True)
    monkeypatch.setattr(scan_mod, "try_acquire_project_activity", try_acquire_mock)
    monkeypatch.setattr(scan_mod, "release_project_activity", MagicMock())

    get_project_calls: list[str] = []

    def _fake_get_project(db: Any, project_id: str) -> Dict[str, Any]:
        """Return a minimal existing-project row with a stale root_path so the
        relocate-by-UUID branch is exercised for whichever project reaches it.
        """
        get_project_calls.append(project_id)
        return {
            "id": project_id,
            "root_path": "/stale/old/location",
            "name": "n",
            "comment": None,
            "watch_dir_id": None,
        }

    monkeypatch.setattr(scan_mod, "get_project", _fake_get_project)
    monkeypatch.setattr(
        scan_mod,
        "resolve_project_root_absolute_str",
        MagicMock(return_value="/stale/old/location"),
    )
    monkeypatch.setattr(scan_mod, "refresh_project_metadata_from_projectid", MagicMock())

    relocate_mock = MagicMock(return_value=True)
    monkeypatch.setattr(scan_mod, "relocate_project_root_after_disk_move", relocate_mock)

    # Cut the run short right after the per-project loop: scan_watch_dir wraps
    # its whole body in a broad try/except that logs+counts an error and still
    # returns stats normally, so raising here from the (locally-imported)
    # ignore-merge helper is a clean, in-contract way to stop before the
    # unrelated disk-scan/bulk-sync half without faking that half's behavior.
    def _cutoff(*_a: Any, **_k: Any) -> Any:
        """Abort the scan right after the per-project loop under test."""
        raise RuntimeError(_CUTOFF_MARKER)

    monkeypatch.setattr(
        "code_analysis.core.watch_dir_settings.merge_watch_ignore_patterns",
        _cutoff,
    )

    spec = WatchDirSpec(watch_dir=watch_dir, watch_dir_id="wd-1", ignore_patterns=())

    return {
        "watch_dir": watch_dir,
        "spec": spec,
        "database": database,
        "locked_root": locked_root,
        "unlocked_root": unlocked_root,
        "is_locked_calls": is_locked_calls,
        "get_project_calls": get_project_calls,
        "relocate_mock": relocate_mock,
        "try_acquire_mock": try_acquire_mock,
    }


def _run_scan(env: Dict[str, Any], tmp_path: Path) -> Dict[str, Any]:
    """Invoke ``scan_watch_dir`` against ``env`` and return its stats dict.

    Args:
        env: Fixture handles from ``_scan_env``.
        tmp_path: Pytest tmp dir, used for the lock-file directory.

    Returns:
        The stats dict ``scan_watch_dir`` returns (the cutoff exception is
        swallowed internally, incrementing ``errors`` by one).
    """
    return scan_mod.scan_watch_dir(
        env["spec"],
        MagicMock(),  # processor: unused before the cutoff
        env["database"],
        (),  # global_ignore_patterns
        tmp_path / "locks",
        12345,  # pid
    )


def test_scan_skips_exclusively_locked_project_before_relocate(
    _scan_env: Dict[str, Any], tmp_path: Path
) -> None:
    """A locked discovered project is skipped: no get_project, no relocate."""
    env = _scan_env

    _run_scan(env, tmp_path)

    assert _LOCKED_ID in env["is_locked_calls"]
    # The lock gate fires before the try: block that calls get_project, so the
    # locked project is never touched at all this cycle.
    assert _LOCKED_ID not in env["get_project_calls"]
    relocated_ids = [c.args[1] for c in env["relocate_mock"].call_args_list]
    assert _LOCKED_ID not in relocated_ids


def test_scan_still_relocates_unlocked_project(
    _scan_env: Dict[str, Any], tmp_path: Path
) -> None:
    """Sanity: an unlocked, diverged project is still relocated as before the
    gate was added (the gate must not over-skip)."""
    env = _scan_env

    _run_scan(env, tmp_path)

    assert _UNLOCKED_ID in env["is_locked_calls"]
    assert _UNLOCKED_ID in env["get_project_calls"]
    relocated_ids = [c.args[1] for c in env["relocate_mock"].call_args_list]
    assert relocated_ids == [_UNLOCKED_ID]


def test_scan_checks_lock_before_watcher_staging_lease(
    _scan_env: Dict[str, Any], tmp_path: Path
) -> None:
    """The lock gate must run before try_acquire_project_activity (the
    watcher's own, unrelated short lease) so a locked project never even takes
    the watcher_staging lease."""
    env = _scan_env

    _run_scan(env, tmp_path)

    staging_calls = [c.args[1] for c in env["try_acquire_mock"].call_args_list]
    assert _LOCKED_ID not in staging_calls
    assert _UNLOCKED_ID in staging_calls
