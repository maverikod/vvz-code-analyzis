"""
Unit tests for the pre-scan ignore-purge gate signature (bug 5b663fbb cost fix).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Optional, Tuple
from unittest.mock import patch

from code_analysis.core.file_watcher_pkg.multi_project_worker_scan import \
    _run_gated_ignore_purge_for_project
from code_analysis.core.file_watcher_pkg.purge_gate_signature import (
    compute_ignore_policy_stamp, compute_project_db_purge_signature,
    purge_gate_needed)


class _FakeDb:
    """Minimal fake DB: ``execute`` returns a canned ``{"data": [...]}`` row."""

    def __init__(self, count: int, max_updated: Optional[float]) -> None:
        self.count = count
        self.max_updated = max_updated
        self.calls: list[Tuple[str, Any]] = []

    def execute(self, sql: str, params: Any) -> dict:
        """Execute."""
        self.calls.append((sql, params))
        return {"data": [{"cnt": self.count, "max_updated": self.max_updated}]}


class _ErrorDb:
    """Fake DB whose ``execute`` always raises."""

    def execute(self, sql: str, params: Any) -> dict:
        """Execute."""
        raise RuntimeError("db unavailable")


def test_compute_project_db_purge_signature_reads_count_and_max_updated() -> None:
    """Signature is (count, max_updated) from the aggregate row."""
    db = _FakeDb(count=42, max_updated=2461234.5)
    sig = compute_project_db_purge_signature(db, "proj-1")
    assert sig == (42, 2461234.5)
    # Scoped to the project id, single aggregate query.
    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert "COUNT(*)" in sql
    assert "MAX(updated_at)" in sql
    assert params == ("proj-1",)


def test_compute_project_db_purge_signature_empty_project() -> None:
    """Zero active rows -> (0, None), not an error."""
    db = _FakeDb(count=0, max_updated=None)
    assert compute_project_db_purge_signature(db, "proj-empty") == (0, None)


def test_compute_project_db_purge_signature_query_failure_is_treated_as_changed() -> None:
    """A failing signature query must not silently disable the purge forever --
    it returns a sentinel signature that can never match a cached value, so
    the caller falls back to running the purge (fail open on cost, not on
    correctness)."""
    sig = compute_project_db_purge_signature(_ErrorDb(), "proj-1")
    assert sig == (-1, None)


def test_compute_ignore_policy_stamp_stable_for_same_patterns() -> None:
    """Same pattern tuple -> same stamp."""
    a = compute_ignore_policy_stamp(("**/test_data/**", "**/.venv/**"))
    b = compute_ignore_policy_stamp(("**/test_data/**", "**/.venv/**"))
    assert a == b


def test_compute_ignore_policy_stamp_changes_with_patterns() -> None:
    """Different pattern tuple -> different stamp."""
    a = compute_ignore_policy_stamp(("**/test_data/**",))
    b = compute_ignore_policy_stamp(("**/test_data/**", "**/extra/**"))
    assert a != b


def test_purge_gate_needed_no_cache_always_runs() -> None:
    """cache=None disables the gate entirely (always run) -- safe default."""
    assert purge_gate_needed("p1", (1, 1.0), "stamp", None) is True


def test_purge_gate_needed_first_sight_runs() -> None:
    """Project not yet in cache (first sight after worker start) -> run."""
    cache: dict = {}
    assert purge_gate_needed("p1", (1, 1.0), "stamp", cache) is True


def test_purge_gate_needed_unchanged_signature_skips() -> None:
    """Matching cached (db_signature, policy_stamp) -> gate says skip."""
    cache = {"p1": ((5, 100.0), "stampA")}
    assert purge_gate_needed("p1", (5, 100.0), "stampA", cache) is False


def test_purge_gate_needed_db_signature_change_runs() -> None:
    """A new row (different COUNT/MAX(updated_at)) -> run again."""
    cache = {"p1": ((5, 100.0), "stampA")}
    assert purge_gate_needed("p1", (6, 101.0), "stampA", cache) is True


def test_purge_gate_needed_policy_stamp_change_runs() -> None:
    """Same DB signature but the merged ignore policy changed -> run again."""
    cache = {"p1": ((5, 100.0), "stampA")}
    assert purge_gate_needed("p1", (5, 100.0), "stampB", cache) is True


def _gated_purge_kwargs(purge_signature_cache: Optional[dict]) -> dict:
    """Shared kwargs for :func:`_run_gated_ignore_purge_for_project` calls below."""
    return dict(
        allowed_venv_py=None,
        exc_files_filtered=None,
        exc_patterns=None,
        config_path=None,
        docs_indexing_snap=None,
        purge_signature_cache=purge_signature_cache,
    )


def test_gated_purge_runs_on_first_cycle_and_populates_cache() -> None:
    """First sight (empty cache): the purge runs, and the cache is populated
    with (db_signature, policy_stamp) afterward."""
    db = _FakeDb(count=3, max_updated=10.0)
    cache: dict = {}
    with patch(
        "code_analysis.core.file_watcher_pkg.ignore_pre_scan_purge."
        "run_pre_scan_ignore_purge_for_project"
    ) as mock_purge:
        _run_gated_ignore_purge_for_project(
            db, "proj-1", ("**/test_data/**",), **_gated_purge_kwargs(cache)
        )
    assert mock_purge.call_count == 1
    assert "proj-1" in cache
    assert cache["proj-1"][0] == (3, 10.0)


def test_gated_purge_does_not_run_on_unchanged_second_cycle() -> None:
    """Second cycle with an unchanged DB signature and policy: the purge is
    skipped (bug 5b663fbb cost fix)."""
    db = _FakeDb(count=3, max_updated=10.0)
    cache: dict = {}
    with patch(
        "code_analysis.core.file_watcher_pkg.ignore_pre_scan_purge."
        "run_pre_scan_ignore_purge_for_project"
    ) as mock_purge:
        _run_gated_ignore_purge_for_project(
            db, "proj-1", ("**/test_data/**",), **_gated_purge_kwargs(cache)
        )
        _run_gated_ignore_purge_for_project(
            db, "proj-1", ("**/test_data/**",), **_gated_purge_kwargs(cache)
        )
    assert mock_purge.call_count == 1


def test_gated_purge_runs_again_when_db_signature_changes() -> None:
    """A DB-side row change (e.g. bulk sync inserted a row) re-runs the purge."""
    db = _FakeDb(count=3, max_updated=10.0)
    cache: dict = {}
    with patch(
        "code_analysis.core.file_watcher_pkg.ignore_pre_scan_purge."
        "run_pre_scan_ignore_purge_for_project"
    ) as mock_purge:
        _run_gated_ignore_purge_for_project(
            db, "proj-1", ("**/test_data/**",), **_gated_purge_kwargs(cache)
        )
        db.count = 4
        db.max_updated = 11.0
        _run_gated_ignore_purge_for_project(
            db, "proj-1", ("**/test_data/**",), **_gated_purge_kwargs(cache)
        )
    assert mock_purge.call_count == 2


def test_gated_purge_runs_again_when_policy_changes() -> None:
    """The merged ignore pattern set changing re-runs the purge even though
    the DB-side signature is unchanged."""
    db = _FakeDb(count=3, max_updated=10.0)
    cache: dict = {}
    with patch(
        "code_analysis.core.file_watcher_pkg.ignore_pre_scan_purge."
        "run_pre_scan_ignore_purge_for_project"
    ) as mock_purge:
        _run_gated_ignore_purge_for_project(
            db, "proj-1", ("**/test_data/**",), **_gated_purge_kwargs(cache)
        )
        _run_gated_ignore_purge_for_project(
            db,
            "proj-1",
            ("**/test_data/**", "**/extra/**"),
            **_gated_purge_kwargs(cache),
        )
    assert mock_purge.call_count == 2


def test_gated_purge_always_runs_when_cache_is_none() -> None:
    """purge_signature_cache=None disables the gate entirely (prior behavior)."""
    db = _FakeDb(count=3, max_updated=10.0)
    with patch(
        "code_analysis.core.file_watcher_pkg.ignore_pre_scan_purge."
        "run_pre_scan_ignore_purge_for_project"
    ) as mock_purge:
        _run_gated_ignore_purge_for_project(
            db, "proj-1", ("**/test_data/**",), **_gated_purge_kwargs(None)
        )
        _run_gated_ignore_purge_for_project(
            db, "proj-1", ("**/test_data/**",), **_gated_purge_kwargs(None)
        )
    assert mock_purge.call_count == 2
