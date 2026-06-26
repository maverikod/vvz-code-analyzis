"""
PostgreSQL: ``projects.root_path`` as watch-relative folder segment.

Drops legacy UNIQUE on ``root_path`` when named ``projects_root_path_key``,
adds ``UNIQUE (watch_dir_id, root_path)``, and rewrites absolute ``root_path``
values to a single folder segment when the project is an immediate child of
``watch_dir_paths.absolute_path``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from code_analysis.core.project_root_path import (
    fetch_watch_dir_absolute_path,
    is_legacy_projects_root_path_absolute_storage,
    persist_projects_root_path_stored_value,
)

logger = logging.getLogger(__name__)

_MIGRATION_KEY = "projects_root_segment_postgres_v1"


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


def migrate_projects_root_segment_postgres(database: Any) -> None:
    """Idempotent migration for PostgreSQL driver only."""
    if getattr(database, "_driver_type", None) != "postgres":
        return
    if _db_settings_has(database, _MIGRATION_KEY):
        return

    logger.info("PostgreSQL migration: projects.root_path watch-relative segment model")

    for cname in ("projects_root_path_key", "projects_root_path_unique"):
        try:
            database._execute(
                f'ALTER TABLE projects DROP CONSTRAINT IF EXISTS "{cname}"'
            )
            database._commit()
        except Exception as ex:
            logger.debug("DROP CONSTRAINT %s: %s", cname, ex)

    # Replaced by migrate_projects_root_path_per_server_instance (server-scoped).
    try:
        database._execute(
            "ALTER TABLE projects ADD CONSTRAINT projects_watch_dir_id_root_path_uniq "
            "UNIQUE (watch_dir_id, root_path)"
        )
        database._commit()
    except Exception as e:
        logger.debug(
            "ADD CONSTRAINT projects_watch_dir_id_root_path_uniq (may exist): %s",
            e,
        )
    try:
        from code_analysis.core.database.migrations.projects_root_path_per_server_instance import (
            migrate_projects_root_path_per_server_instance,
        )

        migrate_projects_root_path_per_server_instance(database)
    except Exception as e:
        logger.debug(
            "projects_root_path_per_server_instance after segment migration: %s",
            e,
        )

    try:
        prows = database._fetchall(
            "SELECT id, root_path, watch_dir_id FROM projects WHERE watch_dir_id IS NOT NULL"
        )
    except Exception as e:
        logger.warning("Could not load projects for root_path migration: %s", e)
        prows = []

    for pr in prows or []:
        if not isinstance(pr, dict):
            continue
        pid = pr.get("id")
        stored = str(pr.get("root_path") or "").strip()
        wid = str(pr.get("watch_dir_id") or "").strip()
        if not pid or not stored or not wid:
            continue
        if not is_legacy_projects_root_path_absolute_storage(stored):
            continue
        if not fetch_watch_dir_absolute_path(database, wid):
            continue
        try:
            abs_root = Path(stored).expanduser().resolve()
        except OSError:
            continue
        new_stored = persist_projects_root_path_stored_value(
            project_root_absolute=abs_root,
            watch_dir_id=wid,
            database=database,
        )
        if new_stored == stored:
            continue
        if is_legacy_projects_root_path_absolute_storage(new_stored):
            continue
        try:
            database._execute(
                "UPDATE projects SET root_path = ? WHERE id = ?",
                (new_stored, pid),
            )
            database._commit()
        except Exception as ex:
            logger.warning(
                "Could not migrate projects.root_path id=%s to segment %r: %s",
                pid,
                new_stored,
                ex,
            )

    _db_settings_set(database, _MIGRATION_KEY, "1")
    logger.info("PostgreSQL migration completed: %s", _MIGRATION_KEY)
