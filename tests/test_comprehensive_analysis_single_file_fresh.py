"""
Single-file comprehensive_analysis always runs checks; does not use mtime DB cache.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from unittest.mock import MagicMock

import pytest

from code_analysis.commands.comprehensive_analysis_mcp.execute_single import (
    run_single_file,
)


def _empty_results() -> dict:
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
        "summary": {},
    }


@pytest.mark.asyncio
async def test_single_file_runs_mypy_when_mtime_gate_would_skip_cached_row(
    tmp_path,
) -> None:
    """If DB says up-to-date, we still run analyzers; do not return stale get_comprehensive_analysis_results."""
    (tmp_path / "x.py").write_text("a = 1\n", encoding="utf-8")

    db = MagicMock()
    db.get_file_by_path = MagicMock(return_value={"id": 99, "project_id": "p1"})
    db.should_analyze_file = MagicMock(
        return_value={
            "should_analyze": False,
            "reason": "equal_within_tolerance",
            "db_mtime": 1.0,
            "disk_mtime": 1.0,
        }
    )
    db.get_comprehensive_analysis_results = MagicMock(
        return_value={
            "results": {
                **_empty_results(),
                "mypy_errors": [],
            }
        }
    )
    db.disconnect = MagicMock()
    db.save_comprehensive_analysis_results = MagicMock()

    fresh_mypy = {
        "success": False,
        "error_message": "Found 1 mypy errors",
        "errors": ["x.py:1: error: [test] intentional"],
        "error_count": 1,
    }
    analyzer = MagicMock()
    analyzer.check_mypy = MagicMock(return_value=fresh_mypy)

    ctx = {
        "db": db,
        "root_path": tmp_path,
        "proj_id": "p1",
        "analysis_logger": logging.getLogger("test_ca_single_fresh"),
        "log_timing": lambda _phase, t0: time.perf_counter(),
        "progress_tracker": None,
        "analyzer": analyzer,
        "results": _empty_results(),
        "mypy_config": None,
        "file_path": "x.py",
        "check_placeholders": False,
        "check_stubs": False,
        "check_empty_methods": False,
        "check_imports": False,
        "check_duplicates": False,
        "check_flake8": False,
        "check_mypy": True,
        "check_docstrings": False,
        "duplicate_min_lines": 5,
        "duplicate_min_similarity": 0.8,
    }

    cmd = MagicMock()

    def _validate(fp: str, root):
        return (root / fp).resolve()

    cmd._validate_file_path = _validate

    result = await run_single_file(cmd, ctx)

    db.get_comprehensive_analysis_results.assert_not_called()
    analyzer.check_mypy.assert_called_once()
    assert result.data is ctx["results"]
    assert len(ctx["results"]["mypy_errors"]) == 1
    assert ctx["results"]["mypy_errors"][0]["errors"] == fresh_mypy["errors"]
    s = ctx["results"]["summary"]
    assert s["files_analyzed"] == 1
    assert s["files_skipped"] == 0
    assert s["files_total"] == 1
