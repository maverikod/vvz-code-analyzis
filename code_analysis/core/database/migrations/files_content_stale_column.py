"""
Add ``content_stale`` / ``content_stale_since`` columns to ``files`` (bug 56c23bd9).

Driver-agnostic additive migration, precedent-matched to
``migrate_watch_dirs_deleted_column`` (same module shape, same idempotency
guard via ``db_settings``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MIGRATION_KEY = "files_content_stale_column_v1"


def _db_settings_has(database: Any, key: str) -> bool:
    """Return db settings has."""
    try:
        row = database._fetchone(
            "SELECT 1 FROM db_settings WHERE key = ? LIMIT 1", (key,)
        )
        return bool(row)
    except Exception:
        return False


def _db_settings_set(database: Any, key: str, value: str) -> None:
    """Return db settings set."""
    database._execute(
        "INSERT INTO db_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    database._commit()


def _column_exists(database: Any, table: str, column: str) -> bool:
    """Return column exists."""
    info = database._get_table_info(table)
    return any(col.get("name") == column for col in info)


def migrate_files_content_stale_column(database: Any) -> None:
    """Idempotent: add ``files.content_stale`` (BOOLEAN, default false) and
    ``files.content_stale_since`` (REAL, nullable)."""
    have_both = _column_exists(
        database, "files", "content_stale"
    ) and _column_exists(database, "files", "content_stale_since")
    if _db_settings_has(database, _MIGRATION_KEY) and have_both:
        return
    is_postgres = getattr(database, "_driver_type", None) == "postgres"
    if not _column_exists(database, "files", "content_stale"):
        try:
            logger.info("Migrating files table: adding content_stale column")
            default = "FALSE" if is_postgres else "0"
            database._execute(
                f"ALTER TABLE files ADD COLUMN content_stale BOOLEAN NOT NULL DEFAULT {default}"
            )
            database._commit()
        except Exception as exc:
            logger.warning("Could not add files.content_stale column: %s", exc)
            return
    if not _column_exists(database, "files", "content_stale_since"):
        try:
            logger.info("Migrating files table: adding content_stale_since column")
            database._execute(
                "ALTER TABLE files ADD COLUMN content_stale_since REAL DEFAULT NULL"
            )
            database._commit()
        except Exception as exc:
            logger.warning(
                "Could not add files.content_stale_since column: %s", exc
            )
            return
    _db_settings_set(database, _MIGRATION_KEY, "1")
