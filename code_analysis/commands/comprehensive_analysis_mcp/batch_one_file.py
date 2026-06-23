"""
Analyze one file inside comprehensive_analysis batch.

Returns file_results and file_summary for a single file; caller aggregates
and handles save_batch / progress.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...core.duplicate_detector import DuplicateDetector
from .batch_summary import quality_findings_counts

logger = logging.getLogger(__name__)


def analyze_one_file_in_batch(
    full_path: Path,
    file_path_str: str,
    source_code: str,
    file_id: Any,
    file_record: Dict[str, Any],
    proj_id: Optional[str],
    analyzer: Any,
    project_mypy_errors: Dict[str, List[str]],
    timings_sec: Dict[str, float],
    check_placeholders: bool,
    check_stubs: bool,
    check_empty_methods: bool,
    check_imports: bool,
    check_duplicates: bool,
    check_flake8: bool,
    check_mypy: bool,
    check_docstrings: bool,
    duplicate_min_lines: int,
    duplicate_min_similarity: float,
    set_step_desc: Optional[Callable[[str], None]] = None,
    check_black: bool = False,
    check_isort: bool = False,
    check_bandit: bool = False,
    bandit_config: Optional[Path] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Any]:
    """
    Run all analysis checks for one file in batch mode.

    If set_step_desc is provided, it is called with the current check name
    (e.g. "placeholders", "flake8", "mypy") before each check for status display.

    Mutates timings_sec. Returns (file_results, file_summary, file_project_id).
    """
    file_results: Dict[str, Any] = {
        "placeholders": [],
        "stubs": [],
        "empty_methods": [],
        "imports_not_at_top": [],
        "duplicates": [],
        "flake8_errors": [],
        "mypy_errors": [],
        "black_findings": [],
        "isort_findings": [],
        "bandit_findings": [],
        "missing_docstrings": [],
    }

    if check_placeholders:
        if set_step_desc:
            set_step_desc("placeholders")
        t0 = time.perf_counter()
        placeholders = analyzer.find_placeholders(full_path, source_code)
        timings_sec["placeholders"] += time.perf_counter() - t0
        for p in placeholders:
            p["file_path"] = file_path_str
        file_results["placeholders"] = placeholders

    if check_stubs:
        if set_step_desc:
            set_step_desc("stubs")
        t0 = time.perf_counter()
        stubs = analyzer.find_stubs(full_path, source_code)
        timings_sec["stubs"] += time.perf_counter() - t0
        for s in stubs:
            s["file_path"] = file_path_str
        file_results["stubs"] = stubs

    if check_empty_methods:
        if set_step_desc:
            set_step_desc("empty_methods")
        t0 = time.perf_counter()
        empty_methods = analyzer.find_empty_methods(full_path, source_code)
        timings_sec["empty_methods"] += time.perf_counter() - t0
        for m in empty_methods:
            m["file_path"] = file_path_str
        file_results["empty_methods"] = empty_methods

    if check_imports:
        if set_step_desc:
            set_step_desc("imports")
        t0 = time.perf_counter()
        imports_not_at_top = analyzer.find_imports_not_at_top(full_path, source_code)
        timings_sec["imports"] += time.perf_counter() - t0
        for imp in imports_not_at_top:
            imp["file_path"] = file_path_str
        file_results["imports_not_at_top"] = imports_not_at_top

    if check_duplicates:
        if set_step_desc:
            set_step_desc("duplicates")
        t0 = time.perf_counter()
        detector = DuplicateDetector(
            min_lines=duplicate_min_lines,
            min_similarity=duplicate_min_similarity,
            use_semantic=False,
        )
        duplicates = detector.find_duplicates_in_code(source_code, str(full_path))
        timings_sec["duplicates"] += time.perf_counter() - t0
        for group in duplicates:
            for occ in group["occurrences"]:
                occ["file_path"] = file_path_str
        file_results["duplicates"] = duplicates

    if check_flake8:
        if set_step_desc:
            set_step_desc("flake8")
        t0 = time.perf_counter()
        flake8_result = analyzer.check_flake8(full_path)
        timings_sec["flake8"] += time.perf_counter() - t0
        if not flake8_result["success"]:
            flake8_result["file_path"] = file_path_str
            file_results["flake8_errors"] = [flake8_result]

    if check_mypy:
        if set_step_desc:
            set_step_desc("mypy")
        key = str(full_path.resolve())
        mypy_errors_list = project_mypy_errors.get(key, [])
        if mypy_errors_list:
            mypy_result = {
                "success": False,
                "error_message": (f"Found {len(mypy_errors_list)} mypy errors"),
                "errors": mypy_errors_list,
                "error_count": len(mypy_errors_list),
                "file_path": file_path_str,
            }
            file_results["mypy_errors"] = [mypy_result]
        else:
            file_results["mypy_errors"] = []

    if check_black:
        if set_step_desc:
            set_step_desc("black")
        t0 = time.perf_counter()
        black_result = analyzer.check_black(full_path)
        timings_sec["black"] = timings_sec.get("black", 0.0) + (time.perf_counter() - t0)
        if not black_result["success"]:
            black_result["file_path"] = file_path_str
            file_results["black_findings"] = [black_result]

    if check_isort:
        if set_step_desc:
            set_step_desc("isort")
        t0 = time.perf_counter()
        isort_result = analyzer.check_isort(full_path)
        timings_sec["isort"] = timings_sec.get("isort", 0.0) + (time.perf_counter() - t0)
        if not isort_result["success"]:
            isort_result["file_path"] = file_path_str
            file_results["isort_findings"] = [isort_result]

    if check_bandit:
        if set_step_desc:
            set_step_desc("bandit")
        t0 = time.perf_counter()
        bandit_result = analyzer.check_bandit(full_path, bandit_config)
        timings_sec["bandit"] = timings_sec.get("bandit", 0.0) + (time.perf_counter() - t0)
        if not bandit_result["success"]:
            bandit_result["file_path"] = file_path_str
            file_results["bandit_findings"] = [bandit_result]

    if check_docstrings:
        if set_step_desc:
            set_step_desc("docstrings")
        t0 = time.perf_counter()
        missing_docstrings = analyzer.find_missing_docstrings(full_path, source_code)
        timings_sec["docstrings"] += time.perf_counter() - t0
        for d in missing_docstrings:
            d["file_path"] = file_path_str
        file_results["missing_docstrings"] = missing_docstrings

    file_summary = {
        "total_placeholders": len(file_results["placeholders"]),
        "total_stubs": len(file_results["stubs"]),
        "total_empty_methods": len(file_results["empty_methods"]),
        "total_imports_not_at_top": len(file_results["imports_not_at_top"]),
        "total_duplicate_groups": len(file_results["duplicates"]),
        "total_duplicate_occurrences": sum(
            len(g["occurrences"]) for g in file_results["duplicates"]
        ),
        "total_flake8_errors": sum(
            e.get("error_count", 0) for e in file_results.get("flake8_errors", [])
        ),
        "files_with_flake8_errors": len(file_results.get("flake8_errors", [])),
        "total_mypy_errors": sum(
            e.get("error_count", 0) for e in file_results.get("mypy_errors", [])
        ),
        "files_with_mypy_errors": len(file_results.get("mypy_errors", [])),
        "total_missing_docstrings": len(file_results["missing_docstrings"]),
        **quality_findings_counts(file_results),
    }

    file_project_id = proj_id or file_record.get("project_id")
    return (file_results, file_summary, file_project_id)
