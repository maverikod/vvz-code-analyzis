"""
Tests for the enumeration cache introduced to fix bug 8e6acb34 (concurrency
speedup regression in ``list_project_files``/``fs_grep``): repeat calls with
identical parameters must not re-walk the project tree, the cache must be
single-flight under concurrency, must expire and reflect disk changes after
its TTL, must not cross-contaminate between distinct parameter tuples, and
pagination across cached calls must stay stable.

Also pins the DESIGN DECISION recorded in
``code_analysis/commands/project_fs_enumerate.py`` (module-level comment
above ``enumerate_project_paths``): disk stays the sole source of truth for
listing -- the DB ``files`` index is never consulted to hide or ghost-add a
path -- because the watcher only indexes ``CODE_FILE_EXTENSIONS`` (``.py``)
plus opt-in docs suffixes, which is not a superset of what a default
(``python_only=False``) listing must return.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands import project_fs_enumerate as pfe
from code_analysis.commands.ast.list_files import ListProjectFilesMCPCommand

_PROJECT_ID = "00000000-0000-0000-0000-0000000000f1"


@pytest.fixture(autouse=True)
def _mock_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real DB in unit tests; default index has no file rows."""
    mock_db = MagicMock()
    mock_db.get_project_file_rows.return_value = []

    def _open(_self: object, auto_analyze: bool = False) -> MagicMock:
        return mock_db

    monkeypatch.setattr(
        ListProjectFilesMCPCommand, "_open_database_from_config", _open
    )
    monkeypatch.setattr(
        "code_analysis.commands.ast.list_files.get_file_rows_by_paths",
        lambda driver, project_id, relative_paths, include_deleted=False: [],
    )


@pytest.fixture(autouse=True)
def _clear_cache_around_test() -> None:
    """Isolate every test from cache state left by another test/process."""
    pfe.clear_enumeration_cache()
    yield
    pfe.clear_enumeration_cache()


def _make_project(root: Path, n: int = 10) -> None:
    root.mkdir()
    for i in range(n):
        (root / f"f{i:03d}.py").write_text("#\n")


