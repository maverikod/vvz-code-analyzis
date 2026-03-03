"""
Comprehensive analysis API for database client.

All access goes through the driver: no direct DB connection.
- Reads: self.execute(SELECT, params) -> RPC "execute" -> driver.
- Single save: self.execute(INSERT, params) -> RPC "execute" -> driver.
- Batch save: self.begin_transaction(); self.execute_batch(ops, tid);
  self.commit_transaction(tid) -> RPC "execute_batch" -> driver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from .client_base import _DatabaseClientBase

logger = logging.getLogger(__name__)

# Type for one batch item: (file_id, project_id, file_mtime, results, summary)
_ComprehensiveAnalysisItem = Tuple[int, str, float, Dict[str, Any], Dict[str, Any]]

_INSERT_SQL = """
INSERT OR REPLACE INTO comprehensive_analysis_results
(file_id, project_id, file_mtime, results_json, summary_json, updated_at)
VALUES (?, ?, ?, ?, ?, julianday('now'))
"""


class _ClientAPIComprehensiveAnalysisMixin(_DatabaseClientBase):
    """Mixin with comprehensive analysis methods for DatabaseClient."""

    def should_analyze_file(
        self,
        file_id: int,
        file_mtime: float,
        tolerance: float = 0.1,
    ) -> Dict[str, Any]:
        """Determine whether to run comprehensive analysis for a file (mtime gate).

        Rule: analyze only if file on disk is newer than latest DB analysis
        (or no prior record). Older-than-DB files are skipped.

        - No previous record -> analyze.
        - disk_mtime > db_mtime + tolerance -> analyze.
        - abs(disk_mtime - db_mtime) <= tolerance -> skip.
        - disk_mtime + tolerance < db_mtime (disk older) -> skip.

        Args:
            file_id: File ID.
            file_mtime: Current file modification time (disk).
            tolerance: Time tolerance in seconds (default: 0.1).

        Returns:
            Dict with: should_analyze (bool), reason (str), db_mtime (float or None),
            disk_mtime (float). Used for logging and decision.
        """
        result = self.execute(
            """
            SELECT file_mtime
            FROM comprehensive_analysis_results
            WHERE file_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (file_id,),
        )
        data = result.get("data", []) if isinstance(result, dict) else []
        if not data:
            return {
                "should_analyze": True,
                "reason": "no_record",
                "db_mtime": None,
                "disk_mtime": float(file_mtime),
            }
        row = data[0] if isinstance(data, list) else None
        if not row or "file_mtime" not in row:
            return {
                "should_analyze": True,
                "reason": "no_record",
                "db_mtime": None,
                "disk_mtime": float(file_mtime),
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
        return {
            "should_analyze": False,
            "reason": "disk_older",
            "db_mtime": db_mtime,
            "disk_mtime": disk_mtime,
        }

    def is_analysis_up_to_date(
        self,
        file_id: int,
        file_mtime: float,
        tolerance: float = 0.1,
    ) -> bool:
        """Check if comprehensive analysis results are up-to-date for a file.

        Uses same semantics as should_analyze_file: True = skip, False = analyze.

        Args:
            file_id: File ID.
            file_mtime: Current file modification time.
            tolerance: Time tolerance in seconds (default: 0.1).

        Returns:
            True if analysis is up-to-date (skip), False otherwise (analyze).
        """
        gate = self.should_analyze_file(file_id, file_mtime, tolerance)
        return not gate["should_analyze"]

    def get_comprehensive_analysis_results(
        self,
        file_id: int,
        file_mtime: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get comprehensive analysis results for a file.

        Args:
            file_id: File ID.
            file_mtime: Optional file modification time to check if up-to-date.

        Returns:
            Dict with 'results', 'summary', 'file_mtime', 'analysis_date' or None.
        """
        if file_mtime is not None:
            sql = """
                SELECT results_json, summary_json, file_mtime, updated_at
                FROM comprehensive_analysis_results
                WHERE file_id = ? AND file_mtime = ?
                ORDER BY updated_at DESC
                LIMIT 1
            """
            params: Tuple[Union[int, float], ...] = (file_id, file_mtime)
        else:
            sql = """
                SELECT results_json, summary_json, file_mtime, updated_at
                FROM comprehensive_analysis_results
                WHERE file_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
            """
            params = (file_id,)

        result = self.execute(sql, params)
        data = result.get("data", []) if isinstance(result, dict) else []
        if not data:
            return None
        row = data[0] if isinstance(data, list) else None
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
            logger.error(
                "Error parsing analysis results for file_id %s: %s",
                file_id,
                e,
            )
            return None

    def save_comprehensive_analysis_results(
        self,
        file_id: int,
        project_id: str,
        file_mtime: float,
        results: Dict[str, Any],
        summary: Dict[str, Any],
    ) -> int:
        """Save comprehensive analysis results for a single file.

        Args:
            file_id: File ID.
            project_id: Project ID (UUID).
            file_mtime: File modification time at analysis.
            results: Analysis results dict.
            summary: Summary statistics dict.

        Returns:
            Analysis result row id (lastrowid).
        """
        results_json = json.dumps(results, ensure_ascii=False)
        summary_json = json.dumps(summary, ensure_ascii=False)
        result = self.execute(
            _INSERT_SQL,
            (file_id, project_id, file_mtime, results_json, summary_json),
        )
        if isinstance(result, dict):
            lastrowid = result.get("lastrowid")
            return int(lastrowid) if lastrowid is not None else 0
        return 0

    def save_comprehensive_analysis_results_batch(
        self,
        items: List[_ComprehensiveAnalysisItem],
    ) -> None:
        """Save comprehensive analysis results for multiple files in one batch.

        Uses execute_batch within a single transaction for efficiency.

        Args:
            items: List of (file_id, project_id, file_mtime, results, summary).
        """
        if not items:
            return
        operations: List[Tuple[str, Optional[tuple]]] = []
        for file_id, project_id, file_mtime, results, summary in items:
            results_json = json.dumps(results, ensure_ascii=False)
            summary_json = json.dumps(summary, ensure_ascii=False)
            operations.append(
                (
                    _INSERT_SQL,
                    (file_id, project_id, file_mtime, results_json, summary_json),
                )
            )
        try:
            tid = self.begin_transaction()
            self.execute_batch(operations, transaction_id=tid)
            self.commit_transaction(tid)
        except Exception as e:
            logger.warning(
                "save_comprehensive_analysis_results_batch failed (n=%s): %s",
                len(items),
                e,
            )
            raise
