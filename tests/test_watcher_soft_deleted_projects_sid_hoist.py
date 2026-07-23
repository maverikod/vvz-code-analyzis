"""
Tests for the cycle-level ``current_server_instance_id()`` hoist (bug 9f5d860e).

``partition_discovered_projects_by_db_soft_delete`` used to resolve the server
instance id once PER PROJECT inside its loop; hoisted to once per call so a
multi-project watch cycle no longer amplifies the (now-memoized, but still
non-free) resolver call N times per cycle.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from code_analysis.core.file_watcher_pkg import watcher_soft_deleted_projects as mod
from code_analysis.core.project_discovery import ProjectRoot


class _FakeProjectInfo:
    """Minimal stand-in for ``load_project_info`` return value: never deleted."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self.deleted = False
        self.processing_paused = False
        self.description = "test"


class _FakeDatabase:
    """
    Stub database: no ``sync_project_metadata_from_projectid`` attribute (so
    that call is skipped entirely, matching the "not soft-deleted" path) and
    ``execute`` always returns no matching rows (project not soft-deleted by
    root_path either).
    """

    def __init__(self) -> None:
        """Initialize the instance."""
        self.execute_calls = 0

    def execute(self, sql: str, params: Tuple[Any, ...], **kwargs: Any) -> List[Any]:
        """Record a call and return no matching rows."""
        self.execute_calls += 1
        return []


def _make_project_root(tmp_path: Path, name: str) -> ProjectRoot:
    """Build a discovered ``ProjectRoot`` under ``tmp_path`` for the test."""
    root = tmp_path / name
    root.mkdir()
    return ProjectRoot(
        root_path=root,
        project_id=f"pid-{name}",
        description="test",
        watch_dir=tmp_path,
    )


def test_current_server_instance_id_called_once_per_partition_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    3+ discovered projects, all reaching the DB soft-delete check -> the server
    instance id resolver is called exactly ONCE per
    ``partition_discovered_projects_by_db_soft_delete`` invocation (hoisted out
    of the per-project loop), not once per project.

    Strict equality (== 1, not <= N) so this fails on unfixed code: before the
    hoist, 3 discovered projects would drive the counter to 3.
    """
    monkeypatch.setattr(mod, "load_project_info", lambda root: _FakeProjectInfo())
    monkeypatch.setattr(mod, "get_project", lambda database, project_id: None)

    calls: Dict[str, int] = {"n": 0}

    def _counting_sid(**kwargs: Any) -> str:
        calls["n"] += 1
        return "sid-fixed"

    monkeypatch.setattr(
        "code_analysis.core.database.watch_dirs_partition.current_server_instance_id",
        _counting_sid,
    )

    discovered = [
        _make_project_root(tmp_path, "proj-a"),
        _make_project_root(tmp_path, "proj-b"),
        _make_project_root(tmp_path, "proj-c"),
    ]
    database = _FakeDatabase()

    active, excluded = mod.partition_discovered_projects_by_db_soft_delete(
        database, discovered
    )

    assert calls["n"] == 1
    assert len(active) == 3
    assert excluded == set()
    assert database.execute_calls == 3


def test_current_server_instance_id_called_once_even_with_zero_active_projects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    The hoist computes ``sid`` unconditionally once per call, even when every
    discovered project is excluded before reaching the DB row check (proves
    the call moved out of the loop body rather than merely being deduped).
    """

    class _DeletedProjectInfo:
        deleted = True
        processing_paused = False
        description = "deleted"

    monkeypatch.setattr(mod, "load_project_info", lambda root: _DeletedProjectInfo())

    calls: Dict[str, int] = {"n": 0}

    def _counting_sid(**kwargs: Any) -> str:
        calls["n"] += 1
        return "sid-fixed"

    monkeypatch.setattr(
        "code_analysis.core.database.watch_dirs_partition.current_server_instance_id",
        _counting_sid,
    )

    discovered = [
        _make_project_root(tmp_path, "proj-a"),
        _make_project_root(tmp_path, "proj-b"),
        _make_project_root(tmp_path, "proj-c"),
    ]
    database = _FakeDatabase()

    active, excluded = mod.partition_discovered_projects_by_db_soft_delete(
        database, discovered
    )

    assert calls["n"] == 1
    assert active == []
    assert len(excluded) == 3
    assert database.execute_calls == 0
