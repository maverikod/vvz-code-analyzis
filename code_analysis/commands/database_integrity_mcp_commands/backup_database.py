"""MCP commands for PostgreSQL database backup.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ...core.config import get_driver_config
from ...core.postgres_cli_backup import (
    PostgresCliBackupError,
    backup_postgres_custom_format,
)
from ...core.storage_paths import load_raw_config
from ..base_mcp_command import BaseMCPCommand

logger = logging.getLogger(__name__)


class BackupDatabaseMCPCommand(BaseMCPCommand):
    """Create a PostgreSQL backup of the project database (pg_dump custom format).

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
    descr = "Backup PostgreSQL database (pg_dump -Fc, custom format)"
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
            "description": (
                "Create a PostgreSQL backup of the shared database via "
                "pg_dump custom format (requires pg_dump on PATH)."
            ),
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
            config_path = BaseMCPCommand._resolve_config_path()
            raw = load_raw_config(config_path)
            driver = get_driver_config(raw) or {}
            driver_type = str(driver.get("type") or "").lower()
            storage = BaseMCPCommand._get_shared_storage()
            out_dir = Path(backup_dir).resolve() if backup_dir else storage.backup_dir

            dcfg = driver.get("config") or {}
            if not isinstance(dcfg, dict):
                return ErrorResult(
                    message="Invalid PostgreSQL driver config (expected object)",
                    code="BACKUP_DATABASE_ERROR",
                    details={"driver_type": driver_type},
                )
            try:
                backups = backup_postgres_custom_format(dcfg, backup_dir=out_dir)
            except PostgresCliBackupError as e:
                return ErrorResult(
                    message=str(e),
                    code="BACKUP_DATABASE_ERROR",
                    details={"driver_type": driver_type},
                )
            return SuccessResult(
                data={
                    "driver": "postgres",
                    "backup_dir": str(out_dir),
                    "backup_paths": list(backups),
                    "count": len(backups),
                    "format": "custom",
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
                "The backup_database command backs up the shared PostgreSQL database "
                "from server config. It runs ``pg_dump -Fc`` (custom format) using "
                "``code_analysis.database.driver.config``; ``pg_dump`` must be on PATH "
                "or set ``pg_dump_path`` in driver config.\n\n"
                "Operation flow:\n"
                "1. Resolves driver config from server config (one shared DB for all projects)\n"
                "2. Determines backup directory (default: backup_dir from server config)\n"
                "3. Runs pg_dump -Fc against the configured database\n"
                "4. Returns list of created backup file paths\n\n"
                "Backup Files:\n"
                "- Custom-format pg_dump archive, timestamped filename\n"
                "- Timestamp format: YYYYMMDD-HHMMSS\n\n"
                "Use cases:\n"
                "- Create backup before repair operations\n"
                "- Preserve database state before destructive changes\n"
                "- Create recovery point for database restoration\n"
                "- Backup before major database operations\n\n"
                "Important notes:\n"
                "- Backups are created with timestamp in filename\n"
                "- Multiple backups can coexist (each has unique timestamp)\n"
                "- Backup directory is created if it doesn't exist\n"
                "- Original database is not modified (read-only operation)\n"
                "- Use restore_database to restore from backup"
            ),
            "parameters": {
                "root_dir": {
                    "description": "Optional; ignored. DB config from server config.",
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
                        "driver": "Always 'postgres'",
                        "backup_dir": "Directory where backups were created",
                        "backup_paths": "List of created pg_dump backup file paths",
                        "count": "Number of backup files created",
                        "format": "Always 'custom' (pg_dump -Fc)",
                    },
                    "example": {
                        "driver": "postgres",
                        "backup_dir": "/var/code_analysis/backups",
                        "backup_paths": [
                            "/var/code_analysis/backups/code_analysis.pgdump.20240115-143025",
                        ],
                        "count": 1,
                        "format": "custom",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., BACKUP_DATABASE_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use backup_database before any destructive database operations",
                "Store backups in separate directory for safety",
                "Keep multiple backups with different timestamps",
                "Verify backup_paths list after backup creation",
                "Use restore_database to restore from backup if needed",
            ],
        }
