"""
Batch (multi-file) execution for comprehensive_analysis MCP command.

Runs analysis for multiple project files: pagination, per-file checks,
batch save, long-files check, summary, return.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from mcp_proxy_adapter.commands.result import SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ...core.sql_portable import WHERE_FILES_ACTIVE
from .batch_one_file import analyze_one_file_in_batch
from .batch_summary import build_batch_summary, _merge_project_integrity_summary

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 15
_BATCH_SAVE_SIZE = 100


async def run_batch(
    cmd: BaseMCPCommand,
    ctx: Dict[str, Any],
) -> SuccessResult:
    """
    Run comprehensive analysis for multiple files (batch mode).

    Uses ctx for db, root_path, proj_id, analysis_logger, log_timing,
    progress_tracker, analyzer, results, and all execute params including
    limit, offset. Mutates ctx["results"] and returns SuccessResult.
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
    limit = ctx["limit"]
    offset = ctx["offset"]
    t_start = ctx["t_start"]
    check_placeholders = ctx["check_placeholders"]
    check_stubs = ctx["check_stubs"]
    check_empty_methods = ctx["check_empty_methods"]
    check_imports = ctx["check_imports"]
    check_long_files = ctx["check_long_files"]
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

    t_get_files = time.perf_counter()
    batch_size = limit if limit is not None else _DEFAULT_BATCH_SIZE
    batch_offset = offset
    if limit is None:
        if proj_id:
            count_result = db.execute(
                "SELECT COUNT(*) as c FROM files WHERE project_id = ? AND "
                + WHERE_FILES_ACTIVE,
                (proj_id,),
            )
        else:
            count_result = db.execute(
                "SELECT COUNT(*) as c FROM files WHERE " + WHERE_FILES_ACTIVE
            )
        files_total = (
            (count_result.get("data") or [{}])[0].get("c", 0)
            if isinstance(count_result.get("data"), list)
            else 0
        )
        analysis_logger.info(
            f"Starting comprehensive analysis: {files_total} files in batches of {_DEFAULT_BATCH_SIZE}"
        )
        if progress_tracker and files_total > 0:
            progress_tracker.set_description(
                f"Processing {files_total} file(s) for analysis..."
            )
    else:
        files_total = 0

    all_placeholders: List[Dict[str, Any]] = []
    all_stubs: List[Dict[str, Any]] = []
    all_empty_methods: List[Dict[str, Any]] = []
    all_imports_not_at_top: List[Dict[str, Any]] = []
    all_duplicates: List[Dict[str, Any]] = []
    all_flake8_errors: List[Dict[str, Any]] = []
    all_mypy_errors: List[Dict[str, Any]] = []
    all_black_findings: List[Dict[str, Any]] = []
    all_isort_findings: List[Dict[str, Any]] = []
    all_bandit_findings: List[Dict[str, Any]] = []
    all_missing_docstrings: List[Dict[str, Any]] = []
    file_records: List[Dict[str, Any]] = []

    files_analyzed = 0
    # Legacy summary key: skipped only when mtime/up-to-date gate says not to re-analyze.
    files_skipped = 0
    # Explicit bucket matching files_skipped (gate / up-to-date); kept in sync for clarity in summary.
    files_skipped_up_to_date = 0
    # Missing path, not a file, stat() failure, or read_text failure (rows that hit continue before analyze).
    files_skipped_unreadable_or_missing = 0
    t_loop_start = time.perf_counter()

    def _avg_eta_suffix(current: int, total: int, start_sec: float) -> str:
        """Return ' | avg X.Xs/file ETA HH:MM' or '' if not computable."""
        if current <= 0 or total <= 0:
            return ""
        elapsed = time.perf_counter() - start_sec
        if elapsed <= 0:
            return ""
        avg_sec = elapsed / current
        remaining = total - current
        if remaining <= 0:
            return f" | avg {avg_sec:.1f}s/file"
        eta_sec = remaining * avg_sec
        eta_dt = datetime.now() + timedelta(seconds=eta_sec)
        return f" | avg {avg_sec:.1f}s/file ETA {eta_dt:%H:%M}"

    save_batch: List[tuple] = []
    timings_sec: Dict[str, float] = {
        "placeholders": 0.0,
        "stubs": 0.0,
        "empty_methods": 0.0,
        "imports": 0.0,
        "duplicates": 0.0,
        "flake8": 0.0,
        "mypy": 0.0,
        "black": 0.0,
        "isort": 0.0,
        "bandit": 0.0,
        "docstrings": 0.0,
        "read_file": 0.0,
        "save": 0.0,
    }

    project_mypy_errors: Dict[str, List[str]] = {}
    if check_mypy:
        if progress_tracker:
            progress_tracker.set_description("Analysis: mypy (project)")
        t0 = time.perf_counter()
        from ...core.code_quality.type_checker import (
            type_check_project_with_mypy,
        )

        _, project_mypy_errors = type_check_project_with_mypy(root_path, mypy_config)
        timings_sec["mypy"] += time.perf_counter() - t0
        analysis_logger.info(
            "[TIMING] phase=mypy_project_once elapsed_sec=%.4f",
            timings_sec["mypy"],
        )

    while True:
        if proj_id:
            project_files = db.get_project_files(
                proj_id,
                include_deleted=False,
                limit=batch_size,
                offset=batch_offset,
            )
            files = []
            for f in project_files:
                if isinstance(f, dict):
                    files.append(
                        {
                            "id": f["id"],
                            "path": f.get("path", ""),
                            "lines": f.get("lines", 0),
                            "project_id": f.get("project_id"),
                        }
                    )
                else:
                    files.append(
                        {
                            "id": getattr(f, "id", None),
                            "path": getattr(f, "path", None)
                            or getattr(f, "relative_path", "")
                            or "",
                            "lines": getattr(f, "lines", None) or 0,
                            "project_id": getattr(f, "project_id", None),
                        }
                    )
        else:
            rows = db.select(
                "files",
                where={"deleted": 0},
                order_by=["path"],
                limit=batch_size,
                offset=batch_offset,
            )
            files = [
                {
                    "id": r.get("id"),
                    "path": r.get("path", ""),
                    "lines": r.get("lines", 0),
                    "project_id": r.get("project_id"),
                }
                for r in (rows or [])
            ]

        if not files:
            break
        if limit is not None and files_total == 0:
            files_total = len(files)

        log_timing("multi_get_files", t_get_files)
        if progress_tracker and files_total > 0:
            progress_tracker.set_description(f"Analyzing: 0/{files_total} (0%)")
            progress_tracker.set_progress(0)

        for idx, file_record in enumerate(files):
            t_file_start = time.perf_counter()
            file_path_str = file_record["path"]
            file_id = file_record["id"]

            # Show current file in progress (for every file we consider, skip or analyze)
            if progress_tracker and files_total > 0:
                global_idx = batch_offset + idx + 1
                percent = int((global_idx / files_total) * 100)
                file_name = Path(file_path_str).name
                progress_tracker.set_progress(percent)
                suffix = _avg_eta_suffix(global_idx, files_total, t_start)
                progress_tracker.set_description(
                    f"Analyzing: {global_idx}/{files_total} ({percent}%) — {file_name}{suffix}"
                )

            if Path(file_path_str).is_absolute():
                full_path = Path(file_path_str)
            else:
                full_path = root_path / file_path_str

            if not full_path.exists() or not full_path.is_file():
                logger.debug(f"Skipping non-existent file: {file_path_str}")
                files_skipped_unreadable_or_missing += 1
                continue

            try:
                file_mtime = full_path.stat().st_mtime
            except Exception as e:
                logger.warning(f"Failed to get mtime for {file_path_str}: {e}")
                files_skipped_unreadable_or_missing += 1
                continue

            if hasattr(db, "should_analyze_file"):
                gate = db.should_analyze_file(file_id, file_mtime)
                if not gate["should_analyze"]:
                    files_skipped += 1
                    files_skipped_up_to_date += 1
                    reason = gate.get("reason", "unknown")
                    logger.debug(
                        "Skipping %s: %s (disk_mtime older or equal)",
                        file_path_str,
                        reason,
                    )
                    analysis_logger.debug(
                        "Skipping %s: %s (db_mtime=%s, disk_mtime=%s)",
                        file_path_str,
                        reason,
                        gate.get("db_mtime"),
                        gate.get("disk_mtime"),
                    )
                    file_records.append(
                        {
                            "path": file_path_str,
                            "lines": file_record.get("lines", 0),
                        }
                    )
                    continue

            t0 = time.perf_counter()
            try:
                source_code = full_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to read file {file_path_str}: {e}")
                files_skipped_unreadable_or_missing += 1
                continue
            timings_sec["read_file"] += time.perf_counter() - t0

            file_records.append(
                {
                    "path": file_path_str,
                    "lines": file_record.get("lines", 0),
                }
            )

            files_analyzed += 1
            global_idx = batch_offset + idx + 1
            percent = int((global_idx / files_total) * 100)
            file_name = Path(file_path_str).name
            logger.info(f"Analyzing file {global_idx}/{files_total}: {file_path_str}")
            analysis_logger.info(
                f"Analyzing file {global_idx}/{files_total}: {file_path_str}"
            )

            def set_step_desc(step: str) -> None:
                """Update progress text for the current batch analysis step."""
                if progress_tracker and files_total > 0:
                    suffix = _avg_eta_suffix(global_idx, files_total, t_start)
                    progress_tracker.set_description(
                        f"Analyzing: {global_idx}/{files_total} ({percent}%) — {step}{suffix}"
                    )

            file_results, file_summary, file_project_id = analyze_one_file_in_batch(
                full_path,
                file_path_str,
                source_code,
                file_id,
                file_record,
                proj_id,
                analyzer,
                project_mypy_errors,
                timings_sec,
                check_placeholders,
                check_stubs,
                check_empty_methods,
                check_imports,
                check_duplicates,
                check_flake8,
                check_mypy,
                check_docstrings,
                duplicate_min_lines,
                duplicate_min_similarity,
                set_step_desc=set_step_desc,
                check_black=check_black,
                check_isort=check_isort,
                check_bandit=check_bandit,
                bandit_config=bandit_config,
            )
            all_placeholders.extend(file_results["placeholders"])
            all_stubs.extend(file_results["stubs"])
            all_empty_methods.extend(file_results["empty_methods"])
            all_imports_not_at_top.extend(file_results["imports_not_at_top"])
            all_duplicates.extend(file_results["duplicates"])
            all_flake8_errors.extend(file_results["flake8_errors"])
            all_mypy_errors.extend(file_results["mypy_errors"])
            all_black_findings.extend(file_results.get("black_findings", []))
            all_isort_findings.extend(file_results.get("isort_findings", []))
            all_bandit_findings.extend(file_results.get("bandit_findings", []))
            all_missing_docstrings.extend(file_results["missing_docstrings"])

            if file_project_id:
                save_batch.append(
                    (
                        file_id,
                        file_project_id,
                        file_mtime,
                        file_results,
                        file_summary,
                    )
                )
                if len(save_batch) >= _BATCH_SAVE_SIZE:
                    try:
                        t_save0 = time.perf_counter()
                        db.save_comprehensive_analysis_results_batch(save_batch)
                        timings_sec["save"] += time.perf_counter() - t_save0
                        analysis_logger.info(
                            "Saved batch of %s analysis results",
                            len(save_batch),
                        )
                        save_batch.clear()
                    except Exception as e:
                        logger.error(
                            "Failed to save analysis results batch: %s",
                            e,
                            exc_info=True,
                        )
                        analysis_logger.error(
                            "Failed to save analysis results batch: %s", e
                        )
            else:
                logger.warning(
                    "Cannot save results for %s: project_id not available",
                    file_path_str,
                )

            file_elapsed = time.perf_counter() - t_file_start
            analysis_logger.info(
                "[TIMING] phase=multi_file_one file=%s elapsed_sec=%.4f",
                file_path_str,
                file_elapsed,
            )

        batch_offset += len(files)
        if limit is not None:
            break
        if len(files) < batch_size:
            break
        t_get_files = time.perf_counter()

    if save_batch:
        if progress_tracker:
            progress_tracker.set_description("Analysis: saving results")
        try:
            t_save0 = time.perf_counter()
            db.save_comprehensive_analysis_results_batch(save_batch)
            timings_sec["save"] += time.perf_counter() - t_save0
            analysis_logger.info(
                "Saved final batch of %s analysis results",
                len(save_batch),
            )
        except Exception as e:
            logger.error(
                "Failed to save final analysis results batch: %s",
                e,
                exc_info=True,
            )
            analysis_logger.error("Failed to save final analysis results batch: %s", e)

    loop_elapsed = time.perf_counter() - t_loop_start
    analysis_logger.info(
        "[TIMING] phase=multi_file_loop_total elapsed_sec=%.4f files_analyzed=%s",
        loop_elapsed,
        files_analyzed,
    )
    parts = " ".join(f"{k}_sec={v:.4f}" for k, v in sorted(timings_sec.items()))
    analysis_logger.info("[TIMING] phase=multi_file_breakdown %s", parts)

    results["placeholders"] = all_placeholders
    results["stubs"] = all_stubs
    results["empty_methods"] = all_empty_methods
    results["imports_not_at_top"] = all_imports_not_at_top
    results["duplicates"] = all_duplicates
    results["flake8_errors"] = all_flake8_errors
    results["mypy_errors"] = all_mypy_errors
    results["black_findings"] = all_black_findings
    results["isort_findings"] = all_isort_findings
    results["bandit_findings"] = all_bandit_findings
    results["missing_docstrings"] = all_missing_docstrings

    if check_long_files:
        t0 = time.perf_counter()
        results["long_files"] = analyzer.find_long_files(file_records)
        log_timing("multi_long_files", t0)

    analysis_logger.info(
        "Analysis complete: analyzed=%s skipped_up_to_date=%s skipped_missing_or_unreadable=%s",
        files_analyzed,
        files_skipped,
        files_skipped_unreadable_or_missing,
    )

    if progress_tracker:
        progress_tracker.set_description("Analysis: building summary")
    results["summary"] = build_batch_summary(
        results,
        files_analyzed,
        files_skipped,
        files_total,
        files_skipped_up_to_date=files_skipped_up_to_date,
        files_skipped_unreadable_or_missing=files_skipped_unreadable_or_missing,
    )

    log_timing("total_elapsed", t_start)
    db.disconnect()

    if progress_tracker:
        progress_tracker.set_progress(100)
        progress_tracker.set_description("Analysis completed")
        progress_tracker.set_status("completed")

    analysis_logger.info(
        f"Comprehensive analysis completed. Summary: {results['summary']}"
    )

    for handler in analysis_logger.handlers[:]:
        handler.close()
        analysis_logger.removeHandler(handler)

    return SuccessResult(data=results)
