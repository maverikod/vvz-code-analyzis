"""
SQLite driver connection-time migrations (indexing_errors, code_chunks, files, stats).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from code_analysis.core.client_sessions import ensure_client_session_tables
from code_analysis.core.subordinate_sessions import ensure_subordinate_session_tables

logger = logging.getLogger(__name__)


def _sqlite_table_exists(conn: Any, table_name: str) -> bool:
    """Return True if ``table_name`` exists in ``sqlite_master``."""
    if not conn:
        return False
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    try:
        return cur.fetchone() is not None
    finally:
        cur.close()


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

PROJECT_ACTIVITY_LOCKS_TABLE = "project_activity_locks"
PROJECT_ACTIVITY_LOCKS_DDL = (
    f"CREATE TABLE IF NOT EXISTS {PROJECT_ACTIVITY_LOCKS_TABLE} ("
    "project_id TEXT PRIMARY KEY, "
    "owner_type TEXT NOT NULL, "
    "owner_id TEXT NOT NULL, "
    "activity TEXT NOT NULL, "
    "acquired_at REAL NOT NULL, "
    "heartbeat_at REAL NOT NULL, "
    "lease_until REAL NOT NULL"
    ")"
)
PROJECT_ACTIVITY_LOCKS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_project_activity_locks_lease_until "
    f"ON {PROJECT_ACTIVITY_LOCKS_TABLE}(lease_until)"
)
RUNTIME_LOCK_SESSIONS_TABLE = "runtime_lock_sessions"
FILE_ADVISORY_LOCK_LEASES_TABLE = "file_advisory_lock_leases"
RUNTIME_LOCK_SESSIONS_DDL = (
    f"CREATE TABLE IF NOT EXISTS {RUNTIME_LOCK_SESSIONS_TABLE} ("
    "session_id TEXT PRIMARY KEY, "
    "pid INTEGER NOT NULL UNIQUE, "
    "listener_url TEXT, "
    "role TEXT NOT NULL, "
    "hostname TEXT, "
    "started_at REAL DEFAULT (julianday('now')), "
    "updated_at REAL DEFAULT (julianday('now'))"
    ")"
)
FILE_ADVISORY_LOCK_LEASES_DDL = (
    f"CREATE TABLE IF NOT EXISTS {FILE_ADVISORY_LOCK_LEASES_TABLE} ("
    "session_id TEXT NOT NULL, "
    "project_id TEXT NOT NULL, "
    "file_path TEXT NOT NULL, "
    "lock_mode TEXT NOT NULL, "
    "locked_since REAL DEFAULT (julianday('now')), "
    "updated_at REAL DEFAULT (julianday('now')), "
    "refcount INTEGER NOT NULL DEFAULT 1, "
    "PRIMARY KEY (session_id, project_id, file_path, lock_mode), "
    "FOREIGN KEY (session_id) REFERENCES runtime_lock_sessions(session_id) ON DELETE CASCADE, "
    "FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE, "
    "CHECK (lock_mode IN ('exclusive', 'shared')), "
    "CHECK (refcount > 0)"
    ")"
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS indexing_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                error_type TEXT,
                error_message TEXT,
                created_at REAL DEFAULT (julianday('now')),
                UNIQUE(project_id, file_path)
            )
            """)
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
    """Legacy hook: schema sync owns files table shape and indexes (greenfield)."""
    _ = conn, schema_manager


def ensure_project_activity_locks_table(conn: Any) -> None:
    """
    Create project_activity_locks and its index if the DB is initialized (has projects).
    Idempotent. Unix epoch times stored as REAL floats (application layer).
    """
    if not conn:
        return
    if not _sqlite_table_exists(conn, "projects"):
        return
    try:
        conn.execute(PROJECT_ACTIVITY_LOCKS_DDL)
        conn.execute(PROJECT_ACTIVITY_LOCKS_INDEX)
        conn.commit()
    except Exception as e:
        logger.warning("Could not ensure project_activity_locks table: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass


def ensure_runtime_file_lock_tables(conn: Any) -> None:
    """
    Create runtime advisory lock session/lease tables after core DB bootstrap.
    """
    if not conn:
        return
    if not _sqlite_table_exists(conn, "projects"):
        return
    try:
        conn.execute(RUNTIME_LOCK_SESSIONS_DDL)
        conn.execute(FILE_ADVISORY_LOCK_LEASES_DDL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runtime_lock_sessions_pid "
            f"ON {RUNTIME_LOCK_SESSIONS_TABLE}(pid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_advisory_lock_leases_file "
            f"ON {FILE_ADVISORY_LOCK_LEASES_TABLE}(project_id, file_path)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_advisory_lock_leases_session "
            f"ON {FILE_ADVISORY_LOCK_LEASES_TABLE}(session_id)"
        )
        conn.commit()
    except Exception as e:
        logger.warning("Could not ensure runtime file lock tables: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass


def run_all_ensure(conn: Any, schema_manager: Any, db_path: Path) -> None:
    """Run all connection-time migrations in order."""
    # Align with legacy schema bootstrap / run_create_schema: apply schema_creation_migrate so
    # existing DBs gain columns (e.g. files.deleted, projects.deleted) before RPC SQL.
    from code_analysis.core.database.schema_creation_migrate import run_migrate_schema

    run_migrate_schema(_SqliteConnMigrateAdapter(conn, schema_manager))
    ensure_files_table_migrations(conn, schema_manager)
    ensure_code_chunks_migrations(conn, schema_manager)
    ensure_indexing_worker_stats_table(conn, schema_manager)
    ensure_indexing_errors_table(conn)
    ensure_project_activity_locks_table(conn)
    ensure_runtime_file_lock_tables(conn)
    ensure_client_session_tables(conn)
    ensure_subordinate_session_tables(conn)
