"""
Tests that comprehensive_analysis's flake8 pass is restricted to Python files.

Covers bug a012547c: flake8 (a Python-only linter) was invoked against
non-Python files (e.g. markdown) picked up by the comprehensive analysis
index, producing spurious E999 SyntaxError findings.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

from code_analysis.commands.comprehensive_analysis_mcp.batch_one_file import (
    analyze_one_file_in_batch,
)


def test_analyze_one_file_in_batch_skips_flake8_for_markdown_file(
    tmp_path: Path,
) -> None:
    """A .md fixture file must produce zero flake8 findings and no flake8 call."""
    full_path = tmp_path / "notes.md"
    full_path.write_text("# Not Python\n\nSome *markdown* text.\n", encoding="utf-8")
    source_code = full_path.read_text(encoding="utf-8")
    timings_sec: Dict[str, float] = {"flake8": 0.0}
    analyzer = MagicMock()
    file_record: Dict[str, Any] = {"project_id": "p_test"}

    file_results, file_summary, _pid = analyze_one_file_in_batch(
        full_path=full_path,
        file_path_str="notes.md",
        source_code=source_code,
        file_id=1,
        file_record=file_record,
        proj_id="p_test",
        analyzer=analyzer,
        project_mypy_errors={},
        timings_sec=timings_sec,
        check_placeholders=False,
        check_stubs=False,
        check_empty_methods=False,
        check_imports=False,
        check_duplicates=False,
        check_flake8=True,
        check_mypy=False,
        check_docstrings=False,
        duplicate_min_lines=5,
        duplicate_min_similarity=0.8,
        set_step_desc=None,
    )

    assert analyzer.check_flake8.call_count == 0
    assert file_results["flake8_errors"] == []
    assert file_summary["total_flake8_errors"] == 0
    assert file_summary["files_with_flake8_errors"] == 0


def test_analyze_one_file_in_batch_still_runs_flake8_for_python_file(
    tmp_path: Path,
) -> None:
    """A .py fixture file still goes through flake8 when check_flake8 is requested."""
    full_path = tmp_path / "module.py"
    full_path.write_text("x = 1\n", encoding="utf-8")
    source_code = full_path.read_text(encoding="utf-8")
    timings_sec: Dict[str, float] = {"flake8": 0.0}
    analyzer = MagicMock()
    analyzer.check_flake8.return_value = {
        "success": True,
        "error_message": None,
        "errors": [],
        "error_count": 0,
        "tool_available": True,
    }
    file_record: Dict[str, Any] = {"project_id": "p_test"}

    analyze_one_file_in_batch(
        full_path=full_path,
        file_path_str="module.py",
        source_code=source_code,
        file_id=1,
        file_record=file_record,
        proj_id="p_test",
        analyzer=analyzer,
        project_mypy_errors={},
        timings_sec=timings_sec,
        check_placeholders=False,
        check_stubs=False,
        check_empty_methods=False,
        check_imports=False,
        check_duplicates=False,
        check_flake8=True,
        check_mypy=False,
        check_docstrings=False,
        duplicate_min_lines=5,
        duplicate_min_similarity=0.8,
        set_step_desc=None,
    )

    assert analyzer.check_flake8.call_count == 1
    analyzer.check_flake8.assert_called_once_with(full_path)
