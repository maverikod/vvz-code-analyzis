"""
Project integrity DB access via DatabaseClient (command → client → RPC → driver → SUBD).

Circular-import detection runs as one ``execute_batch`` inside a transaction so
session-scoped TEMP tables stay on the same connection.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Sequence

from code_analysis.core.integrity_analysis.import_cycles_sql import (
    DEFAULT_MAX_CHAIN_DEPTH,
    build_import_cycle_detection_batch,
    parse_import_cycle_rows,
)

from .client_base import _DatabaseClientBase

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class _ClientAPIIntegrityMixin(_DatabaseClientBase):
    """Mixin: integrity checks that require transactional SQL on the driver."""

    def fetch_import_cycle_paths(
        self,
        project_id: str,
        *,
        max_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
    ) -> List[List[str]]:
        """
        Run the three-step import-cycle SQL batch on the configured backend.

        All statements execute in one transaction (``execute_batch``) so TEMP
        tables remain visible for the final SELECT.
        """
        batch = build_import_cycle_detection_batch(project_id, max_depth=max_depth)
        operations = [(sql, params) for sql, params in batch]
        tid = self.begin_transaction()
        try:
            results = self.execute_batch(operations, transaction_id=tid)
            self.commit_transaction(tid)
        except Exception:
            self.rollback_transaction(tid)
            raise

        if not results:
            return []
        last = results[-1]
        rows = last.get("data") if isinstance(last, dict) else None
        return parse_import_cycle_rows(rows or [], max_depth=max_depth)

    def clear_project_integrity_issues(
        self,
        project_id: str,
        issue_types: Sequence[str],
    ) -> int:
        """Delete ``issues`` rows for ``project_id`` and given ``issue_types``."""
        if not issue_types:
            return 0
        placeholders = ",".join("?" for _ in issue_types)
        result = self.execute(
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
