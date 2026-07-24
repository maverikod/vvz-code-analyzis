"""
Create the ``project_exclusive_locks`` table (whole-project admin lock, no TTL).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def migrate_project_exclusive_locks_table(database: Any) -> None:
    """Idempotent: create the ``project_exclusive_locks`` table if missing.

    No TTL/lease columns by design — this is a whole-project admin lock held
    until explicitly released by rename_project/emergency_unlock_project, not
    a short-lease coordination table (contrast with ``project_activity_locks``
    in core/worker_project_activity.py).

    Args:
        database: Driver/migration-adapter object exposing ``_execute(sql,
            params)`` and ``_commit()`` (the migration-adapter surface used by
            every module in ``core/database/migrations/``, e.g.
            ``watch_dirs_deleted_column.py``).

    Returns:
        None. Failures are caught and logged, never raised, matching the
        existing migration modules' error-swallowing convention.
    """
    try:
        database._execute(
            "CREATE TABLE IF NOT EXISTS project_exclusive_locks ("
            "project_id TEXT PRIMARY KEY, "
            "locked_at REAL NOT NULL, "
            "owner TEXT NOT NULL, "
            "reason TEXT"
            ")"
        )
        database._commit()
    except Exception as exc:
        logger.warning("Could not create project_exclusive_locks table: %s", exc)
