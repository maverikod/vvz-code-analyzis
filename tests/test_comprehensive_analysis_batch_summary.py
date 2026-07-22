"""
Tests for comprehensive_analysis batch summary trust counters.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.comprehensive_analysis_mcp.batch_summary import (
    build_batch_summary,
)
from code_analysis.commands.comprehensive_analysis_mcp.execute_batch import run_batch
from code_analysis.core.comprehensive_analyzer import ComprehensiveAnalyzer


def _minimal_results() -> dict:
    """Return minimal results."""
    return {
        "placeholders": [],
        "stubs": [],
        "empty_methods": [],
        "imports_not_at_top": [],
        "long_files": [],
        "duplicates": [],
        "flake8_errors": [],
        "mypy_errors": [],
        "missing_docstrings": [],
    }


def _empty_file_results() -> dict:
    """Return empty file results."""
    return {
        "placeholders": [],
        "stubs": [],
        "empty_methods": [],
        "imports_not_at_top": [],
        "duplicates": [],
        "flake8_errors": [],
        "mypy_errors": [],
        "missing_docstrings": [],
    }


@pytest.fixture(autouse=True)
def _patch_get_project_files_to_db_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route the domain ``get_project_files`` call site back to ``db.get_project_files``.

    ``run_batch`` calls the driver-direct free function (stage-2 layer
    collapse), which reads through ``driver.select`` - a primitive the bare
    ``MagicMock()`` db in this module does not model.
    """
    monkeypatch.setattr(
        "code_analysis.commands.comprehensive_analysis_mcp.execute_batch.get_project_files",
        lambda driver, project_id, include_deleted=False, limit=None, offset=None: (
            driver.get_project_files(
                project_id,
                include_deleted=include_deleted,
                limit=limit,
                offset=offset,
            )
        ),
    )


def test_build_batch_summary_includes_trust_counters_and_sum() -> None:
    """Summary exposes new keys; analyzed + skipped + unreadable/missing equals total."""
    results = _minimal_results()
    summary = build_batch_summary(
        results,
        2,
        1,
        4,
        files_skipped_up_to_date=1,
        files_skipped_unreadable_or_missing=1,
    )
    assert summary["files_analyzed"] == 2
    assert summary["files_skipped"] == 1
    assert summary["files_total"] == 4
    assert summary["files_skipped_up_to_date"] == 1
    assert summary["files_skipped_unreadable_or_missing"] == 1
    assert (
        summary["files_analyzed"]
        + summary["files_skipped"]
        + summary["files_skipped_unreadable_or_missing"]
        == summary["files_total"]
    )


def test_build_batch_summary_default_trust_counters_zero() -> None:
    """Callers passing only legacy positional args get new keys as zero."""
    summary = build_batch_summary(_minimal_results(), 0, 0, 0)
    assert summary["files_skipped_up_to_date"] == 0
    assert summary["files_skipped_unreadable_or_missing"] == 0


def test_build_batch_summary_save_error_counters_default_zero() -> None:
    """Callers passing only legacy positional args get save counters as zero."""
    summary = build_batch_summary(_minimal_results(), 0, 0, 0)
    assert summary["save_errors"] == 0
    assert summary["results_persisted"] == 0


def test_build_batch_summary_save_error_counters_passthrough() -> None:
    """save_errors/results_persisted surface explicitly-passed batch-save outcomes."""
    summary = build_batch_summary(
        _minimal_results(),
        2,
        1,
        4,
        save_errors=1,
        results_persisted=3,
    )
    assert summary["save_errors"] == 1
    assert summary["results_persisted"] == 3


@pytest.mark.asyncio
async def test_run_batch_summary_counter_invariants(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One missing file, one up-to-date skip, one analyzed row: buckets sum to files_total."""
    # execute_batch calls the driver-direct should_analyze_file free function (stage-2
    # layer collapse) unconditionally now, instead of hasattr(db, "should_analyze_file")
    # dispatch - route it back to db.should_analyze_file(fid, mtime) below.
    monkeypatch.setattr(
        "code_analysis.commands.comprehensive_analysis_mcp.execute_batch."
        "should_analyze_file",
        lambda driver, file_id, file_mtime: driver.should_analyze_file(
            file_id, file_mtime
        ),
    )
    (tmp_path / "stale.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "live.py").write_text("y = 2\n", encoding="utf-8")

    file_rows = [
        {"id": 1, "path": "gone.py", "lines": 1, "project_id": "p1"},
        {"id": 2, "path": "stale.py", "lines": 1, "project_id": "p1"},
        {"id": 3, "path": "live.py", "lines": 1, "project_id": "p1"},
    ]

    db = MagicMock()
    db.get_project_files = MagicMock(return_value=file_rows)
    db.disconnect = MagicMock()
    db.save_comprehensive_analysis_results_batch = MagicMock()

    def should_analyze_file(fid, _mtime):
        """Return should analyze file."""
        if fid == 2:
            return {"should_analyze": False, "reason": "up_to_date"}
        return {"should_analyze": True}

    db.should_analyze_file = should_analyze_file

    results = {
        **_minimal_results(),
        "summary": {},
    }
    ctx = {
        "db": db,
        "root_path": tmp_path,
        "proj_id": "p1",
        "analysis_logger": logging.getLogger("test_ca_batch_summary"),
        "log_timing": lambda _phase, t0: time.perf_counter(),
        "progress_tracker": None,
        "analyzer": ComprehensiveAnalyzer(max_lines=10_000),
        "results": results,
        "mypy_config": None,
        "limit": 3,
        "offset": 0,
        "t_start": time.perf_counter(),
        "check_placeholders": False,
        "check_stubs": False,
        "check_empty_methods": False,
        "check_imports": False,
        "check_long_files": False,
        "check_duplicates": False,
        "check_flake8": False,
        "check_mypy": False,
        "check_docstrings": False,
        "duplicate_min_lines": 5,
        "duplicate_min_similarity": 0.8,
    }

    empty_fr = _empty_file_results()
    with patch(
        "code_analysis.commands.comprehensive_analysis_mcp.execute_batch.analyze_one_file_in_batch",
        return_value=(empty_fr, {}, "p1"),
    ):
        await run_batch(MagicMock(), ctx)

    s = results["summary"]
    assert s["files_total"] == 3
    assert s["files_analyzed"] == 1
    assert s["files_skipped"] == 1
    assert s["files_skipped_up_to_date"] == 1
    assert s["files_skipped_unreadable_or_missing"] == 1
    assert s["files_skipped"] == s["files_skipped_up_to_date"]
    assert (
        s["files_analyzed"]
        + s["files_skipped"]
        + s["files_skipped_unreadable_or_missing"]
        == s["files_total"]
    )