def _count_uncached_calls(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Wrap ``_enumerate_project_paths_uncached`` with a call counter."""
    counters = {"n": 0}
    real = pfe._enumerate_project_paths_uncached

    def _counting(*args: object, **kwargs: object) -> list:
        counters["n"] += 1
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pfe, "_enumerate_project_paths_uncached", _counting)
    return counters


def test_repeat_identical_call_within_ttl_hits_cache_not_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard for bug 8e6acb34: identical repeat calls walk once."""
    root = tmp_path / "proj"
    _make_project(root, n=25)
    counters = _count_uncached_calls(monkeypatch)

    first = pfe.enumerate_project_paths(root, show_venv=False, python_only=False)
    second = pfe.enumerate_project_paths(root, show_venv=False, python_only=False)

    assert counters["n"] == 1
    assert [p.name for p in first] == [p.name for p in second]
    assert len(first) == 25


@pytest.mark.asyncio
async def test_page_size_1_command_does_not_rewalk_on_repeat_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: ``list_project_files(page_size=1)`` twice in a row walks once.

    This is the exact param shape bug 8e6acb34's own pipeline check
    (``lifecycle_read_throughput.py``) exercises N=16 times back to back.
    """
    root = tmp_path / "proj"
    _make_project(root, n=50)
    counters = _count_uncached_calls(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        r1 = await cmd.execute(project_id=_PROJECT_ID, page_size=1)
        r2 = await cmd.execute(project_id=_PROJECT_ID, page_size=1)

    assert counters["n"] == 1
    assert r1.data is not None and r2.data is not None
    assert r1.data["total"] == 50
    assert r2.data["total"] == 50
    assert r1.data["count"] == 1


def test_different_params_do_not_share_a_cache_entry(tmp_path: Path) -> None:
    """Distinct (filters, pattern) tuples must never collide on one cache slot."""
    root = tmp_path / "proj"
    _make_project(root, n=2)
    (root / "README.md").write_text("# x\n")

    py_only = pfe.enumerate_project_paths(root, show_venv=False, python_only=True)
    all_files = pfe.enumerate_project_paths(root, show_venv=False, python_only=False)

    assert len(py_only) == 2
    assert len(all_files) == 3


def test_cache_expires_after_ttl_and_reflects_new_disk_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cache HIT is bounded by the TTL; after it elapses the walk re-runs
    and a file created in between becomes visible (staleness is bounded, not
    permanent -- unlike switching to the DB index, which was rejected)."""
    root = tmp_path / "proj"
    _make_project(root, n=3)
    monkeypatch.setattr(pfe, "_ENUMERATION_CACHE_TTL_SECONDS", 0.05)

    first = pfe.enumerate_project_paths(root, show_venv=False, python_only=False)
    assert len(first) == 3

    (root / "new_file.py").write_text("#\n")
    time.sleep(0.15)

    second = pfe.enumerate_project_paths(root, show_venv=False, python_only=False)
    assert len(second) == 4


def test_clear_enumeration_cache_forces_fresh_walk(tmp_path: Path) -> None:
    """Explicit invalidation must not wait out the TTL."""
    root = tmp_path / "proj"
    _make_project(root, n=1)

    first = pfe.enumerate_project_paths(root, show_venv=False, python_only=False)
    assert len(first) == 1

    (root / "added.py").write_text("#\n")
    pfe.clear_enumeration_cache()

    second = pfe.enumerate_project_paths(root, show_venv=False, python_only=False)
    assert len(second) == 2


def test_concurrent_identical_calls_are_single_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent callers with the same key must collapse to one real walk,
    not N (this is what turns the 8e6acb34 GIL-contention story around for
    the repeated-identical-call access pattern)."""
    root = tmp_path / "proj"
    _make_project(root, n=5)
    real = pfe._enumerate_project_paths_uncached
    counters = {"n": 0}

    def _slow_uncached(*args: object, **kwargs: object) -> list:
        counters["n"] += 1
        time.sleep(0.1)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pfe, "_enumerate_project_paths_uncached", _slow_uncached)

    results: list = []
    results_lock = threading.Lock()

    def _worker() -> None:
        r = pfe.enumerate_project_paths(root, show_venv=False, python_only=False)
        with results_lock:
            results.append(r)

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert counters["n"] == 1
    assert len(results) == 8
    assert all(len(r) == 5 for r in results)


@pytest.mark.asyncio
async def test_pagination_stable_across_cached_pages(tmp_path: Path) -> None:
    """Multiple ``block_position`` calls against the same listing must together
    cover every file exactly once, sorted, whether served from cache or not."""
    root = tmp_path / "proj"
    _make_project(root, n=10)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        pages = [
            await cmd.execute(
                project_id=_PROJECT_ID, page_size=4, block_position=bp
            )
            for bp in (1, 2, 3)
        ]

    all_rel = [
        f["relative_path"]
        for page in pages
        for f in (page.data["files"] if page.data else [])
    ]
    assert len(all_rel) == 10
    assert all_rel == sorted(all_rel)
    assert len(set(all_rel)) == 10


@pytest.mark.asyncio
async def test_disk_present_file_listed_regardless_of_index_state(
    tmp_path: Path,
) -> None:
    """Design decision (bug 8e6acb34): disk stays the listing source of truth.

    A file present on disk but never indexed by the watcher (e.g. a non-.py,
    non-docs-eligible suffix -- the watcher's ``CODE_FILE_EXTENSIONS`` is
    exactly ``{".py"}``, see ``core/constants.py``) is still listed, with
    ``file_id=None`` and ``deleted=False``: the listing path never asks the
    DB whether to hide or ghost-add a path, only to enrich it.
    """
    root = tmp_path / "proj"
    root.mkdir()
    (root / "notes.txt").write_text("hello\n")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=_PROJECT_ID, page_size=10)

    assert result.data is not None
    assert result.data["total"] == 1
    row = result.data["files"][0]
    assert row["relative_path"] == "notes.txt"
    assert row["file_id"] is None
    assert row["deleted"] is False
