"""MCP commands for SQLite database integrity safe mode.

These commands implement a strict policy:
- if a project DB is detected as corrupted, DB-dependent commands are blocked;
- only backup/restore/repair commands are allowed.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand

logger = logging.getLogger(__name__)


class GetDatabaseCorruptionStatusMCPCommand(BaseMCPCommand):
    """Get persistent database corruption status for a project.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "get_database_corruption_status"
    version = "1.0.0"
    descr = "Get corruption marker and quick_check status for project database"
    category = "database_integrity"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["GetDatabaseCorruptionStatusMCPCommand"],
    ) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": "Get database safe-mode/corruption status for the shared DB (one DB for all projects).",
            "properties": {},
            "required": [],
            "additionalProperties": False,
            "examples": [{}],
        }

    async def execute(
        self: "GetDatabaseCorruptionStatusMCPCommand",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute corruption status command.

        Uses the shared database path from server config (one DB for all projects).

        Returns:
            SuccessResult with status payload or ErrorResult on failure.
        """
        try:
            from ..core.db_integrity import (
                check_sqlite_integrity,
                corruption_marker_path,
                read_corruption_marker,
            )

            storage = BaseMCPCommand._get_shared_storage()
            db_path = storage.db_path

            marker = read_corruption_marker(db_path)
            marker_path = str(corruption_marker_path(db_path))

            check = check_sqlite_integrity(db_path)
            return SuccessResult(
                data={
                    "db_path": str(db_path),
                    "marker_path": marker_path,
                    "marker_present": marker is not None,
                    "marker": marker,
                    "integrity_ok": check.ok,
                    "integrity_message": check.message,
                }
            )
        except Exception as e:
            return self._handle_error(
                e,
                "DB_CORRUPTION_STATUS_ERROR",
                "get_database_corruption_status",
            )

    @classmethod
    def metadata(cls: type["GetDatabaseCorruptionStatusMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The get_database_corruption_status command checks the corruption status "
                "of a project's SQLite database. It reports both the persistent corruption "
                "marker status and the current physical integrity check result.\n\n"
                "Operation flow:\n"
                "1. Resolves database path from server config (one shared DB for all projects)\n"
                "2. Reads persistent corruption marker (if present)\n"
                "3. Runs SQLite integrity check (PRAGMA quick_check)\n"
                "4. Returns combined status information\n\n"
                "Corruption Marker:\n"
                "- Persistent marker file stored next to database\n"
                "- Created when corruption is detected\n"
                "- Prevents DB-dependent commands from running\n"
                "- Contains backup paths and error message\n"
                "- Must be cleared explicitly after repair\n\n"
                "Integrity Check:\n"
                "- Uses SQLite PRAGMA quick_check(1) for fast check\n"
                "- Falls back to PRAGMA integrity_check if needed\n"
                "- Detects physical corruption (malformed database)\n"
                "- Ignores transient errors (database locked, busy)\n"
                "- Returns OK if database file doesn't exist (not corrupted)\n\n"
                "Safe Mode Policy:\n"
                "- If marker present, DB-dependent commands are blocked\n"
                "- Only backup/restore/repair commands allowed\n"
                "- Prevents further corruption from operations\n"
                "- Ensures data safety during recovery\n\n"
                "Use cases:\n"
                "- Check database health before operations\n"
                "- Diagnose corruption issues\n"
                "- Verify marker status after repair\n"
                "- Monitor database integrity\n"
                "- Troubleshoot database errors\n\n"
                "Important notes:\n"
                "- Marker presence blocks DB-dependent commands\n"
                "- Integrity check is read-only (doesn't modify DB)\n"
                "- Transient lock errors are not treated as corruption\n"
                "- Marker must be cleared after successful repair\n"
                "- Both marker and integrity status are reported"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Optional; ignored. Database path is taken from server config (shared DB)."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [],
                },
            },
            "usage_examples": [
                {
                    "description": "Check shared database corruption status",
                    "command": {},
                    "explanation": (
                        "Checks both corruption marker and integrity status for the shared database."
                    ),
                },
            ],
            "error_cases": {
                "DB_CORRUPTION_STATUS_ERROR": {
                    "description": "Error during status check",
                    "example": (
                        "Invalid root_dir, permission errors, or unexpected exceptions"
                    ),
                    "solution": (
                        "Verify root_dir exists and is accessible, check file permissions, "
                        "review logs for details"
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Status check completed successfully",
                    "data": {
                        "db_path": "Path to shared database file (from server config)",
                        "marker_path": "Path to corruption marker file",
                        "marker_present": "True if corruption marker exists",
                        "marker": (
                            "Marker data if present (None otherwise). Contains:\n"
                            "- message: Error message\n"
                            "- backup_paths: List of backup file paths\n"
                            "- timestamp: When marker was created"
                        ),
                        "integrity_ok": "True if database integrity check passed",
                        "integrity_message": "Message from integrity check",
                    },
                    "example_healthy": {
                        "db_path": "/var/code_analysis/data/code_analysis.db",
                        "marker_path": "/home/user/projects/my_project/data/code_analysis.db.corrupt-marker",
                        "marker_present": False,
                        "marker": None,
                        "integrity_ok": True,
                        "integrity_message": "quick_check: ok",
                    },
                    "example_corrupted": {
                        "db_path": "/var/code_analysis/data/code_analysis.db",
                        "marker_path": "/home/user/projects/my_project/data/code_analysis.db.corrupt-marker",
                        "marker_present": True,
                        "marker": {
                            "message": "Database is marked as corrupted",
                            "backup_paths": [
                                "/home/user/projects/my_project/data/code_analysis.db.corrupt-backup.20240115-143025"
                            ],
                            "timestamp": "2024-01-15T14:30:25",
                        },
                        "integrity_ok": False,
                        "integrity_message": "integrity_check failed: database disk image is malformed",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., DB_CORRUPTION_STATUS_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Check status before running DB-dependent operations",
                "If marker_present=True, run repair_sqlite_database to fix",
                "If integrity_ok=False, database needs repair",
                "Use backup_database before repair operations",
                "Clear marker after successful repair (done automatically by repair command)",
                "Monitor integrity_ok status regularly",
            ],
        }


class BackupDatabaseMCPCommand(BaseMCPCommand):
    """Create a filesystem backup of the project SQLite database file.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "backup_database"
    version = "1.0.0"
    descr = "Backup project SQLite database file (db + wal/shm/journal if present)"
    category = "database_integrity"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["BackupDatabaseMCPCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": "Create filesystem backup of the shared database (one DB for all projects).",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Optional; ignored. DB path from server config.",
                    "examples": [],
                },
                "backup_dir": {
                    "type": "string",
                    "description": "Optional directory for backup files (default: backup_dir from server config).",
                    "examples": ["/abs/path/to/backups"],
                },
            },
            "required": [],
            "additionalProperties": False,
            "examples": [{}, {"backup_dir": "/abs/path/to/backups"}],
        }

    async def execute(
        self: "BackupDatabaseMCPCommand",
        root_dir: Optional[str] = None,
        backup_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute database backup command.

        Uses shared DB path from server config (one DB for all projects).

        Args:
            self: Command instance.
            root_dir: Optional; ignored.
            backup_dir: Optional backup directory (default: from server config).
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with backup paths or ErrorResult on failure.
        """
        try:
            from ..core.db_integrity import backup_sqlite_files

            storage = BaseMCPCommand._get_shared_storage()
            db_path = storage.db_path
            out_dir = Path(backup_dir).resolve() if backup_dir else storage.backup_dir

            backups = backup_sqlite_files(
                db_path, backup_dir=out_dir, include_sidecars=True
            )
            return SuccessResult(
                data={
                    "db_path": str(db_path),
                    "backup_dir": str(out_dir),
                    "backup_paths": list(backups),
                    "count": len(backups),
                }
            )
        except Exception as e:
            return self._handle_error(e, "BACKUP_DATABASE_ERROR", "backup_database")

    @classmethod
    def metadata(cls: type["BackupDatabaseMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The backup_database command creates filesystem backups of a project's "
                "SQLite database file and its sidecar files (WAL, SHM, journal). "
                "This is a safety measure before destructive operations like repair.\n\n"
                "Operation flow:\n"
                "1. Resolves database path from server config (one shared DB for all projects)\n"
                "2. Determines backup directory (default: backup_dir from server config)\n"
                "3. Creates timestamped backups of database file\n"
                "4. Creates backups of sidecar files if present (-wal, -shm, -journal)\n"
                "5. Returns list of created backup file paths\n\n"
                "Backup Files:\n"
                "- Main database file: code_analysis.db.corrupt-backup.TIMESTAMP\n"
                "- WAL file (if present): code_analysis.db-wal.corrupt-backup.TIMESTAMP\n"
                "- SHM file (if present): code_analysis.db-shm.corrupt-backup.TIMESTAMP\n"
                "- Journal file (if present): code_analysis.db-journal.corrupt-backup.TIMESTAMP\n"
                "- Timestamp format: YYYYMMDD-HHMMSS\n\n"
                "Sidecar Files:\n"
                "- WAL (Write-Ahead Logging): Transaction log for SQLite\n"
                "- SHM (Shared Memory): Shared memory file for WAL mode\n"
                "- Journal: Rollback journal (if not in WAL mode)\n"
                "- These files are critical for database consistency\n\n"
                "Use cases:\n"
                "- Create backup before repair operations\n"
                "- Preserve database state before destructive changes\n"
                "- Create recovery point for database restoration\n"
                "- Backup before major database operations\n"
                "- Safety measure before corruption repair\n\n"
                "Important notes:\n"
                "- Backups are created with timestamp in filename\n"
                "- Multiple backups can coexist (each has unique timestamp)\n"
                "- Only existing files are backed up (missing sidecars are skipped)\n"
                "- Backup directory is created if it doesn't exist\n"
                "- Original files are not modified (read-only operation)\n"
                "- Use restore_database to restore from backup"
            ),
            "parameters": {
                "root_dir": {
                    "description": "Optional; ignored. DB path from server config.",
                    "type": "string",
                    "required": False,
                    "examples": [],
                },
                "backup_dir": {
                    "description": (
                        "Optional directory where backup files will be stored. "
                        "If not provided, uses backup_dir from server config. "
                        "Directory is created if it doesn't exist."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["/backups/code_analysis"],
                },
            },
            "usage_examples": [
                {
                    "description": "Backup shared database to default location",
                    "command": {},
                    "explanation": (
                        "Creates backups in server config backup_dir with timestamped filenames."
                    ),
                },
                {
                    "description": "Backup database to custom location",
                    "command": {"backup_dir": "/backups/code_analysis"},
                    "explanation": (
                        "Creates backups in specified directory instead of default."
                    ),
                },
            ],
            "error_cases": {
                "BACKUP_DATABASE_ERROR": {
                    "description": "Error during backup creation",
                    "examples": [
                        {
                            "case": "Database file not found",
                            "message": "Database file does not exist",
                            "solution": (
                                "Verify database path is correct. "
                                "Database may not exist yet (this is OK, backup will be empty)."
                            ),
                        },
                        {
                            "case": "Permission error",
                            "message": "Permission denied",
                            "solution": (
                                "Check file and directory permissions. "
                                "Ensure write access to backup directory."
                            ),
                        },
                        {
                            "case": "Disk space",
                            "message": "No space left on device",
                            "solution": "Free up disk space in backup directory",
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "Backup created successfully",
                    "data": {
                        "db_path": "Path to shared database file (from server config)",
                        "backup_dir": "Directory where backups were created",
                        "backup_paths": (
                            "List of created backup file paths. Includes:\n"
                            "- Database file backup\n"
                            "- Sidecar file backups (if present)"
                        ),
                        "count": "Number of backup files created",
                    },
                    "example": {
                        "db_path": "/var/code_analysis/data/code_analysis.db",
                        "backup_dir": "/var/code_analysis/backups",
                        "backup_paths": [
                            "/var/code_analysis/backups/code_analysis.db.corrupt-backup.20240115-143025",
                            "/var/code_analysis/backups/code_analysis.db-wal.corrupt-backup.20240115-143025",
                        ],
                        "count": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., BACKUP_DATABASE_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Run backup_database before repair_sqlite_database",
                "Use backup_database before any destructive database operations",
                "Store backups in separate directory for safety",
                "Keep multiple backups with different timestamps",
                "Verify backup_paths list after backup creation",
                "Use restore_database to restore from backup if needed",
                "Backup is automatically created by repair command, but manual backup is safer",
            ],
        }


class RepairSQLiteDatabaseMCPCommand(BaseMCPCommand):
    """Repair corrupted SQLite database file by recreating it from scratch.

    Notes:
        This is a destructive operation for the DB content. After recreation, you
        should re-run `update_indexes` for the project.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "repair_sqlite_database"
    version = "1.0.0"
    descr = "Repair corrupted SQLite database file (backup + recreate + clear marker)"
    category = "database_integrity"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["RepairSQLiteDatabaseMCPCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": "Backup and recreate the shared database, then clear safe-mode marker (one DB for all projects).",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Optional; ignored. DB path from server config.",
                    "examples": [],
                },
                "force": {
                    "type": "boolean",
                    "description": "Must be true to perform destructive repair.",
                    "default": False,
                    "examples": [True],
                },
                "backup_dir": {
                    "type": "string",
                    "description": "Optional directory for backups (default: backup_dir from server config).",
                    "examples": ["/abs/path/to/backups"],
                },
            },
            "required": [],
            "additionalProperties": False,
            "examples": [{"force": True}],
        }

    async def execute(
        self: "RepairSQLiteDatabaseMCPCommand",
        root_dir: Optional[str] = None,
        force: bool = False,
        backup_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute SQLite repair command.

        Uses shared DB path from server config (one DB for all projects).

        Args:
            self: Command instance.
            root_dir: Optional; ignored.
            force: Must be True to perform repair.
            backup_dir: Optional directory for backups (default: from server config).
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with repair result or ErrorResult on failure.
        """
        try:
            from ..core.db_integrity import (
                check_sqlite_integrity,
                clear_corruption_marker,
                ensure_sqlite_integrity_or_recreate,
                read_corruption_marker,
                recover_files_table_if_needed,
            )
            from ..core.worker_manager import get_worker_manager

            storage = BaseMCPCommand._get_shared_storage()
            db_path = storage.db_path
            out_dir = Path(backup_dir).resolve() if backup_dir else storage.backup_dir

            if not force:
                # Non-destructive mode: allow clearing marker when DB is healthy.
                # This is useful when a marker was created due to transient errors
                # (e.g. "database is locked") or after manual recovery.
                marker = read_corruption_marker(db_path)
                if marker is not None:
                    integrity = check_sqlite_integrity(db_path)
                    if integrity.ok:
                        marker_cleared = clear_corruption_marker(db_path)
                        return SuccessResult(
                            data={
                                "db_path": str(db_path),
                                "mode": "marker_clear_only",
                                "integrity_ok": True,
                                "integrity_message": integrity.message,
                                "marker_cleared": marker_cleared,
                                "next_step": "Re-run the blocked command (marker cleared)",
                            }
                        )

                # Non-destructive: recover files table if migration left temp_files (no files).
                if recover_files_table_if_needed(db_path):
                    return SuccessResult(
                        data={
                            "db_path": str(db_path),
                            "mode": "files_table_recovered",
                            "files_table_recovered": True,
                            "next_step": "Re-run indexing or update_indexes; no force=true needed",
                        }
                    )

                return ErrorResult(
                    code="CONFIRM_REQUIRED",
                    message=(
                        "This operation is destructive (recreates SQLite DB). "
                        "Re-run with force=true to proceed. "
                        "If you only need to clear a marker, ensure DB integrity is OK and retry with force=false."
                    ),
                )

            stop_result = get_worker_manager().stop_all_workers(timeout=10.0)
            repair = ensure_sqlite_integrity_or_recreate(db_path, backup_dir=out_dir)
            marker_cleared = clear_corruption_marker(db_path)

            return SuccessResult(
                data={
                    "db_path": str(db_path),
                    "backup_dir": str(out_dir),
                    "workers_stopped": stop_result,
                    "repair": {
                        "ok": repair.ok,
                        "repaired": repair.repaired,
                        "message": repair.message,
                        "backup_paths": list(repair.backup_paths),
                    },
                    "marker_cleared": marker_cleared,
                    "next_step": "Run update_indexes for the project to rebuild indexes",
                }
            )
        except Exception as e:
            return self._handle_error(
                e, "REPAIR_SQLITE_ERROR", "repair_sqlite_database"
            )

    @classmethod
    def metadata(cls: type["RepairSQLiteDatabaseMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The repair_sqlite_database command repairs a corrupted SQLite database "
                "by backing it up and recreating it from scratch. This is a destructive "
                "operation that removes all data from the database.\n\n"
                "Operation flow:\n"
                "1. Resolves database path from server config (one shared DB for all projects)\n"
                "2. If force=False, checks if only marker clearing is needed\n"
                "3. If force=False and DB is healthy, clears marker only\n"
                "4. If force=False and DB is corrupted, requires force=True\n"
                "5. If force=True, stops all workers\n"
                "6. Creates automatic backup of database and sidecars\n"
                "7. Recreates database file from scratch (empty schema)\n"
                "8. Clears corruption marker\n"
                "9. Returns repair result with next steps\n\n"
                "Repair Modes:\n"
                "- Non-destructive (force=False): Only clears marker if DB is healthy\n"
                "  - Useful when marker was set due to transient errors\n"
                "  - Does not recreate database\n"
                "  - Safe operation, no data loss\n"
                "- Destructive (force=True): Backs up and recreates database\n"
                "  - All database data is lost\n"
                "  - Creates fresh empty database\n"
                "  - Requires explicit confirmation (force=True)\n\n"
                "Worker Management:\n"
                "- All workers are stopped before repair\n"
                "- Prevents concurrent access during repair\n"
                "- Workers can be restarted after repair\n\n"
                "After Repair:\n"
                "- Database is empty (fresh schema)\n"
                "- Corruption marker is cleared\n"
                "- Must run update_indexes to rebuild indexes\n"
                "- All project data must be re-indexed\n\n"
                "Use cases:\n"
                "- Repair corrupted database\n"
                "- Clear corruption marker after manual recovery\n"
                "- Recover from database corruption\n"
                "- Reset database to clean state\n"
                "- Fix database integrity issues\n\n"
                "Important notes:\n"
                "- ⚠️ DESTRUCTIVE: All database data is lost when force=True\n"
                "- Automatic backup is created before recreation\n"
                "- Must run update_indexes after repair to rebuild data\n"
                "- Use force=False to clear marker without data loss\n"
                "- Workers are stopped automatically during repair"
            ),
            "parameters": {
                "root_dir": {
                    "description": "Optional; ignored. DB path from server config.",
                    "type": "string",
                    "required": False,
                    "examples": [],
                },
                "force": {
                    "description": (
                        "Must be True to perform destructive repair (recreate database). "
                        "If False, only clears marker if database is healthy. "
                        "Default is False."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [False, True],
                },
                "backup_dir": {
                    "description": (
                        "Optional directory where backup files will be stored. "
                        "If not provided, uses backup_dir from server config. "
                        "Backup is created automatically before repair."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["/backups/code_analysis"],
                },
            },
            "usage_examples": [
                {
                    "description": "Clear marker without data loss",
                    "command": {"force": False},
                    "explanation": (
                        "Clears corruption marker if database is healthy. "
                        "No data loss, safe operation."
                    ),
                },
                {
                    "description": "Repair corrupted database",
                    "command": {"force": True},
                    "explanation": (
                        "Backs up and recreates shared database. All data is lost. "
                        "Must run update_indexes after repair."
                    ),
                },
                {
                    "description": "Repair with custom backup location",
                    "command": {"force": True, "backup_dir": "/backups/code_analysis"},
                    "explanation": (
                        "Repairs database and stores backup in custom location."
                    ),
                },
            ],
            "error_cases": {
                "CONFIRM_REQUIRED": {
                    "description": "Force confirmation required",
                    "message": (
                        "This operation is destructive (recreates SQLite DB). "
                        "Re-run with force=true to proceed."
                    ),
                    "solution": (
                        "Set force=True to confirm destructive operation. "
                        "If you only need to clear marker, ensure DB is healthy and use force=False."
                    ),
                },
                "REPAIR_SQLITE_ERROR": {
                    "description": "Error during repair",
                    "examples": [
                        {
                            "case": "Permission error",
                            "message": "Permission denied",
                            "solution": (
                                "Check file and directory permissions. "
                                "Ensure write access to database and backup directory."
                            ),
                        },
                        {
                            "case": "Workers cannot be stopped",
                            "message": "Failed to stop workers",
                            "solution": (
                                "Manually stop workers or wait for operations to complete. "
                                "Workers must be stopped before repair."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "Repair completed successfully",
                    "data": {
                        "db_path": "Path to shared database file (from server config)",
                        "backup_dir": "Directory where backups were created",
                        "workers_stopped": "Result of stopping workers",
                        "repair": {
                            "ok": "True if repair succeeded",
                            "repaired": "True if database was recreated",
                            "message": "Human-readable repair message",
                            "backup_paths": "List of created backup file paths",
                        },
                        "marker_cleared": "True if corruption marker was cleared",
                        "next_step": "Recommended next action (usually 'Run update_indexes')",
                        "mode": "Repair mode (only present if force=False and marker cleared)",
                    },
                    "example_marker_clear": {
                        "db_path": "/var/code_analysis/data/code_analysis.db",
                        "mode": "marker_clear_only",
                        "integrity_ok": True,
                        "integrity_message": "quick_check: ok",
                        "marker_cleared": True,
                        "next_step": "Re-run the blocked command (marker cleared)",
                    },
                    "example_full_repair": {
                        "db_path": "/var/code_analysis/data/code_analysis.db",
                        "backup_dir": "/var/code_analysis/backups",
                        "workers_stopped": {"stopped": True, "count": 2},
                        "repair": {
                            "ok": True,
                            "repaired": True,
                            "message": (
                                "Database was corrupted; backed up 2 file(s) and recreated"
                            ),
                            "backup_paths": [
                                "/var/code_analysis/backups/code_analysis.db.corrupt-backup.20240115-143025",
                                "/var/code_analysis/backups/code_analysis.db-wal.corrupt-backup.20240115-143025",
                            ],
                        },
                        "marker_cleared": True,
                        "next_step": "Run update_indexes for the project to rebuild indexes",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., CONFIRM_REQUIRED, REPAIR_SQLITE_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "⚠️ WARNING: force=True destroys all database data",
                "Run backup_database manually before repair for extra safety",
                "Use force=False first to clear marker if DB is healthy",
                "After repair, immediately run update_indexes to rebuild data",
                "Check repair.repaired field to confirm database was recreated",
                "Verify backup_paths list to ensure backup was created",
                "Use restore_database if you need to restore from backup",
                "Stop workers manually if automatic stop fails",
            ],
        }
