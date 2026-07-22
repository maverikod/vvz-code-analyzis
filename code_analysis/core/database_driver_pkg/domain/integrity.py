"""
Project integrity checks, ported driver-direct (stage 2 layer collapse, Part 1).

Free-function port of ``code_analysis.core.database_client.client_api_integrity``'s
``_ClientAPIIntegrityMixin`` methods. Each function takes ``driver: Any``
(duck-typed against ``execute``/``execute_batch``/``begin_transaction``/
``commit_transaction``/``rollback_transaction`` - see
scratchpad/stage2-parity-spike.md) instead of ``self``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, List, Sequence

from code_analysis.core.integrity_analysis.import_cycles_sql import (
    DEFAULT_MAX_CHAIN_DEPTH,
    build_import_cycle_detection_batch,
    parse_import_cycle_rows,
)

logger = logging.getLogger(__name__)


def fetch_import_cycle_paths(
    driver: Any,
    project_id: str,
    *,
    max_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
) -> List[List[str]]:
    """
    Run the three-step import-cycle SQL batch on the configured backend.

    Exact port of ``_ClientAPIIntegrityMixin.fetch_import_cycle_paths``. All
    statements execute in one transaction (``execute_batch``) so TEMP tables
    remain visible for the final SELECT.
    """
    batch = build_import_cycle_detection_batch(project_id, max_depth=max_depth)
    operations = [(sql, params) for sql, params in batch]
    tid = driver.begin_transaction()
    try:
        results = driver.execute_batch(operations, transaction_id=tid)
        driver.commit_transaction(tid)
    except Exception:
        driver.rollback_transaction(tid)
        raise

    if not results:
        return []
    last = results[-1]
    rows = last.get("data") if isinstance(last, dict) else None
    return parse_import_cycle_rows(rows or [], max_depth=max_depth)


def clear_project_integrity_issues(
    driver: Any,
    project_id: str,
    issue_types: Sequence[str],
) -> int:
    """Delete ``issues`` rows for ``project_id`` and given ``issue_types``.

    Exact port of ``_ClientAPIIntegrityMixin.clear_project_integrity_issues``.
    """
    if not issue_types:
        return 0
    placeholders = ",".join("?" for _ in issue_types)
    result = driver.execute(
        f"""
        DELETE FROM issues
        WHERE project_id = ? AND issue_type IN ({placeholders})
        """,
        (project_id, *issue_types),
    )
    affected = result.get("affected_rows", 0) if isinstance(result, dict) else 0
    try:
        return int(affected) if affected is not None else 0
    except (TypeError, ValueError):
        return 0
