"""
Tests for mypy summary coherence in comprehensive_analysis (single-file and batch summaries).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.commands.comprehensive_analysis_mcp.batch_summary import (
    build_batch_summary,
    build_single_file_summary,
    mypy_diagnostic_counts,
)


def test_mypy_diagnostic_counts_only_files_with_positive_error_count() -> None:
    """Stale row: success false, error_count 0 — does not count as a file with errors."""
    rows = [
        {
            "success": False,
            "error_message": "Found 0 mypy errors",
            "errors": [],
            "error_count": 0,
            "file_path": "pkg/mod.py",
        }
    ]
    total, files_with = mypy_diagnostic_counts(rows)
    assert total == 0
    assert files_with == 0


def test_mypy_diagnostic_counts_real_errors() -> None:
    rows = [
        {
            "success": False,
            "error_message": "Found 2 mypy errors",
            "errors": ["a.py:1: error: x", "a.py:2: error: y"],
            "error_count": 2,
            "file_path": "a.py",
        }
    ]
    total, files_with = mypy_diagnostic_counts(rows)
    assert total == 2
    assert files_with == 1


def test_build_single_file_summary_matches_totals_for_stale_mypy_row() -> None:
    results = {
        "placeholders": [],
        "stubs": [],
        "empty_methods": [],
        "imports_not_at_top": [],
        "duplicates": [],
        "flake8_errors": [],
        "mypy_errors": [
            {
                "success": False,
                "error_count": 0,
                "errors": [],
                "file_path": "x.py",
            }
        ],
        "missing_docstrings": [],
    }
    s = build_single_file_summary(results, 0, 1, 1)
    assert s["total_mypy_errors"] == 0
    assert s["files_with_mypy_errors"] == 0
    assert s["files_analyzed"] == 0
    assert s["files_skipped"] == 1
    assert s["files_total"] == 1


def test_build_batch_summary_mypy_coherence() -> None:
    results = {
        "placeholders": [],
        "stubs": [],
        "empty_methods": [],
        "imports_not_at_top": [],
        "long_files": [],
        "duplicates": [],
        "flake8_errors": [],
        "mypy_errors": [
            {
                "success": False,
                "error_count": 0,
                "errors": [],
                "file_path": "m.py",
            }
        ],
        "missing_docstrings": [],
    }
    summary = build_batch_summary(results, 1, 0, 1)
    assert summary["total_mypy_errors"] == 0
    assert summary["files_with_mypy_errors"] == 0
