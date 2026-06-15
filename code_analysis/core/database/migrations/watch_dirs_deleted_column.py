"""
Add ``deleted`` column to ``watch_dirs``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MIGRATION_KEY = "watch_dirs_deleted_column_v1"


def _db_settings_has(database: Any, key: str) -> bool:
    try:
        row = database._fetchone(
            "SELECT 1 FROM db_settings WHERE key = ? LIMIT 1", (key,)
        )
        return bool(row)
    except Exception:
        return False


def _db_settings_set(database: Any, key: str, value: str) -> None:
    database._execute(
        "INSERT INTO db_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    database._commit()


def _column_exists(database: Any, table: str, column: str) -> bool:
    info = database._get_table_info(table)
    return any(col.get("name") == column for col in info)


def migrate_watch_dirs_deleted_column(database: Any) -> None:
    """Idempotent: add ``watch_dirs.deleted`` (BOOLEAN, default 0)."""
    if _db_settings_has(database, _MIGRATION_KEY) and _column_exists(
        database, "watch_dirs", "deleted"
    ):
        return
    if not _column_exists(database, "watch_dirs", "deleted"):
        try:
            logger.info("Migrating watch_dirs: adding deleted column")
            default = (
                "FALSE"
                if getattr(database, "_driver_type", None) == "postgres"
                else "0"
            )
            database._execute(
                f"ALTER TABLE watch_dirs ADD COLUMN deleted BOOLEAN DEFAULT {default}"
            )
            database._commit()
        except Exception as exc:
            logger.warning("Could not add watch_dirs.deleted column: %s", exc)
            return
    _db_settings_set(database, _MIGRATION_KEY, "1")
