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
            "description": "Get database safe-mode/corruption status for a project.",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db).",
                    "examples": ["/abs/path/to/project"],
                }
            },
            "required": ["root_dir"],
            "additionalProperties": False,
            "examples": [{"root_dir": "/abs/path/to/project"}],
        }

    async def execute(
        self: "GetDatabaseCorruptionStatusMCPCommand",
        root_dir: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute corruption status command.

        Args:
            self: Command instance.
            root_dir: Project root directory.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with status payload or ErrorResult on failure.
        """
        try:
            from ..core.db_integrity import (
                check_sqlite_integrity,
                corruption_marker_path,
                read_corruption_marker,
            )

            root_path = self._validate_root_dir(root_dir)
            db_path = (root_path / "data" / "code_analysis.db").resolve()

            marker = read_corruption_marker(db_path)
            marker_path = str(corruption_marker_path(db_path))

            check = check_sqlite_integrity(db_path)
            return SuccessResult(
                data={
                    "root_dir": str(root_path),
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
            "description": "Create filesystem backup of data/code_analysis.db for the project.",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db).",
                    "examples": ["/abs/path/to/project"],
                },
                "backup_dir": {
                    "type": "string",
                    "description": "Optional directory where backup files will be stored (default: root_dir/data).",
                    "examples": ["/abs/path/to/project/data"],
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
            "examples": [
                {"root_dir": "/abs/path/to/project"},
                {
                    "root_dir": "/abs/path/to/project",
                    "backup_dir": "/abs/path/to/project/data",
                },
            ],
        }

    async def execute(
        self: "BackupDatabaseMCPCommand",
        root_dir: str,
        backup_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute database backup command.

        Args:
            self: Command instance.
            root_dir: Project root directory.
            backup_dir: Optional backup directory path.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with backup paths or ErrorResult on failure.
        """
        try:
            from ..core.db_integrity import backup_sqlite_files

            root_path = self._validate_root_dir(root_dir)
            db_path = (root_path / "data" / "code_analysis.db").resolve()
            out_dir = (
                Path(backup_dir).resolve()
                if backup_dir
                else (root_path / "data").resolve()
            )

            backups = backup_sqlite_files(
                db_path, backup_dir=out_dir, include_sidecars=True
            )
            return SuccessResult(
                data={
                    "root_dir": str(root_path),
                    "db_path": str(db_path),
                    "backup_dir": str(out_dir),
                    "backup_paths": list(backups),
                    "count": len(backups),
                }
            )
        except Exception as e:
            return self._handle_error(e, "BACKUP_DATABASE_ERROR", "backup_database")


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
            "description": "Backup and recreate data/code_analysis.db, then clear safe-mode marker.",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db).",
                    "examples": ["/abs/path/to/project"],
                },
                "force": {
                    "type": "boolean",
                    "description": "Must be true to perform destructive repair.",
                    "default": False,
                    "examples": [True],
                },
                "backup_dir": {
                    "type": "string",
                    "description": "Optional directory where backup files will be stored (default: root_dir/data).",
                    "examples": ["/abs/path/to/project/data"],
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
            "examples": [
                {"root_dir": "/abs/path/to/project", "force": True},
            ],
        }

    async def execute(
        self: "RepairSQLiteDatabaseMCPCommand",
        root_dir: str,
        force: bool = False,
        backup_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute SQLite repair command.

        Args:
            self: Command instance.
            root_dir: Project root directory.
            force: Must be True to perform repair.
            backup_dir: Optional directory where backups will be stored.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with repair result or ErrorResult on failure.
        """
        try:
            from ..core.db_integrity import (
                clear_corruption_marker,
                ensure_sqlite_integrity_or_recreate,
            )
            from ..core.worker_manager import get_worker_manager

            if not force:
                return ErrorResult(
                    code="CONFIRM_REQUIRED",
                    message=(
                        "This operation is destructive (recreates SQLite DB). "
                        "Re-run with force=true to proceed."
                    ),
                )

            root_path = self._validate_root_dir(root_dir)
            db_path = (root_path / "data" / "code_analysis.db").resolve()
            out_dir = (
                Path(backup_dir).resolve()
                if backup_dir
                else (root_path / "data").resolve()
            )

            stop_result = get_worker_manager().stop_all_workers(timeout=10.0)
            repair = ensure_sqlite_integrity_or_recreate(db_path, backup_dir=out_dir)
            marker_cleared = clear_corruption_marker(db_path)

            return SuccessResult(
                data={
                    "root_dir": str(root_path),
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
