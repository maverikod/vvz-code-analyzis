"""MCP commands for SQLite database integrity safe mode.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand

logger = logging.getLogger(__name__)


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
            from ...core.db_integrity import backup_sqlite_files

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
