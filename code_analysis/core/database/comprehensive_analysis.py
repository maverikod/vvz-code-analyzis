"""
Module comprehensive_analysis results storage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from typing import Any, Dict, Optional

from code_analysis.core.sql_portable import sql_julian_timestamp_now_expr

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

    _now = sql_julian_timestamp_now_expr(self)
    self._execute(
        f"""
            INSERT OR REPLACE INTO comprehensive_analysis_results
            (file_id, project_id, file_mtime, results_json, summary_json, updated_at)
            VALUES (?, ?, ?, ?, ?, {_now})
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

    Uses same semantics as should_analyze_file: returns True when file
    should be skipped (no re-analysis needed), False when analysis needed.

    Args:
        file_id: File ID
        file_mtime: Current file modification time
        tolerance: Time tolerance in seconds (default: 0.1)

    Returns:
        True if analysis is up-to-date (skip), False otherwise (analyze).
    """
    gate = should_analyze_file(self, file_id, file_mtime, tolerance)
    return not gate["should_analyze"]


def should_analyze_file(
    self,
    file_id: int,
    file_mtime: float,
    tolerance: float = 0.1,
) -> Dict[str, Any]:
    """
    Determine whether to run comprehensive analysis for a file (mtime gate).

    Rule: analyze only if file on disk is newer than latest DB analysis
    (or no prior record). Older-than-DB files are skipped.

    - No previous record -> analyze.
    - disk_mtime > db_mtime + tolerance -> analyze.
    - abs(disk_mtime - db_mtime) <= tolerance -> skip (equal within tolerance).
    - disk_mtime + tolerance < db_mtime (disk older) -> skip.

    Args:
        file_id: File ID.
        file_mtime: Current file modification time (disk).
        tolerance: Time tolerance in seconds (default: 0.1).

    Returns:
        Dict with: should_analyze (bool), reason (str), db_mtime (float or None),
        disk_mtime (float). Used for logging and decision.
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
        return {
            "should_analyze": True,
            "reason": "no_record",
            "db_mtime": None,
            "disk_mtime": file_mtime,
        }

    db_mtime = float(row["file_mtime"])
    disk_mtime = float(file_mtime)

    if disk_mtime > db_mtime + tolerance:
        return {
            "should_analyze": True,
            "reason": "disk_newer",
            "db_mtime": db_mtime,
            "disk_mtime": disk_mtime,
        }
    if abs(disk_mtime - db_mtime) <= tolerance:
        return {
            "should_analyze": False,
            "reason": "equal_within_tolerance",
            "db_mtime": db_mtime,
            "disk_mtime": disk_mtime,
        }
    # disk_mtime + tolerance < db_mtime => disk older
    return {
        "should_analyze": False,
        "reason": "disk_older",
        "db_mtime": db_mtime,
        "disk_mtime": disk_mtime,
    }


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


def get_project_analysis_summary(self, project_id: str) -> Dict[str, Any]:
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
