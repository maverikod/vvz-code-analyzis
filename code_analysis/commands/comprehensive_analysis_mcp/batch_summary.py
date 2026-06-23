"""
Build summary dict for comprehensive_analysis batch results.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List, Tuple

__all__ = [
    "build_batch_summary",
    "build_single_file_summary",
    "mypy_diagnostic_counts",
    "quality_findings_counts",
]

# Opt-in quality tools whose findings are stored as ``<tool>_findings`` lists.
_QUALITY_FINDING_TOOLS = ("black", "isort", "bandit")


def quality_findings_counts(results: Dict[str, Any]) -> Dict[str, int]:
    """Summary counters for black/isort/bandit findings.

    Produces ``total_<tool>_findings`` (sum of per-file error_count) and
    ``files_with_<tool>_findings`` (number of files with any finding) for each
    opt-in tool. Always returns all keys (zero when the check did not run).
    """
    counts: Dict[str, int] = {}
    for tool in _QUALITY_FINDING_TOOLS:
        rows = results.get(f"{tool}_findings") or []
        counts[f"total_{tool}_findings"] = sum(
            int(r.get("error_count") or 0) for r in rows
        )
        counts[f"files_with_{tool}_findings"] = len(rows)
    return counts


def mypy_diagnostic_counts(
    rows: List[Dict[str, Any]],
) -> Tuple[int, int]:
    """Return (total_error_lines, files_with_positive_error_count) for mypy result rows."""
    total = 0
    files_with = 0
    for row in rows:
        ec = int(row.get("error_count") or 0)
        if ec > 0:
            total += ec
            files_with += 1
    return total, files_with


def build_single_file_summary(
    results: Dict[str, Any],
    files_analyzed: int,
    files_skipped: int,
    files_total: int,
) -> Dict[str, Any]:
    """Summary for a single analyzed file (same mypy keys as batch, scoped to one pass)."""
    mypy_rows = results.get("mypy_errors") or []
    total_mypy, files_mypy = mypy_diagnostic_counts(mypy_rows)
    return {
        "total_mypy_errors": total_mypy,
        "files_with_mypy_errors": files_mypy,
        "files_analyzed": files_analyzed,
        "files_skipped": files_skipped,
        "files_total": files_total,
    }


def build_batch_summary(
    results: Dict[str, Any],
    files_analyzed: int,
    files_skipped: int,
    files_total: int,
    *,
    files_skipped_up_to_date: int = 0,
    files_skipped_unreadable_or_missing: int = 0,
) -> Dict[str, Any]:
    """Build summary_data dict from aggregated results and counts.

    Trust counters: ``files_skipped`` remains the legacy key (mtime / up-to-date gate only).
    ``files_skipped_up_to_date`` matches that semantics. ``files_skipped_unreadable_or_missing``
    counts rows skipped before analysis (missing path, not a file, stat/read errors).

    For a full scan with one pass per DB row:
    ``files_analyzed + files_skipped + files_skipped_unreadable_or_missing == files_total``.
    """
    mypy_rows = results.get("mypy_errors") or []
    total_mypy, files_mypy = mypy_diagnostic_counts(mypy_rows)
    summary: Dict[str, Any] = {
        "total_placeholders": len(results["placeholders"]),
        "total_stubs": len(results["stubs"]),
        "total_empty_methods": len(results["empty_methods"]),
        "total_imports_not_at_top": len(results["imports_not_at_top"]),
        "total_long_files": len(results["long_files"]),
        "total_duplicate_groups": len(results["duplicates"]),
        "total_duplicate_occurrences": sum(
            len(g["occurrences"]) for g in results["duplicates"]
        ),
        "total_flake8_errors": sum(
            e.get("error_count", 0) for e in results["flake8_errors"]
        ),
        "files_with_flake8_errors": len(results["flake8_errors"]),
        "total_mypy_errors": total_mypy,
        "files_with_mypy_errors": files_mypy,
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
        "files_analyzed": files_analyzed,
        "files_skipped": files_skipped,
        "files_total": files_total,
        "files_skipped_up_to_date": files_skipped_up_to_date,
        "files_skipped_unreadable_or_missing": files_skipped_unreadable_or_missing,
    }
    summary.update(quality_findings_counts(results))
    integrity = results.get("project_integrity") or {}
    if integrity:
        summary = _merge_project_integrity_summary(summary, integrity)
    return summary


def _merge_project_integrity_summary(
    summary: Dict[str, Any],
    integrity: Dict[str, Any],
) -> Dict[str, Any]:
    """Add project-level integrity counters (issues table) to batch summary."""
    summary = dict(summary)
    summary["project_integrity_skipped"] = bool(integrity.get("skipped"))
    summary["project_integrity_skip_reason"] = integrity.get("reason")
    summary["total_missing_files_on_disk"] = int(
        integrity.get("missing_files_count") or 0
    )
    summary["total_circular_imports"] = int(
        integrity.get("circular_imports_count") or 0
    )
    summary["integrity_issues_cleared"] = int(integrity.get("cleared_issues") or 0)
    # Entity-index self-check (C-1): surface loudly in the summary.
    if "entity_index_ok" in integrity:
        summary["entity_index_ok"] = bool(integrity.get("entity_index_ok"))
        ei = integrity.get("entity_index") or {}
        summary["entity_index_entities"] = int(ei.get("entities") or 0)
    return summary
