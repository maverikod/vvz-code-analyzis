"""
Portable SQL predicates for PostgreSQL.

Boolean columns (``files.deleted``, ``files.has_docstring``, ``projects.deleted``)
are native BOOLEAN in PostgreSQL. Comparisons such as ``deleted = 0`` or
``has_docstring = 1`` fail on PostgreSQL (``operator does not exist: boolean =
integer``). Use ``IS TRUE`` / ``IS NOT TRUE`` with ``OR ... IS NULL`` where legacy
rows may have NULL.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

# --- files.deleted / projects.deleted: "active" (not soft-deleted) ---
WHERE_FILES_ACTIVE = "(deleted IS NOT TRUE OR deleted IS NULL)"
WHERE_FILES_ACTIVE_F = "(f.deleted IS NOT TRUE OR f.deleted IS NULL)"
WHERE_FILES_ACTIVE_P = "(p.deleted IS NOT TRUE OR p.deleted IS NULL)"

# --- soft-deleted row (trash) ---
WHERE_FILES_TRASHED = "deleted IS TRUE"
WHERE_PROJECTS_TRASHED = "deleted IS TRUE"

# --- projects.deleted: not soft-deleted (active project row) ---
WHERE_PROJECTS_ACTIVE = "(deleted IS NOT TRUE OR deleted IS NULL)"
WHERE_PROJECTS_ACTIVE_P = "(p.deleted IS NOT TRUE OR p.deleted IS NULL)"

# --- files.has_docstring ---
WHERE_HAS_DOCSTRING = "has_docstring IS TRUE"
WHERE_HAS_DOCSTRING_F = "f.has_docstring IS TRUE"

# --- projects.processing_paused (BOOLEAN): "not paused" ---
WHERE_PROCESSING_ACTIVE = "(processing_paused IS NOT TRUE OR processing_paused IS NULL)"
WHERE_PROCESSING_ACTIVE_P = (
    "(p.processing_paused IS NOT TRUE OR p.processing_paused IS NULL)"
)


def unix_timestamp_to_julian_day(unix_ts: float) -> float:
    """Convert Unix epoch seconds to Julian day (same convention as ``julianday()``)."""
    return unix_ts / 86400.0 + 2440587.5


def sql_julian_timestamp_now_expr(database: Any) -> str:
    """
    SQL fragment for REAL Julian-day style timestamps (``files.updated_at``).

    PostgreSQL uses ``EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)`` to match schema
    defaults mapped in ``schema_sync_sql_postgres``.
    """
    _ = database  # kept for call-site compatibility; only PostgreSQL is supported
    return "EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)"


def sql_julian_one_day_ago_expr(database: Any) -> str:
    """
    SQL fragment for Julian-day threshold ~24 hours ago (status / analytics).

    PostgreSQL: subtract ``INTERVAL '1 day'``.
    """
    _ = database  # kept for call-site compatibility; only PostgreSQL is supported
    return "EXTRACT(JULIAN FROM (CURRENT_TIMESTAMP - INTERVAL '1 day'))"


def database_has_sqlite_code_content_fts(database: Any) -> bool:
    """
    Return True if DML may target a SQLite FTS5 ``code_content_fts`` virtual table.

    SQLite support was removed; PostgreSQL deployments never have this virtual
    table, so this is always False. Kept as a named predicate for callers that
    still gate FTS ``DELETE`` statements on it.
    """
    _ = database  # kept for call-site compatibility; only PostgreSQL is supported
    return False
