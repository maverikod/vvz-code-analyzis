"""
Build summary dict for comprehensive_analysis batch results.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict


def build_batch_summary(
    results: Dict[str, Any],
    files_analyzed: int,
    files_skipped: int,
    files_total: int,
) -> Dict[str, Any]:
    """Build summary_data dict from aggregated results and counts."""
    return {
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
        "total_mypy_errors": sum(
            e.get("error_count", 0) for e in results["mypy_errors"]
        ),
        "files_with_mypy_errors": len(results["mypy_errors"]),
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
    }
