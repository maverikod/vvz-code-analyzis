"""
SQLite database driver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseDatabaseDriver


class SQLiteDriver(BaseDatabaseDriver):
    """SQLite database driver."""

    @property
    def is_thread_safe(self) -> bool:
        """SQLite is not thread-safe for concurrent writes."""
        return False

    def __init__(self) -> None:
        """Initialize SQLite driver."""
        self.conn: Optional[sqlite3.Connection] = None
        self.db_path: Optional[Path] = None
        self._lastrowid: Optional[int] = None

    def connect(self, config: Dict[str, Any]) -> None:
        """
        Establish SQLite connection.

        Args:
            config: Configuration dict with 'path' key pointing to database file

        Raises:
            RuntimeError: If code is not running in DB worker process.
        """
        if "path" not in config:
            raise ValueError("SQLite driver requires 'path' in config")

        # Direct SQLite driver can only be used in DB worker process
        is_worker = os.getenv("CODE_ANALYSIS_DB_WORKER", "0") == "1"
        if not is_worker:
            raise RuntimeError(
                "Direct SQLite driver can only be used in DB worker process. "
                "Use sqlite_proxy driver instead."
            )

        self.db_path = Path(config["path"]).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Allow connection to be used from different threads
        # Thread safety is ensured by locks in CodeDatabase
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")

    def disconnect(self) -> None:
        """Close SQLite connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
        self._lastrowid = None

    def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> None:
        """
        Execute SQL statement.

        Args:
            sql: SQL statement
            params: Optional parameters for parameterized query
        """
        if not self.conn:
            raise RuntimeError("Database connection not established")

        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        # Store lastrowid for later retrieval
        self._lastrowid = cursor.lastrowid

    def fetchone(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute SELECT query and return first row.

        Args:
            sql: SQL SELECT statement
            params: Optional parameters for parameterized query

        Returns:
            Dictionary with column names as keys, or None if no rows
        """
        if not self.conn:
            raise RuntimeError("Database connection not established")

        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(
        self, sql: str, params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute SELECT query and return all rows.

        Args:
            sql: SQL SELECT statement
            params: Optional parameters for parameterized query

        Returns:
            List of dictionaries with column names as keys
        """
        if not self.conn:
            raise RuntimeError("Database connection not established")

        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def commit(self) -> None:
        """Commit current transaction."""
        if not self.conn:
            raise RuntimeError("Database connection not established")
        self.conn.commit()

    def rollback(self) -> None:
        """Rollback current transaction."""
        if not self.conn:
            raise RuntimeError("Database connection not established")
        self.conn.rollback()

    def lastrowid(self) -> Optional[int]:
        """
        Get last inserted row ID.

        Returns:
            Last inserted row ID or None
        """
        return self._lastrowid

    def create_schema(self, schema_sql: List[str]) -> None:
        """
        Create database schema.

        Args:
            schema_sql: List of SQL statements for schema creation
        """
        if not self.conn:
            raise RuntimeError("Database connection not established")

        cursor = self.conn.cursor()
        for sql in schema_sql:
            cursor.execute(sql)
        self.conn.commit()

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get information about table columns using PRAGMA.

        Args:
            table_name: Name of the table

        Returns:
            List of dictionaries with column information
        """
        if not self.conn:
            raise RuntimeError("Database connection not established")

        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        rows = cursor.fetchall()
        # Convert to list of dicts
        columns = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
        return [dict(zip(columns, row)) for row in rows]

    def begin_transaction(self) -> None:
        """Begin a transaction."""
        if not self.conn:
            raise RuntimeError("Database connection not established")
        self.conn.execute("BEGIN TRANSACTION")

    def sync_schema(
        self, schema_definition: Dict[str, Any], backup_dir: Path
    ) -> Dict[str, Any]:
        """
        Synchronize database schema with code schema.

        Blocks database during synchronization using file lock.
        Validates data compatibility BEFORE making changes.
        If validation fails - leaves database unchanged, blocks connection, logs error.
        Driver handles data migration during schema changes.
        Rolls back on error.

        Args:
            schema_definition: Schema definition from CodeDatabase._get_schema_definition()
            backup_dir: Directory for database backups (from StoragePaths)

        Raises:
            RuntimeError: If schema sync fails (blocks connection)

        Returns:
            Dict with sync results:
            {
                "success": bool,
                "backup_uuid": Optional[str],
                "changes_applied": List[str],
                "error": Optional[str]
            }
        """
        import fcntl
        import logging

        logger = logging.getLogger(__name__)

        result = {
            "success": False,
            "backup_uuid": None,
            "changes_applied": [],
            "error": None,
        }

        # Lock file for schema synchronization
        lock_file = Path(str(self.db_path) + ".schema_sync.lock")
        lock_fd = None

        try:
            # Acquire lock before synchronization
            lock_fd = open(lock_file, "w")
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            logger.info("Schema sync lock acquired")

            # Get current schema version (defaults to "0.0.0" if not set)
            current_version = self._get_schema_version() or "0.0.0"
            from ..database.base import SCHEMA_VERSION

            code_version = schema_definition.get("version", SCHEMA_VERSION)

            # Compare schemas using SchemaComparator (runs in same process)
            from ..database.schema_sync import SchemaComparator

            comparator = SchemaComparator(self, schema_definition)
            diff = comparator.compare_schemas()

            if not diff.has_changes():
                # Schema is up to date
                if current_version != code_version:
                    # Update version only
                    self._set_schema_version(code_version)
                    self.commit()
                result["success"] = True
                return result

            # Validate data compatibility BEFORE making changes
            logger.info("Validating data compatibility before schema changes...")
            validation_result = comparator.validate_data_compatibility(diff)
            if not validation_result["compatible"]:
                error_msg = (
                    f"Data compatibility check failed: {validation_result['error']}"
                )
                logger.error(error_msg)
                # Leave database unchanged, block connection
                raise RuntimeError(error_msg)

            # Schema changes needed - create backup (only if DB is not empty)
            # CRITICAL: If backup fails, do NOT proceed with migration
            # Get project root for BackupManager
            if self.db_path.parent.name == "data":
                project_root = self.db_path.parent.parent
            else:
                project_root = self.db_path.parent

            from ..backup_manager import BackupManager

            backup_manager = BackupManager(project_root)
            backup_uuid = backup_manager.create_database_backup(
                self.db_path,
                backup_dir=backup_dir,
                comment=f"Schema sync: {current_version} -> {code_version}",
            )

            # If backup failed (returned None) and DB is not empty, block migration
            if backup_uuid is None:
                # Check if DB is actually empty (backup manager skips empty DBs)
                # If DB has data but backup failed, this is an error
                try:
                    test_conn = sqlite3.connect(str(self.db_path))
                    cursor = test_conn.cursor()
                    cursor.execute(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    )
                    table_count = cursor.fetchone()[0]
                    test_conn.close()

                    if table_count > 0:
                        # DB has tables but backup failed - block migration
                        error_msg = "Database backup failed but database contains data. Migration blocked for safety."
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
                except Exception as e:
                    logger.warning(f"Could not verify if database is empty: {e}")
                    # If we can't verify, assume it's not empty and block migration
                    error_msg = "Database backup failed and could not verify database state. Migration blocked for safety."
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e

            result["backup_uuid"] = backup_uuid

            # Run version-specific migration methods if needed
            # Migration methods are called in order from current_version to code_version
            from ..database.base import MIGRATION_METHODS

            def _version_compare(v1: str, v2: str) -> int:
                """
                Compare version strings (e.g., "1.0.0" vs "1.1.0").

                Returns:
                    -1 if v1 < v2
                     0 if v1 == v2
                     1 if v1 > v2
                """
                v1_parts = [int(x) for x in v1.split(".")]
                v2_parts = [int(x) for x in v2.split(".")]
                max_len = max(len(v1_parts), len(v2_parts))
                v1_parts.extend([0] * (max_len - len(v1_parts)))
                v2_parts.extend([0] * (max_len - len(v2_parts)))
                for a, b in zip(v1_parts, v2_parts):
                    if a < b:
                        return -1
                    elif a > b:
                        return 1
                return 0

            # Get migration versions between current and target version
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
                logger.info(f"Running migration for version {migration_version}")
                migration_func(self)

            # Begin transaction for atomic schema changes
            self.begin_transaction()
            try:
                # Generate and apply migration SQL (driver handles data migration)
                migration_sql = comparator.generate_migration_sql(diff)
                for sql in migration_sql:
                    self.execute(sql)
                    result["changes_applied"].append(sql)

                # Update schema version
                self._set_schema_version(code_version)
                self.commit()

                result["success"] = True
                logger.info(
                    f"Schema synchronized: {len(result['changes_applied'])} changes applied"
                )
                return result

            except Exception as e:
                # Rollback on error
                self.rollback()
                raise RuntimeError(f"Schema sync failed during migration: {e}") from e

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Schema sync failed: {e}", exc_info=True)
            # Re-raise to block connection
            raise RuntimeError(f"Schema synchronization failed: {e}") from e

        finally:
            # Release lock
            if lock_fd:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                    lock_fd.close()
                    logger.info("Schema sync lock released")
                except Exception:
                    pass

    def _get_schema_version(self) -> Optional[str]:
        """Get current schema version from database."""
        try:
            result = self.fetchone(
                "SELECT value FROM db_settings WHERE key = ?", ("schema_version",)
            )
            return result["value"] if result else None
        except Exception:
            return None

    def _set_schema_version(self, version: str) -> None:
        """Set schema version in database."""
        self.execute(
            """
            INSERT OR REPLACE INTO db_settings (key, value, updated_at)
            VALUES (?, ?, julianday('now'))
            """,
            ("schema_version", version),
        )
        self.commit()
