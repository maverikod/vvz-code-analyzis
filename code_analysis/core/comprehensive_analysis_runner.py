"""
Comprehensive analysis runner used by MCP command implementation.

This module contains the heavy logic for iterating project files, applying the
ComprehensiveAnalyzer checks, and producing a unified result structure.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .comprehensive_analyzer import ComprehensiveAnalyzer
from .duplicate_detector import DuplicateDetector

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ComprehensiveAnalysisConfig:
    """
    Configuration for comprehensive analysis.

    Attributes:
        max_lines: Maximum lines threshold for long files.
        check_placeholders: Whether to check for placeholders (TODO, FIXME, etc.).
        check_stubs: Whether to check for stubs (pass, ellipsis, NotImplementedError).
        check_empty_methods: Whether to check for empty methods.
        check_imports: Whether to check for imports not at top of file.
        check_long_files: Whether to check for long files.
        check_duplicates: Whether to check for code duplicates.
        check_flake8: Whether to run flake8 linting.
        check_mypy: Whether to run mypy type checking.
        duplicate_min_lines: Minimum lines for duplicate detection.
        duplicate_min_similarity: Minimum similarity for duplicate detection.
        mypy_config: Optional resolved path to mypy config.
        exclude_dir_names: Directory names to exclude from analysis by default.
    """

    max_lines: int = 400
    check_placeholders: bool = True
    check_stubs: bool = True
    check_empty_methods: bool = True
    check_imports: bool = True
    check_long_files: bool = True
    check_duplicates: bool = True
    check_flake8: bool = True
    check_mypy: bool = True
    duplicate_min_lines: int = 5
    duplicate_min_similarity: float = 0.8
    mypy_config: Optional[Path] = None
    exclude_dir_names: Sequence[str] = ("test_data",)


def is_python_file(path: Path) -> bool:
    """
    Check if a given path is a Python source file.

    Args:
        path: Path to check.

    Returns:
        True if the file has `.py` suffix, False otherwise.
    """

    return path.suffix == ".py"


def should_exclude_path(path: Path, exclude_dir_names: Sequence[str]) -> bool:
    """
    Decide whether a path should be excluded based on directory names.

    Args:
        path: File path.
        exclude_dir_names: Directory names to exclude if present in the path parts.

    Returns:
        True if excluded, False otherwise.
    """

    parts = set(path.parts)
    return any(name in parts for name in exclude_dir_names)


def iter_project_python_files_from_db(
    *,
    db: Any,
    project_id: str,
    root_path: Path,
    exclude_dir_names: Sequence[str],
) -> Iterable[Dict[str, Any]]:
    """
    Iterate over Python files for a project based on DB file records.

    This uses the `files` table but filters it aggressively to avoid running
    Python-only checks on non-Python files and to exclude noisy directories.

    Args:
        db: Database-like object with `_fetchall`.
        project_id: Project UUID.
        root_path: Project root path.
        exclude_dir_names: Directory names to exclude.

    Yields:
        File record dicts with at least: path, lines, full_path.
    """

    files = db._fetchall(
        "SELECT id, path, lines FROM files WHERE project_id = ? AND deleted = 0",
        (project_id,),
    )

    for rec in files:
        file_path_str = rec["path"]

        full_path = (
            Path(file_path_str)
            if Path(file_path_str).is_absolute()
            else root_path / file_path_str
        )
        if not full_path.exists() or not full_path.is_file():
            continue

        if should_exclude_path(full_path, exclude_dir_names):
            continue

        if not is_python_file(full_path):
            continue

        yield {
            "path": file_path_str,
            "lines": rec.get("lines", 0),
            "full_path": full_path,
        }


def analyze_single_python_file(
    *,
    analyzer: ComprehensiveAnalyzer,
    detector: Optional[DuplicateDetector],
    file_path_obj: Path,
    rel_path: str,
    config: ComprehensiveAnalysisConfig,
) -> Dict[str, Any]:
    """
    Run configured checks on a single Python file.

    Args:
        analyzer: Analyzer instance.
        detector: Optional duplicate detector (constructed only when enabled).
        file_path_obj: Absolute path to file.
        rel_path: Path relative to root_dir (for reporting).
        config: Analysis configuration.

    Returns:
        Partial results dict for that file.
    """

    source_code = file_path_obj.read_text(encoding="utf-8")

    out: Dict[str, Any] = {
        "placeholders": [],
        "stubs": [],
        "empty_methods": [],
        "imports_not_at_top": [],
        "duplicates": [],
        "flake8_errors": [],
        "mypy_errors": [],
    }

    if config.check_placeholders:
        placeholders = analyzer.find_placeholders(file_path_obj, source_code)
        for p in placeholders:
            p["file_path"] = rel_path
        out["placeholders"] = placeholders

    if config.check_stubs:
        stubs = analyzer.find_stubs(file_path_obj, source_code)
        for s in stubs:
            s["file_path"] = rel_path
        out["stubs"] = stubs

    if config.check_empty_methods:
        empty_methods = analyzer.find_empty_methods(file_path_obj, source_code)
        for m in empty_methods:
            m["file_path"] = rel_path
        out["empty_methods"] = empty_methods

    if config.check_imports:
        imports_not_at_top = analyzer.find_imports_not_at_top(
            file_path_obj, source_code
        )
        for imp in imports_not_at_top:
            imp["file_path"] = rel_path
        out["imports_not_at_top"] = imports_not_at_top

    if config.check_duplicates and detector is not None:
        duplicates = detector.find_duplicates_in_file(str(file_path_obj))
        for group in duplicates:
            for occ in group["occurrences"]:
                occ["file_path"] = rel_path
        out["duplicates"] = duplicates

    if config.check_flake8:
        flake8_result = analyzer.check_flake8(file_path_obj)
        if not flake8_result["success"]:
            flake8_result["file_path"] = rel_path
            out["flake8_errors"].append(flake8_result)

    if config.check_mypy:
        mypy_result = analyzer.check_mypy(file_path_obj, config.mypy_config)
        if not mypy_result["success"]:
            mypy_result["file_path"] = rel_path
            out["mypy_errors"].append(mypy_result)

    return out


def run_comprehensive_analysis(
    *,
    root_path: Path,
    db: Any,
    project_id: str,
    file_path: Optional[Path],
    config: ComprehensiveAnalysisConfig,
    progress_tracker: Optional[Any],
    analysis_logger: logging.Logger,
) -> Dict[str, Any]:
    """
    Run comprehensive analysis for a single file or the whole project.

    Args:
        root_path: Root directory as Path.
        db: Database-like object used to read indexed file list.
        project_id: Project UUID.
        file_path: Optional absolute path to specific file.
        config: Analysis configuration.
        progress_tracker: Optional progress tracker instance.
        analysis_logger: Dedicated logger for the analysis run.

    Returns:
        Results dict compatible with the MCP response format.
    """

    analyzer = ComprehensiveAnalyzer(max_lines=config.max_lines)
    detector = None
    if config.check_duplicates:
        detector = DuplicateDetector(
            min_lines=config.duplicate_min_lines,
            min_similarity=config.duplicate_min_similarity,
            use_semantic=False,
        )

    results: Dict[str, Any] = {
        "placeholders": [],
        "stubs": [],
        "empty_methods": [],
        "imports_not_at_top": [],
        "long_files": [],
        "duplicates": [],
        "flake8_errors": [],
        "mypy_errors": [],
        "summary": {},
    }

    if progress_tracker:
        progress_tracker.set_status("running")
        progress_tracker.set_description("Initializing comprehensive analysis...")
        progress_tracker.set_progress(0)

    if file_path is not None:
        rel_path = str(file_path.relative_to(root_path))
        if should_exclude_path(file_path, config.exclude_dir_names):
            raise ValueError(f"File is excluded from analysis: {rel_path}")
        if not is_python_file(file_path):
            raise ValueError(f"Only Python (.py) files are supported: {rel_path}")

        logger.info("Analyzing single file: %s", rel_path)
        analysis_logger.info("Starting analysis of single file: %s", rel_path)

        file_results = analyze_single_python_file(
            analyzer=analyzer,
            detector=detector,
            file_path_obj=file_path,
            rel_path=rel_path,
            config=config,
        )
        results.update(file_results)
        return _finalize_results(results)

    all_placeholders: List[Dict[str, Any]] = []
    all_stubs: List[Dict[str, Any]] = []
    all_empty_methods: List[Dict[str, Any]] = []
    all_imports_not_at_top: List[Dict[str, Any]] = []
    all_duplicates: List[Dict[str, Any]] = []
    all_flake8_errors: List[Dict[str, Any]] = []
    all_mypy_errors: List[Dict[str, Any]] = []
    file_records_for_long_files: List[Dict[str, Any]] = []

    iterable = list(
        iter_project_python_files_from_db(
            db=db,
            project_id=project_id,
            root_path=root_path,
            exclude_dir_names=config.exclude_dir_names,
        )
    )
    files_total = len(iterable)

    analysis_logger.info(
        "Starting comprehensive analysis: %s Python files to analyze", files_total
    )
    if progress_tracker:
        progress_tracker.set_description(f"Analyzing {files_total} Python files...")
        progress_tracker.set_progress(0)

    last_percent = -1
    for idx, rec in enumerate(iterable):
        file_path_str = rec["path"]
        full_path: Path = rec["full_path"]

        try:
            source_code = full_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read file %s: %s", file_path_str, e)
            continue

        file_records_for_long_files.append(
            {"path": file_path_str, "lines": rec.get("lines", 0)}
        )

        logger.info("Analyzing file %s/%s: %s", idx + 1, files_total, file_path_str)
        analysis_logger.info(
            "Analyzing file %s/%s: %s", idx + 1, files_total, file_path_str
        )

        if config.check_placeholders:
            placeholders = analyzer.find_placeholders(full_path, source_code)
            for p in placeholders:
                p["file_path"] = file_path_str
            all_placeholders.extend(placeholders)

        if config.check_stubs:
            stubs = analyzer.find_stubs(full_path, source_code)
            for s in stubs:
                s["file_path"] = file_path_str
            all_stubs.extend(stubs)

        if config.check_empty_methods:
            empty_methods = analyzer.find_empty_methods(full_path, source_code)
            for m in empty_methods:
                m["file_path"] = file_path_str
            all_empty_methods.extend(empty_methods)

        if config.check_imports:
            imports_not_at_top = analyzer.find_imports_not_at_top(
                full_path, source_code
            )
            for imp in imports_not_at_top:
                imp["file_path"] = file_path_str
            all_imports_not_at_top.extend(imports_not_at_top)

        if config.check_duplicates and detector is not None:
            duplicates = detector.find_duplicates_in_file(str(full_path))
            for group in duplicates:
                for occ in group["occurrences"]:
                    occ["file_path"] = file_path_str
            all_duplicates.extend(duplicates)

        if config.check_flake8:
            flake8_result = analyzer.check_flake8(full_path)
            if not flake8_result["success"]:
                flake8_result["file_path"] = file_path_str
                all_flake8_errors.append(flake8_result)

        if config.check_mypy:
            mypy_result = analyzer.check_mypy(full_path, config.mypy_config)
            if not mypy_result["success"]:
                mypy_result["file_path"] = file_path_str
                all_mypy_errors.append(mypy_result)

        if progress_tracker and files_total > 0:
            percent = int(((idx + 1) / files_total) * 100)
            if percent != last_percent:
                progress_tracker.set_progress(percent)
                progress_tracker.set_description(
                    f"Analyzing: {idx + 1}/{files_total} ({percent}%)"
                )
                last_percent = percent

    results["placeholders"] = all_placeholders
    results["stubs"] = all_stubs
    results["empty_methods"] = all_empty_methods
    results["imports_not_at_top"] = all_imports_not_at_top
    results["duplicates"] = all_duplicates
    results["flake8_errors"] = all_flake8_errors
    results["mypy_errors"] = all_mypy_errors

    if config.check_long_files:
        results["long_files"] = analyzer.find_long_files(file_records_for_long_files)

    return _finalize_results(results)


def _finalize_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add summary to results and return the same dict.

    Args:
        results: Results dict (mutated in place).

    Returns:
        The same dict with `summary` populated.
    """

    results["summary"] = {
        "total_placeholders": len(results["placeholders"]),
        "total_stubs": len(results["stubs"]),
        "total_empty_methods": len(results["empty_methods"]),
        "total_imports_not_at_top": len(results["imports_not_at_top"]),
        "total_long_files": len(results.get("long_files") or []),
        "total_duplicate_groups": len(results["duplicates"]),
        "total_duplicate_occurrences": sum(
            len(g["occurrences"]) for g in results["duplicates"]
        ),
        "total_flake8_errors": sum(
            e.get("error_count", 0) for e in results["flake8_errors"]
        ),
        "files_with_flake8_errors": len(results["flake8_errors"]),
        "total_mypy_errors": sum(
            e.get("error_count", 0) for e in results["mypy_errors"]
        ),
        "files_with_mypy_errors": len(results["mypy_errors"]),
    }
    return results
