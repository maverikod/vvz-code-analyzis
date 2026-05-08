"""
DB worker SQLite schema sync: legacy comparator API over RPC-process SQLiteDriver.

The database_driver_pkg SQLiteDriver uses a different execute contract and a simplified
sync_schema; the worker still needs full SchemaComparator-based migration. This adapter
composes the RPC driver for connect/disconnect (shared integrity/migrations on open) and
implements void execute plus fetch helpers on the underlying connection.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import fcntl
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from code_analysis.core.database.schema_sync import SchemaComparator
from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver

from ..backup_manager import BackupManager
from ..database.schema_definition import MIGRATION_METHODS, SCHEMA_VERSION
from ..db_integrity import fix_all_stale_fks_in_connection

logger = logging.getLogger(__name__)


class SqliteWorkerSchemaSyncAdapter:
    """Wraps database_driver_pkg SQLiteDriver for worker-side full schema sync."""

    def __init__(self) -> None:
        self._driver = SQLiteDriver()

    def connect(self, config: Dict[str, Any]) -> None:
        self._driver.connect(config)

    def disconnect(self) -> None:
        self._driver.disconnect()

    @property
    def conn(self) -> Optional[sqlite3.Connection]:
        return cast(Optional[sqlite3.Connection], self._driver.conn)

    @property
    def db_path(self) -> Optional[Path]:
        return cast(Optional[Path], self._driver.db_path)

    def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> None:
        if not self._driver.conn:
            raise RuntimeError("Database connection not established")
        cursor = self._driver.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

    def fetchone(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> Optional[Dict[str, Any]]:
        if not self._driver.conn:
            raise RuntimeError("Database connection not established")
        cursor = self._driver.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
        if not self._driver.conn:
            raise RuntimeError("Database connection not established")
        cursor = self._driver.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def commit(self) -> None:
        self._driver.commit()

    def rollback(self) -> None:
        self._driver.rollback()

    def begin_transaction(self) -> None:
        if not self._driver.conn:
            raise RuntimeError("Database connection not established")
        self._driver.conn.execute("BEGIN TRANSACTION")

    def _get_schema_version(self) -> Optional[str]:
        try:
            result = self.fetchone(
                "SELECT value FROM db_settings WHERE key = ?", ("schema_version",)
            )
            return result["value"] if result else None
        except Exception:
            return None

    def _set_schema_version(self, version: str) -> None:
        self.execute(
            """
            INSERT OR REPLACE INTO db_settings (key, value, updated_at)
            VALUES (?, ?, julianday('now'))
            """,
            ("schema_version", version),
        )
        self.commit()

    def sync_schema(
        self, schema_definition: Dict[str, Any], backup_dir: Path
    ) -> Dict[str, Any]:
        """
        Synchronize database schema with code schema (same behavior as legacy in-process SQLite).

        Blocks database during synchronization using file lock.
        Validates data compatibility BEFORE making changes.
        """
        result: Dict[str, Any] = {
            "success": False,
            "backup_uuid": None,
            "changes_applied": [],
            "error": None,
        }

        if self.db_path is None:
            raise RuntimeError("Database path not set")

        lock_file = Path(str(self.db_path) + ".schema_sync.lock")
        lock_fd = None

        try:
            lock_fd = open(lock_file, "w")
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            logger.info("Schema sync lock acquired")

            current_version = self._get_schema_version() or "0.0.0"
            code_version = schema_definition.get("version", SCHEMA_VERSION)

            comparator = SchemaComparator(self, schema_definition)
            diff = comparator.compare_schemas()

            if not diff.has_changes():
                if current_version != code_version:
                    self._set_schema_version(code_version)
                    self.commit()
                result["success"] = True
                return result

            logger.info("Validating data compatibility before schema changes...")
            validation_result = comparator.validate_data_compatibility(diff)
            if not validation_result["compatible"]:
                error_msg = (
                    f"Data compatibility check failed: {validation_result['error']}"
                )
                logger.error("%s", error_msg)
                raise RuntimeError(error_msg)

            if self.db_path.parent.name == "data":
                project_root = self.db_path.parent.parent
            else:
                project_root = self.db_path.parent

            backup_manager = BackupManager(project_root)
            backup_uuid = backup_manager.create_database_backup(
                self.db_path,
                backup_dir=backup_dir,
                comment=f"Schema sync: {current_version} -> {code_version}",
            )

            if backup_uuid is None:
                try:
                    test_conn = sqlite3.connect(str(self.db_path))
                    cursor = test_conn.cursor()
                    cursor.execute(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    )
                    table_count = cursor.fetchone()[0]
                    test_conn.close()

                    if table_count > 0:
                        error_msg = (
                            "Database backup failed but database contains data. "
                            "Migration blocked for safety."
                        )
                        logger.error("%s", error_msg)
                        raise RuntimeError(error_msg)
                except Exception as e:
                    logger.warning("Could not verify if database is empty: %s", e)
                    error_msg = (
                        "Database backup failed and could not verify database state. "
                        "Migration blocked for safety."
                    )
                    logger.error("%s", error_msg)
                    raise RuntimeError(error_msg) from e

            result["backup_uuid"] = backup_uuid

            def _version_compare(v1: str, v2: str) -> int:
                v1_parts = [int(x) for x in v1.split(".")]
                v2_parts = [int(x) for x in v2.split(".")]
                max_len = max(len(v1_parts), len(v2_parts))
                v1_parts.extend([0] * (max_len - len(v1_parts)))
                v2_parts.extend([0] * (max_len - len(v2_parts)))
                for a, b in zip(v1_parts, v2_parts):
                    if a < b:
                        return -1
                    if a > b:
                        return 1
                return 0

            migration_versions = sorted(
                [
                    v
                    for v in MIGRATION_METHODS.keys()
                    if _version_compare(v, current_version) > 0
                    and _version_compare(v, code_version) <= 0
                ],
                key=lambda v: tuple(int(x) for x in v.split(".")),
            )

            for migration_version in migration_versions:
                migration_func = MIGRATION_METHODS[migration_version]
                logger.info("Running migration for version %s", migration_version)
                migration_func(self)

            self.execute("PRAGMA foreign_keys = OFF")
            self.begin_transaction()
            try:
                migration_sql = comparator.generate_migration_sql(diff)
                for i, sql in enumerate(migration_sql):
                    try:
                        self.execute(sql)
                    except Exception as e:
                        logger.error(
                            "Migration failed at statement %s: %s: %s",
                            i,
                            sql[:200],
                            e,
                        )
                        raise
                    result["changes_applied"].append(sql)

                self._set_schema_version(code_version)

                changes = result.get("changes_applied") or []
                if any(
                    "ALTER TABLE files RENAME TO temp_files" in s
                    or "ALTER TABLE methods RENAME TO temp_methods" in s
                    for s in changes
                ):
                    if self.conn and fix_all_stale_fks_in_connection(self.conn):
                        logger.info(
                            "Fixed all stale FKs (temp_files/temp_methods) in "
                            "migration transaction"
                        )

                self.execute("PRAGMA foreign_keys = ON")
                self.commit()

                result["success"] = True
                logger.info(
                    "Schema synchronized: %s changes applied",
                    len(result["changes_applied"]),
                )
                return result

            except Exception as e:
                try:
                    self.execute("PRAGMA foreign_keys = ON")
                except Exception:
                    pass
                self.rollback()
                raise RuntimeError(f"Schema sync failed during migration: {e}") from e

        except Exception as e:
            result["error"] = str(e)
            logger.error("Schema sync failed: %s", e, exc_info=True)
            raise RuntimeError(f"Schema synchronization failed: {e}") from e

        finally:
            if lock_fd:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                    lock_fd.close()
                    logger.info("Schema sync lock released")
                except Exception:
                    pass
