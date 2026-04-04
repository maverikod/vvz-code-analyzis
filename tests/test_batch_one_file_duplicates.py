"""
Tests for comprehensive_analysis batch per-file duplicate detection using in-memory source.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from code_analysis.commands.comprehensive_analysis_mcp.batch_one_file import (
    analyze_one_file_in_batch,
)
from code_analysis.core.duplicate_detector import DuplicateDetector


def test_analyze_one_file_in_batch_duplicates_calls_find_duplicates_in_code_with_source_and_path(
    tmp_path: Path,
) -> None:
    """find_duplicates_in_code receives source and path; result flows to file_results."""
    full_path = tmp_path / "sample.py"
    full_path.write_text("x = 1\n", encoding="utf-8")
    source_code = full_path.read_text(encoding="utf-8")
    timings_sec: Dict[str, float] = {"duplicates": 0.0}
    analyzer = MagicMock()
    file_record: Dict[str, Any] = {"project_id": "p_test"}
    with patch.object(
        DuplicateDetector, "find_duplicates_in_code", return_value=[]
    ) as mock_in_code:
        file_results, _summary, _pid = analyze_one_file_in_batch(
            full_path=full_path,
            file_path_str="sample.py",
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
            check_duplicates=True,
            check_flake8=False,
            check_mypy=False,
            check_docstrings=False,
            duplicate_min_lines=5,
            duplicate_min_similarity=0.8,
            set_step_desc=None,
        )
    assert mock_in_code.call_count == 1
    assert mock_in_code.call_args[0][0] == source_code
    assert mock_in_code.call_args[0][1] == str(full_path)
    assert file_results["duplicates"] == []


def test_analyze_one_file_in_batch_duplicates_does_not_call_find_duplicates_in_file(
    tmp_path: Path,
) -> None:
    """Batch duplicate path must not re-read the file via find_duplicates_in_file."""
    full_path = tmp_path / "sample.py"
    full_path.write_text("x = 1\n", encoding="utf-8")
    source_code = full_path.read_text(encoding="utf-8")
    timings_sec: Dict[str, float] = {"duplicates": 0.0}
    analyzer = MagicMock()
    file_record: Dict[str, Any] = {"project_id": "p_test"}
    with patch.object(DuplicateDetector, "find_duplicates_in_code", return_value=[]):
        with patch.object(DuplicateDetector, "find_duplicates_in_file") as mock_in_file:
            analyze_one_file_in_batch(
                full_path=full_path,
                file_path_str="sample.py",
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
                check_duplicates=True,
                check_flake8=False,
                check_mypy=False,
                check_docstrings=False,
                duplicate_min_lines=5,
                duplicate_min_similarity=0.8,
                set_step_desc=None,
            )
    assert mock_in_file.call_count == 0
