"""
Single-file execution for comprehensive_analysis MCP command.

Runs analysis for one file: DB lookup, optional cache, checks, save, return.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ...core.database_driver_pkg.domain.comprehensive_analysis import (
    save_comprehensive_analysis_results,
    should_analyze_file,
)
from ...core.database_driver_pkg.domain.files import get_file_by_path
from ...core.duplicate_detector import DuplicateDetector
from ..base_mcp_command import BaseMCPCommand
from .batch_summary import _merge_project_integrity_summary, quality_findings_counts

logger = logging.getLogger(__name__)


async def run_single_file(
    cmd: BaseMCPCommand,
    ctx: Dict[str, Any],
):
    """
    Run comprehensive analysis for a single file.

    Uses ctx for db, root_path, proj_id, analysis_logger, log_timing,
    progress_tracker, analyzer, results, mypy_config, and all execute params.
    """
    db = ctx["db"]
    root_path = ctx["root_path"]
    proj_id = ctx["proj_id"]
    analysis_logger = ctx["analysis_logger"]
    log_timing = ctx["log_timing"]
    progress_tracker = ctx["progress_tracker"]
    analyzer = ctx["analyzer"]
    results = ctx["results"]
    mypy_config = ctx["mypy_config"]
    file_path = ctx["file_path"]
    check_placeholders = ctx["check_placeholders"]
    check_stubs = ctx["check_stubs"]
    check_empty_methods = ctx["check_empty_methods"]
    check_imports = ctx["check_imports"]
    check_duplicates = ctx["check_duplicates"]
    check_flake8 = ctx["check_flake8"]
    check_mypy = ctx["check_mypy"]
    check_black = ctx.get("check_black", False)
    check_isort = ctx.get("check_isort", False)
    check_bandit = ctx.get("check_bandit", False)
    bandit_config = ctx.get("bandit_config")
    check_docstrings = ctx["check_docstrings"]
    duplicate_min_lines = ctx["duplicate_min_lines"]
    duplicate_min_similarity = ctx["duplicate_min_similarity"]

    t_single_start = time.perf_counter()
    if progress_tracker:
        progress_tracker.set_description("Analyzing: 1/1 (0%)")
    file_path_obj = cmd._validate_file_path(file_path, root_path)
    if not file_path_obj.exists():
        db.disconnect()
        return ErrorResult(message="File not found", code="FILE_NOT_FOUND")

    abs_path = str(file_path_obj.resolve())
    rel_path = str(file_path_obj.relative_to(root_path))
    file_mtime = file_path_obj.stat().st_mtime
    file_id = None
    file_project_id = proj_id

    if proj_id:
        file_record = get_file_by_path(db, abs_path, proj_id, include_deleted=False)
        if file_record:
            file_id = file_record["id"]
            file_project_id = proj_id
            analysis_logger.debug(
                f"Found file in project: file_id={file_id}, project_id={file_project_id}"
            )
        else:
            file_record_deleted = get_file_by_path(
                db, abs_path, proj_id, include_deleted=True
            )
            if file_record_deleted and file_record_deleted.get("deleted"):
                analysis_logger.warning(
                    f"File found in project {proj_id} but marked as deleted (file_id={file_record_deleted['id']}). "
                    f"File exists on disk at {abs_path}. This indicates data inconsistency."
                )
            else:
                # Diagnostic only: same absolute path may appear under another project
                # (nested roots, relocation). Normal analysis must not mutate other rows.
                diag_result = db.execute(
                    "SELECT id, project_id, deleted FROM files WHERE path = ? LIMIT 1",
                    (abs_path,),
                )
                diag_rows = diag_result.get("data", [])
                other_row = diag_rows[0] if diag_rows else None
                if other_row:
                    other_pid = other_row.get("project_id")
                    if str(other_pid) == str(proj_id):
                        analysis_logger.warning(
                            f"Database lookup inconsistency: path {abs_path} has row "
                            f"file_id={other_row.get('id')} for project {proj_id} but "
                            f"get_file_by_path returned no active row. deleted={other_row.get('deleted')}"
                        )
                    else:
                        wrong_file_id = other_row["id"]
                        wrong_project_id = other_row["project_id"]
                        is_deleted = other_row.get("deleted", 0)
                        analysis_logger.warning(
                            f"Cross-project path overlap (diagnostic only): file on disk at {abs_path} "
                            f"is indexed as file_id={wrong_file_id} in project {wrong_project_id} "
                            f"(requested project {proj_id}), deleted={is_deleted}. "
                            f"Not clearing or reassigning that row; analysis runs without a "
                            f"file row for the requested project."
                        )
                        logger.warning(
                            "Cross-project path overlap in comprehensive_analysis single-file: "
                            "abs_path=%s indexed_project=%s requested_project=%s file_id=%s",
                            abs_path,
                            wrong_project_id,
                            proj_id,
                            wrong_file_id,
                        )
                else:
                    analysis_logger.info(
                        f"File not found in project {proj_id} database (may be unindexed): {abs_path}"
                    )
    else:
        analysis_logger.info(
            f"No project_id specified, cannot look up file in database: {abs_path}"
        )

    log_timing("single_file_db_lookup", t_single_start)

    # Single-file comprehensive analysis always runs checks (no stale mtime-cache short
    # circuit). Log when the DB gate would skip; callers still get fresh analyzer output.
    if file_id and file_project_id:
        gate = should_analyze_file(db, file_id, file_mtime)
        if not gate["should_analyze"]:
            analysis_logger.info(
                "DB mtime gate would skip %s (%s); running single-file analyzers anyway "
                "(db_mtime=%s, disk_mtime=%s)",
                rel_path,
                gate.get("reason", "unknown"),
                gate.get("db_mtime"),
                gate.get("disk_mtime"),
            )

    logger.info(f"Analyzing single file: {rel_path}")
    analysis_logger.info(f"Starting analysis of single file: {rel_path}")
    t0 = time.perf_counter()
    source_code = file_path_obj.read_text(encoding="utf-8")
    log_timing("single_file_read", t0)

    if check_placeholders:
        t0 = time.perf_counter()
        placeholders = analyzer.find_placeholders(file_path_obj, source_code)
        for p in placeholders:
            p["file_path"] = rel_path
        results["placeholders"] = placeholders
        log_timing("single_placeholders", t0)

    if check_stubs:
        t0 = time.perf_counter()
        stubs = analyzer.find_stubs(file_path_obj, source_code)
        for s in stubs:
            s["file_path"] = rel_path
        results["stubs"] = stubs
        log_timing("single_stubs", t0)

    if check_empty_methods:
        t0 = time.perf_counter()
        empty_methods = analyzer.find_empty_methods(file_path_obj, source_code)
        for m in empty_methods:
            m["file_path"] = rel_path
        results["empty_methods"] = empty_methods
        log_timing("single_empty_methods", t0)

    if check_imports:
        t0 = time.perf_counter()
        imports_not_at_top = analyzer.find_imports_not_at_top(
            file_path_obj, source_code
        )
        for imp in imports_not_at_top:
            imp["file_path"] = rel_path
        results["imports_not_at_top"] = imports_not_at_top
        log_timing("single_imports", t0)

    if check_duplicates:
        t0 = time.perf_counter()
        detector = DuplicateDetector(
            min_lines=duplicate_min_lines,
            min_similarity=duplicate_min_similarity,
            use_semantic=False,
        )
        duplicates = detector.find_duplicates_in_file(str(file_path_obj))
        for group in duplicates:
            for occ in group["occurrences"]:
                occ["file_path"] = rel_path
        results["duplicates"] = duplicates
        log_timing("single_duplicates", t0)

    if check_flake8:
        t0 = time.perf_counter()
        flake8_result = analyzer.check_flake8(file_path_obj)
        if not flake8_result["success"]:
            flake8_result["file_path"] = rel_path
            results["flake8_errors"].append(flake8_result)
        log_timing("single_flake8", t0)

    if check_mypy:
        t0 = time.perf_counter()
        mypy_result = analyzer.check_mypy(file_path_obj, mypy_config)
        if not mypy_result["success"]:
            mypy_result["file_path"] = rel_path
            results["mypy_errors"].append(mypy_result)
        log_timing("single_mypy", t0)

    if check_black:
        t0 = time.perf_counter()
        black_result = analyzer.check_black(file_path_obj)
        if not black_result["success"]:
            black_result["file_path"] = rel_path
            results["black_findings"].append(black_result)
        log_timing("single_black", t0)

    if check_isort:
        t0 = time.perf_counter()
        isort_result = analyzer.check_isort(file_path_obj)
        if not isort_result["success"]:
            isort_result["file_path"] = rel_path
            results["isort_findings"].append(isort_result)
        log_timing("single_isort", t0)

    if check_bandit:
        t0 = time.perf_counter()
        bandit_result = analyzer.check_bandit(file_path_obj, bandit_config)
        if not bandit_result["success"]:
            bandit_result["file_path"] = rel_path
            results["bandit_findings"].append(bandit_result)
        log_timing("single_bandit", t0)

    if check_docstrings:
        t0 = time.perf_counter()
        missing_docstrings = analyzer.find_missing_docstrings(
            file_path_obj, source_code
        )
        for d in missing_docstrings:
            d["file_path"] = rel_path
        results["missing_docstrings"] = missing_docstrings
        log_timing("single_docstrings", t0)

    if file_id and file_project_id and (proj_id is None or file_project_id == proj_id):
        try:
            t_save0 = time.perf_counter()
            analysis_logger.info(
                f"Saving results for file_id={file_id}, project_id={file_project_id}, mtime={file_mtime}"
            )
            file_summary = {
                "total_placeholders": len(results["placeholders"]),
                "total_stubs": len(results["stubs"]),
                "total_empty_methods": len(results["empty_methods"]),
                "total_imports_not_at_top": len(results["imports_not_at_top"]),
                "total_duplicate_groups": len(results["duplicates"]),
                "total_duplicate_occurrences": sum(
                    len(g["occurrences"]) for g in results["duplicates"]
                ),
                "total_flake8_errors": sum(
                    e.get("error_count", 0) for e in results.get("flake8_errors", [])
                ),
                "files_with_flake8_errors": len(results.get("flake8_errors", [])),
                "total_mypy_errors": sum(
                    e.get("error_count", 0) for e in results.get("mypy_errors", [])
                ),
                "files_with_mypy_errors": len(results.get("mypy_errors", [])),
                "total_missing_docstrings": len(results["missing_docstrings"]),
                **quality_findings_counts(results),
            }
            save_comprehensive_analysis_results(
                db,
                file_id=file_id,
                project_id=file_project_id,
                file_mtime=file_mtime,
                results=results,
                summary=file_summary,
            )
            log_timing("single_file_save", t_save0)
            analysis_logger.info(f"Saved analysis results for {rel_path}")
        except Exception as e:
            logger.error(
                f"Failed to save analysis results for {rel_path}: {e}",
                exc_info=True,
            )
            analysis_logger.error(
                f"Failed to save analysis results for {rel_path}: {e}",
                exc_info=True,
            )
    else:
        if file_id and file_project_id and proj_id and file_project_id != proj_id:
            analysis_logger.error(
                f"Data inconsistency detected: file_id={file_id} belongs to project {file_project_id}, "
                f"but analysis was requested for project {proj_id}. Results will not be saved."
            )
        else:
            analysis_logger.warning(
                f"Cannot save results: file_id={file_id}, file_project_id={file_project_id}, proj_id={proj_id}"
            )

    summary_data = {
        "total_placeholders": len(results["placeholders"]),
        "total_stubs": len(results["stubs"]),
        "total_empty_methods": len(results["empty_methods"]),
        "total_imports_not_at_top": len(results["imports_not_at_top"]),
        "total_long_files": 0,
        "total_duplicate_groups": len(results["duplicates"]),
        "total_duplicate_occurrences": sum(
            len(g["occurrences"]) for g in results["duplicates"]
        ),
        "total_flake8_errors": sum(
            e.get("error_count", 0) for e in results.get("flake8_errors", [])
        ),
        "files_with_flake8_errors": len(results.get("flake8_errors", [])),
        "total_mypy_errors": sum(
            e.get("error_count", 0) for e in results.get("mypy_errors", [])
        ),
        "files_with_mypy_errors": len(results.get("mypy_errors", [])),
        "total_missing_docstrings": len(results["missing_docstrings"]),
        "files_without_docstrings": len(
            set(
                d["file_path"]
                for d in results["missing_docstrings"]
                if d["type"] == "file"
            )
        ),
        "classes_without_docstrings": len(
            [d for d in results["missing_docstrings"] if d["type"] == "class"]
        ),
        "methods_without_docstrings": len(
            [d for d in results["missing_docstrings"] if d["type"] == "method"]
        ),
        "functions_without_docstrings": len(
            [d for d in results["missing_docstrings"] if d["type"] == "function"]
        ),
        "files_analyzed": 1,
        "files_skipped": 0,
        "files_total": 1,
        **quality_findings_counts(results),
    }
    integrity = results.get("project_integrity") or {}
    if integrity:
        summary_data = _merge_project_integrity_summary(summary_data, integrity)
    results["summary"] = summary_data

    db.disconnect()
    if progress_tracker:
        progress_tracker.set_progress(100)
        progress_tracker.set_description("Analysis completed")
        progress_tracker.set_status("completed")

    for handler in analysis_logger.handlers[:]:
        handler.close()
        analysis_logger.removeHandler(handler)

    return SuccessResult(data=results)
