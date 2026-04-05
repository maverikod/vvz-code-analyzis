"""
SQLite driver connection-time migrations (indexing_errors, code_chunks, files, stats).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

logger = logging.getLogger(__name__)


class _SqliteConnMigrateAdapter:
    """Minimal db-like surface for schema_creation_migrate.run_migrate_schema (driver process)."""

    def __init__(self, conn: Any, schema_manager: Any) -> None:
        self._conn = conn
        self._schema_manager = schema_manager

    def _get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        return cast(
            List[Dict[str, Any]], self._schema_manager.get_table_info(table_name)
        )

    def _execute(self, sql: str, params: Any = None) -> None:
        if params is not None and params != ():
            self._conn.execute(sql, params)
        else:
            self._conn.execute(sql)

    def _fetchone(self, sql: str, params: Any = None) -> Optional[Dict[str, Any]]:
        cur = self._conn.cursor()
        try:
            if params is not None and params != ():
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            row = cur.fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            cur.close()

    def _commit(self) -> None:
        self._conn.commit()


INDEXING_WORKER_STATS_TABLE = "indexing_worker_stats"
INDEXING_WORKER_STATS_COLUMNS: List[tuple] = [
    ("cycle_id", "TEXT PRIMARY KEY"),
    ("cycle_start_time", "REAL NOT NULL"),
    ("cycle_end_time", "REAL"),
    ("files_total_at_start", "INTEGER NOT NULL DEFAULT 0"),
    ("files_indexed", "INTEGER NOT NULL DEFAULT 0"),
    ("files_failed", "INTEGER NOT NULL DEFAULT 0"),
    ("total_processing_time_seconds", "REAL NOT NULL DEFAULT 0.0"),
    ("average_processing_time_seconds", "REAL"),
    ("last_updated", "REAL DEFAULT (julianday('now'))"),
]
INDEXING_WORKER_STATS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_indexing_worker_stats_start_time "
    f"ON {INDEXING_WORKER_STATS_TABLE}(cycle_start_time)"
)


def ensure_indexing_errors_table(conn: Any) -> None:
    """Create indexing_errors table if missing."""
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='indexing_errors'"
        )
        if cur.fetchone() is not None:
            return
        logger.info("Creating indexing_errors table (driver)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS indexing_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                error_type TEXT,
                error_message TEXT,
                created_at REAL DEFAULT (julianday('now')),
                UNIQUE(project_id, file_path)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_indexing_errors_project_path "
            "ON indexing_errors(project_id, file_path)"
        )
        conn.commit()
    except Exception as e:
        logger.warning("Could not create indexing_errors table: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass


def ensure_code_chunks_migrations(conn: Any, schema_manager: Any) -> None:
    """Add code_chunks.token_count if missing."""
    if not conn or not schema_manager:
        return
    try:
        info = schema_manager.get_table_info("code_chunks")
        columns = {row["name"] for row in info}
        if "token_count" not in columns:
            logger.info(
                "Migrating code_chunks table: adding token_count column (driver)"
            )
            conn.execute("ALTER TABLE code_chunks ADD COLUMN token_count INTEGER")
            conn.commit()
    except Exception as e:
        logger.warning("Could not add token_count to code_chunks in driver: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass


def ensure_indexing_worker_stats_table(conn: Any, schema_manager: Any) -> None:
    """Create indexing_worker_stats if missing and add any missing columns."""
    if not conn or not schema_manager:
        return
    table = INDEXING_WORKER_STATS_TABLE
    try:
        info = schema_manager.get_table_info(table)
    except Exception:
        info = []
    existing = {row["name"] for row in info} if info else set()

    if not existing:
        try:
            logger.info(
                "Creating %s table in driver (required by indexing worker)",
                table,
            )
            cols = ", ".join(
                f"{name} {spec}" for name, spec in INDEXING_WORKER_STATS_COLUMNS
            )
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({cols})")
            conn.execute(INDEXING_WORKER_STATS_INDEX)
            conn.commit()
            return
        except Exception as e:
            logger.warning("Could not create %s in driver: %s", table, e)
            try:
                conn.rollback()
            except Exception:
                pass
            return

    for name, spec in INDEXING_WORKER_STATS_COLUMNS:
        if name in existing:
            continue
        if "PRIMARY KEY" in spec:
            continue
        try:
            logger.info(
                "Migrating %s: adding column %s (driver)",
                table,
                name,
            )
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")
            conn.commit()
            existing.add(name)
        except Exception as e:
            logger.warning(
                "Could not add column %s to %s in driver: %s",
                name,
                table,
                e,
            )
            try:
                conn.rollback()
            except Exception:
                pass

    try:
        conn.execute(INDEXING_WORKER_STATS_INDEX)
        conn.commit()
    except Exception as e:
        logger.debug("Index for %s may already exist: %s", table, e)
        try:
            conn.rollback()
        except Exception:
            pass


def ensure_files_table_migrations(conn: Any, schema_manager: Any) -> None:
    """Run migrations on files table (needs_chunking; drop dataset_id if present)."""
    if not conn or not schema_manager:
        return
    try:
        info = schema_manager.get_table_info("files")
        columns = {row["name"] for row in info}
        if "needs_chunking" not in columns:
            logger.info("Migrating files table: adding needs_chunking column (driver)")
            conn.execute(
                "ALTER TABLE files ADD COLUMN needs_chunking INTEGER DEFAULT 0"
            )
            conn.commit()
        if "dataset_id" in columns:
            logger.info("Migrating files table: dropping dataset_id column (driver)")
            try:
                conn.execute("ALTER TABLE files DROP COLUMN dataset_id")
                conn.commit()
            except Exception as drop_e:
                logger.warning(
                    "Could not drop dataset_id (SQLite 3.35+ required): %s",
                    drop_e,
                )
                try:
                    conn.rollback()
                except Exception:
                    pass
    except Exception as e:
        logger.warning("Could not add needs_chunking column to files in driver: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass


def run_all_ensure(conn: Any, schema_manager: Any, db_path: Path) -> None:
    """Run all connection-time migrations in order."""
    # Align with CodeDatabase / run_create_schema: apply schema_creation_migrate so
    # existing DBs gain columns (e.g. files.deleted, projects.deleted) before RPC SQL.
    from code_analysis.core.database.schema_creation_migrate import run_migrate_schema

    run_migrate_schema(_SqliteConnMigrateAdapter(conn, schema_manager))
    ensure_files_table_migrations(conn, schema_manager)
    ensure_code_chunks_migrations(conn, schema_manager)
    ensure_indexing_worker_stats_table(conn, schema_manager)
    ensure_indexing_errors_table(conn)
