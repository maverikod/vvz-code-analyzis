"""
Add ``server_instance_id`` partition to watch_dirs, watch_dir_paths, and projects.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, List

logger = logging.getLogger(__name__)

_MIGRATION_KEY = "watch_dirs_server_instance_v1"


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


def _partition_columns_present(database: Any) -> bool:
    return (
        _column_exists(database, "watch_dirs", "server_instance_id")
        and _column_exists(database, "watch_dir_paths", "server_instance_id")
        and _column_exists(database, "projects", "server_instance_id")
    )


def _postgres_primary_key_columns(database: Any, table: str) -> List[str]:
    if getattr(database, "_driver_type", None) != "postgres":
        return []
    rows = database._fetchall(
        """
        SELECT a.attname
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        JOIN pg_namespace n ON t.relnamespace = n.oid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
        WHERE c.contype = 'p'
          AND t.relname = ?
          AND n.nspname = current_schema()
        ORDER BY array_position(c.conkey, a.attnum)
        """,
        (table,),
    )
    return [str(row["attname"]) for row in rows if row.get("attname") is not None]


def _watch_dirs_composite_pk_present(database: Any) -> bool:
    return _postgres_primary_key_columns(database, "watch_dirs") == [
        "server_instance_id",
        "id",
    ]


def migrate_watch_dirs_server_instance(database: Any) -> None:
    """Idempotent schema migration (PostgreSQL and SQLite)."""
    if _db_settings_has(database, _MIGRATION_KEY) and _partition_columns_present(
        database
    ):
        return
    if _watch_dirs_composite_pk_present(database) and _partition_columns_present(
        database
    ):
        _db_settings_set(database, _MIGRATION_KEY, "1")
        return
    if _db_settings_has(database, _MIGRATION_KEY):
        logger.warning(
            "Migration %s marked done but partition columns missing; re-running",
            _MIGRATION_KEY,
        )

    logger.info("Migration: watch_dirs.server_instance_id partition column")

    if not _column_exists(database, "watch_dirs", "server_instance_id"):
        database._execute("ALTER TABLE watch_dirs ADD COLUMN server_instance_id TEXT")
        database._commit()

    if not _column_exists(database, "watch_dir_paths", "server_instance_id"):
        database._execute(
            "ALTER TABLE watch_dir_paths ADD COLUMN server_instance_id TEXT"
        )
        database._commit()

    if not _column_exists(database, "projects", "server_instance_id"):
        database._execute("ALTER TABLE projects ADD COLUMN server_instance_id TEXT")
        database._commit()

    driver = getattr(database, "_driver_type", None)
    if driver == "postgres":
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_watch_dirs_server_instance_id "
            "ON watch_dirs(server_instance_id)",
            "CREATE INDEX IF NOT EXISTS idx_projects_server_instance_id "
            "ON projects(server_instance_id)",
        ):
            try:
                database._execute(stmt)
                database._commit()
            except Exception as ex:
                logger.debug("Index create skipped: %s", ex)
    else:
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_watch_dirs_server_instance_id "
            "ON watch_dirs(server_instance_id)",
            "CREATE INDEX IF NOT EXISTS idx_projects_server_instance_id "
            "ON projects(server_instance_id)",
        ):
            try:
                database._execute(stmt)
                database._commit()
            except Exception as ex:
                logger.debug("Index create skipped: %s", ex)

    _migrate_watch_dirs_composite_keys(database)

    _db_settings_set(database, _MIGRATION_KEY, "1")
    logger.info("Migration watch_dirs_server_instance_v1 completed")


def _backfill_null_server_instance_ids(database: Any) -> None:
    """Populate NULL ``server_instance_id`` from projects before composite PK."""
    driver = getattr(database, "_driver_type", None)
    try:
        if driver == "postgres":
            database._execute("""
                UPDATE watch_dirs wd
                SET server_instance_id = sub.sid
                FROM (
                    SELECT DISTINCT watch_dir_id AS wid, server_instance_id AS sid
                    FROM projects
                    WHERE server_instance_id IS NOT NULL
                      AND watch_dir_id IS NOT NULL
                ) sub
                WHERE wd.id = sub.wid
                  AND wd.server_instance_id IS NULL
                """)
            database._execute("""
                UPDATE watch_dir_paths wdp
                SET server_instance_id = wd.server_instance_id
                FROM watch_dirs wd
                WHERE wdp.watch_dir_id = wd.id
                  AND wdp.server_instance_id IS NULL
                  AND wd.server_instance_id IS NOT NULL
                """)
            database._execute("""
                UPDATE projects p
                SET server_instance_id = wd.server_instance_id
                FROM watch_dirs wd
                WHERE p.watch_dir_id = wd.id
                  AND p.server_instance_id IS NULL
                  AND wd.server_instance_id IS NOT NULL
                """)
        else:
            database._execute("""
                UPDATE watch_dirs
                SET server_instance_id = (
                    SELECT p.server_instance_id FROM projects p
                    WHERE p.watch_dir_id = watch_dirs.id
                      AND p.server_instance_id IS NOT NULL
                    LIMIT 1
                )
                WHERE server_instance_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM projects p
                    WHERE p.watch_dir_id = watch_dirs.id
                      AND p.server_instance_id IS NOT NULL
                  )
                """)
        database._commit()
    except Exception as ex:
        logger.warning("server_instance_id backfill skipped: %s", ex)
        try:
            database._conn.rollback()
        except Exception:
            pass


def _migrate_watch_dirs_composite_keys(database: Any) -> None:
    """Allow the same config watch_dir ``id`` on different server instances."""
    if _watch_dirs_composite_pk_present(database):
        return
    if not _column_exists(database, "watch_dirs", "server_instance_id"):
        return

    _backfill_null_server_instance_ids(database)

    null_row = database._fetchone(
        "SELECT 1 FROM watch_dirs WHERE server_instance_id IS NULL LIMIT 1"
    )
    if null_row:
        logger.warning(
            "Skipping watch_dirs composite PK: rows with NULL server_instance_id "
            "remain (will backfill on watcher init)"
        )
        return

    dup = database._fetchall(
        "SELECT id FROM watch_dirs GROUP BY id HAVING COUNT(*) > 1"
    )
    if dup:
        logger.warning(
            "Skipping watch_dirs composite PK: duplicate id rows exist (%s)",
            len(dup),
        )
        return

    driver = getattr(database, "_driver_type", None)
    try:
        if driver == "postgres":
            database._execute(
                "ALTER TABLE watch_dirs DROP CONSTRAINT IF EXISTS watch_dirs_pkey"
            )
            database._commit()
            try:
                database._execute(
                    "ALTER TABLE watch_dirs ADD PRIMARY KEY (server_instance_id, id)"
                )
                database._commit()
            except Exception as inner:
                try:
                    database._conn.rollback()
                except Exception:
                    pass
                logger.warning(
                    "watch_dirs composite PK failed (%s); restoring PRIMARY KEY (id)",
                    inner,
                )
                database._execute("ALTER TABLE watch_dirs ADD PRIMARY KEY (id)")
                database._commit()
                return
        else:
            database._execute(
                "CREATE TABLE IF NOT EXISTS watch_dirs_new ("
                "server_instance_id TEXT NOT NULL, "
                "id TEXT NOT NULL, "
                "name TEXT, "
                "created_at REAL, "
                "updated_at REAL, "
                "PRIMARY KEY (server_instance_id, id)"
                ")"
            )
            database._execute(
                "INSERT INTO watch_dirs_new "
                "SELECT server_instance_id, id, name, created_at, updated_at "
                "FROM watch_dirs WHERE server_instance_id IS NOT NULL"
            )
            database._execute("DROP TABLE watch_dirs")
            database._execute("ALTER TABLE watch_dirs_new RENAME TO watch_dirs")
            database._commit()
    except Exception as ex:
        logger.warning("watch_dirs composite PK migration skipped: %s", ex)
        return

    if not _column_exists(database, "watch_dir_paths", "server_instance_id"):
        return

    null_path = database._fetchone(
        "SELECT 1 FROM watch_dir_paths WHERE server_instance_id IS NULL LIMIT 1"
    )
    if null_path:
        logger.warning(
            "Skipping watch_dir_paths composite PK: NULL server_instance_id rows remain"
        )
        return

    try:
        if driver == "postgres":
            database._execute(
                "ALTER TABLE watch_dir_paths "
                "DROP CONSTRAINT IF EXISTS watch_dir_paths_pkey"
            )
            database._commit()
            database._execute(
                "ALTER TABLE watch_dir_paths "
                "ADD PRIMARY KEY (server_instance_id, watch_dir_id)"
            )
            database._commit()
    except Exception as ex:
        logger.warning("watch_dir_paths composite PK skipped: %s", ex)
