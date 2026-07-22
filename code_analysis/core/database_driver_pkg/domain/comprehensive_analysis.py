"""
Comprehensive-analysis results, ported driver-direct (stage 2 layer collapse, Part 1).

Free-function port of ``code_analysis.core.database_client.client_api_comprehensive_analysis``'s
``_ClientAPIComprehensiveAnalysisMixin`` methods. Each function takes ``driver: Any``
(duck-typed against ``execute``/``execute_batch``/``begin_transaction``/
``commit_transaction``/``rollback_transaction`` - see
scratchpad/stage2-parity-spike.md) instead of ``self``.

Exact-shape note (``should_analyze_file``): returns a decision dict
``{should_analyze, reason, db_mtime, disk_mtime}``, not a bool - preserved as-is,
all 4 keys, all 4 ``reason`` branches (``no_record``/``disk_newer``/
``equal_within_tolerance``/``disk_older``).

Note (``save_comprehensive_analysis_results_batch``): calls ``driver.begin_transaction()``
without an ``if not tid`` guard (unlike the 4 sites hardened in the prior stage-2
sub-step, see core/file_handlers/text_handler.py etc.) - on the client path today, a
malformed-response ``""`` sentinel would silently be treated as a self-managed
transaction id by ``execute_batch``/``commit_transaction`` (masking the failure); on
the driver path, ``begin_transaction()`` raises ``TransactionError`` immediately
instead, which propagates out of this function unchanged (this function has no
``except`` around ``begin_transaction()`` itself). This is a stricter, fail-loud
behavior change, not a shape violation of this function's documented contract (which
never promised to swallow a failed begin) - flagged per Block B escalation rules,
not treated as a blocking defect.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from code_analysis.core.sql_portable import sql_julian_timestamp_now_expr

logger = logging.getLogger(__name__)

# Type for one batch item: (file_id, project_id, file_mtime, results, summary)
_ComprehensiveAnalysisItem = Tuple[int, str, float, Dict[str, Any], Dict[str, Any]]


def should_analyze_file(
    driver: Any,
    file_id: int,
    file_mtime: float,
    tolerance: float = 0.1,
) -> Dict[str, Any]:
    """Determine whether to run comprehensive analysis for a file (mtime gate).

    Exact port of ``_ClientAPIComprehensiveAnalysisMixin.should_analyze_file``.
    """
    result = driver.execute(
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


def get_comprehensive_analysis_results(
    driver: Any,
    file_id: int,
    file_mtime: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Get comprehensive analysis results for a file.

    Exact port of ``_ClientAPIComprehensiveAnalysisMixin.get_comprehensive_analysis_results``.
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

    result = driver.execute(sql, params)
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
    driver: Any,
    file_id: int,
    project_id: str,
    file_mtime: float,
    results: Dict[str, Any],
    summary: Dict[str, Any],
) -> int:
    """Save comprehensive analysis results for a single file.

    Exact port of ``_ClientAPIComprehensiveAnalysisMixin.save_comprehensive_analysis_results``.
    """
    results_json = json.dumps(results, ensure_ascii=False)
    summary_json = json.dumps(summary, ensure_ascii=False)
    _now = sql_julian_timestamp_now_expr(driver)
    insert_sql = f"""
INSERT OR REPLACE INTO comprehensive_analysis_results
(file_id, project_id, file_mtime, results_json, summary_json, updated_at)
VALUES (?, ?, ?, ?, ?, {_now})
"""
    result = driver.execute(
        insert_sql,
        (file_id, project_id, file_mtime, results_json, summary_json),
    )
    if isinstance(result, dict):
        lastrowid = result.get("lastrowid")
        return int(lastrowid) if lastrowid is not None else 0
    return 0


def save_comprehensive_analysis_results_batch(
    driver: Any,
    items: List[_ComprehensiveAnalysisItem],
) -> None:
    """Save comprehensive analysis results for multiple files in one batch.

    Exact port of
    ``_ClientAPIComprehensiveAnalysisMixin.save_comprehensive_analysis_results_batch``.
    """
    if not items:
        return
    _now = sql_julian_timestamp_now_expr(driver)
    insert_sql = f"""
INSERT OR REPLACE INTO comprehensive_analysis_results
(file_id, project_id, file_mtime, results_json, summary_json, updated_at)
VALUES (?, ?, ?, ?, ?, {_now})
"""
    operations: List[Tuple[str, Optional[tuple]]] = []
    for file_id, project_id, file_mtime, results, summary in items:
        results_json = json.dumps(results, ensure_ascii=False)
        summary_json = json.dumps(summary, ensure_ascii=False)
        operations.append(
            (
                insert_sql,
                (file_id, project_id, file_mtime, results_json, summary_json),
            )
        )
    tid = driver.begin_transaction()
    committed = False
    try:
        driver.execute_batch(operations, transaction_id=tid)
        driver.commit_transaction(tid)
        committed = True
    except Exception as e:
        logger.warning(
            "save_comprehensive_analysis_results_batch failed (n=%s): %s",
            len(items),
            e,
        )
        raise
    finally:
        if not committed:
            try:
                driver.rollback_transaction(tid)
            except Exception as rb:
                logger.warning(
                    "save_comprehensive_analysis_results_batch rollback "
                    "failed (n=%s): %s",
                    len(items),
                    rb,
                )
