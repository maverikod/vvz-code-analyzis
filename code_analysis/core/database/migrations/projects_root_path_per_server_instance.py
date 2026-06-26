"""
Scope ``projects`` root_path uniqueness to ``server_instance_id``.

Allows the same ``(watch_dir_id, root_path)`` on different code-analysis-server
instances sharing one PostgreSQL database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MIGRATION_KEY = "projects_root_path_per_server_instance_v1"

_OLD_INDEX_NAMES = (
    "ux_projects_watch_dir_id_root_path",
    "idx_projects_root_path_unique",
)

_OLD_CONSTRAINT_NAMES = (
    "projects_root_path_key",
    "projects_root_path_unique",
    "projects_watch_dir_id_root_path_uniq",
)

_NEW_INDEX_NAME = "ux_projects_server_instance_watch_dir_root_path"
_NEW_CONSTRAINT_NAME = "projects_server_instance_watch_dir_root_path_uniq"


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


def _drop_legacy_uniqueness(database: Any) -> None:
    """Return drop legacy uniqueness."""
    driver = getattr(database, "_driver_type", None)
    if driver == "postgres":
        for cname in _OLD_CONSTRAINT_NAMES:
            try:
                database._execute(
                    f'ALTER TABLE projects DROP CONSTRAINT IF EXISTS "{cname}"'
                )
                database._commit()
            except Exception as ex:
                logger.debug("DROP CONSTRAINT %s: %s", cname, ex)
        for iname in _OLD_INDEX_NAMES:
            try:
                database._execute(f'DROP INDEX IF EXISTS "{iname}"')
                database._commit()
            except Exception as ex:
                logger.debug("DROP INDEX %s: %s", iname, ex)
    else:
        for iname in _OLD_INDEX_NAMES:
            try:
                database._execute(f"DROP INDEX IF EXISTS {iname}")
                database._commit()
            except Exception as ex:
                logger.debug("DROP INDEX %s: %s", iname, ex)


def _add_server_scoped_uniqueness(database: Any) -> None:
    """Return add server scoped uniqueness."""
    driver = getattr(database, "_driver_type", None)
    if driver == "postgres":
        try:
            database._execute(
                f"ALTER TABLE projects ADD CONSTRAINT {_NEW_CONSTRAINT_NAME} "
                "UNIQUE (server_instance_id, watch_dir_id, root_path)"
            )
            database._commit()
        except Exception as ex:
            logger.debug(
                "ADD CONSTRAINT %s (may exist): %s",
                _NEW_CONSTRAINT_NAME,
                ex,
            )
    else:
        try:
            database._execute(f"""
                CREATE UNIQUE INDEX IF NOT EXISTS {_NEW_INDEX_NAME}
                ON projects(server_instance_id, watch_dir_id, root_path)
                """)
            database._commit()
        except Exception as ex:
            logger.debug("CREATE UNIQUE INDEX %s: %s", _NEW_INDEX_NAME, ex)


def migrate_projects_root_path_per_server_instance(database: Any) -> None:
    """Idempotent: replace global / watch-only root_path uniqueness."""
    if _db_settings_has(database, _MIGRATION_KEY):
        return

    logger.info(
        "Migration: projects UNIQUE(server_instance_id, watch_dir_id, root_path)"
    )
    _drop_legacy_uniqueness(database)
    _add_server_scoped_uniqueness(database)
    _db_settings_set(database, _MIGRATION_KEY, "1")
    logger.info("Migration completed: %s", _MIGRATION_KEY)
