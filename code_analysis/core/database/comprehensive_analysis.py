"""
Module comprehensive_analysis results storage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def save_comprehensive_analysis_results(
    self,
    file_id: int,
    project_id: str,
    file_mtime: float,
    results: Dict[str, Any],
    summary: Dict[str, Any],
) -> int:
    """
    Save comprehensive analysis results for a file.

    Args:
        file_id: File ID
        project_id: Project ID (UUID4 string)
        file_mtime: File modification time at analysis
        results: Analysis results dictionary
        summary: Summary statistics dictionary

    Returns:
        Analysis result ID
    """
    results_json = json.dumps(results, ensure_ascii=False)
    summary_json = json.dumps(summary, ensure_ascii=False)

    self._execute(
        """
            INSERT OR REPLACE INTO comprehensive_analysis_results
            (file_id, project_id, file_mtime, results_json, summary_json, updated_at)
            VALUES (?, ?, ?, ?, ?, julianday('now'))
        """,
        (file_id, project_id, file_mtime, results_json, summary_json),
    )
    self._commit()
    result = self._lastrowid()
    assert result is not None
    return result


def get_comprehensive_analysis_results(
    self, file_id: int, file_mtime: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Get comprehensive analysis results for a file.

    Args:
        file_id: File ID
        file_mtime: Optional file modification time to check if results are up-to-date

    Returns:
        Dictionary with 'results', 'summary', 'file_mtime', 'analysis_date' or None if not found
    """
    if file_mtime is not None:
        # Check if results are up-to-date
        row = self._fetchone(
            """
            SELECT results_json, summary_json, file_mtime, updated_at
            FROM comprehensive_analysis_results
            WHERE file_id = ? AND file_mtime = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (file_id, file_mtime),
        )
    else:
        # Get latest results regardless of mtime
        row = self._fetchone(
            """
            SELECT results_json, summary_json, file_mtime, updated_at
            FROM comprehensive_analysis_results
            WHERE file_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (file_id,),
        )

    if not row:
        return None

    try:
        results = json.loads(row["results_json"])
        summary = json.loads(row["summary_json"])
        return {
            "results": results,
            "summary": summary,
            "file_mtime": row["file_mtime"],
            "analysis_date": row["updated_at"],
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing analysis results for file_id {file_id}: {e}")
        return None


def is_analysis_up_to_date(
    self, file_id: int, file_mtime: float, tolerance: float = 0.1
) -> bool:
    """
    Check if comprehensive analysis results are up-to-date for a file.

    Args:
        file_id: File ID
        file_mtime: Current file modification time
        tolerance: Time tolerance in seconds (default: 0.1)

    Returns:
        True if analysis is up-to-date, False otherwise
    """
    row = self._fetchone(
        """
        SELECT file_mtime
        FROM comprehensive_analysis_results
        WHERE file_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (file_id,),
    )

    if not row:
        return False

    db_mtime = row["file_mtime"]
    # Check if mtime matches (within tolerance)
    return abs(file_mtime - db_mtime) <= tolerance


def delete_comprehensive_analysis_results(self, file_id: int) -> None:
    """
    Delete comprehensive analysis results for a file.

    Args:
        file_id: File ID
    """
    self._execute(
        """
        DELETE FROM comprehensive_analysis_results
        WHERE file_id = ?
        """,
        (file_id,),
    )
    self._commit()


def get_project_analysis_summary(
    self, project_id: str
) -> Dict[str, Any]:
    """
    Get summary of comprehensive analysis for all files in a project.

    Args:
        project_id: Project ID

    Returns:
        Dictionary with summary statistics
    """
    rows = self._fetchall(
        """
        SELECT summary_json, file_mtime, updated_at
        FROM comprehensive_analysis_results
        WHERE project_id = ?
        ORDER BY updated_at DESC
        """,
        (project_id,),
    )

    if not rows:
        return {
            "total_files_analyzed": 0,
            "total_placeholders": 0,
            "total_stubs": 0,
            "total_empty_methods": 0,
            "total_imports_not_at_top": 0,
            "total_long_files": 0,
            "total_duplicate_groups": 0,
            "total_flake8_errors": 0,
            "total_mypy_errors": 0,
            "total_missing_docstrings": 0,
        }

    total_placeholders = 0
    total_stubs = 0
    total_empty_methods = 0
    total_imports_not_at_top = 0
    total_long_files = 0
    total_duplicate_groups = 0
    total_flake8_errors = 0
    total_mypy_errors = 0
    total_missing_docstrings = 0

    for row in rows:
        try:
            summary = json.loads(row["summary_json"])
            total_placeholders += summary.get("total_placeholders", 0)
            total_stubs += summary.get("total_stubs", 0)
            total_empty_methods += summary.get("total_empty_methods", 0)
            total_imports_not_at_top += summary.get("total_imports_not_at_top", 0)
            total_long_files += summary.get("total_long_files", 0)
            total_duplicate_groups += summary.get("total_duplicate_groups", 0)
            total_flake8_errors += summary.get("total_flake8_errors", 0)
            total_mypy_errors += summary.get("total_mypy_errors", 0)
            total_missing_docstrings += summary.get("total_missing_docstrings", 0)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Error parsing summary for project {project_id}: {e}")
            continue

    return {
        "total_files_analyzed": len(rows),
        "total_placeholders": total_placeholders,
        "total_stubs": total_stubs,
        "total_empty_methods": total_empty_methods,
        "total_imports_not_at_top": total_imports_not_at_top,
        "total_long_files": total_long_files,
        "total_duplicate_groups": total_duplicate_groups,
        "total_flake8_errors": total_flake8_errors,
        "total_mypy_errors": total_mypy_errors,
        "total_missing_docstrings": total_missing_docstrings,
    }

