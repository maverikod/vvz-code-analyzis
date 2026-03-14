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
            from ...core.db_integrity import (
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
