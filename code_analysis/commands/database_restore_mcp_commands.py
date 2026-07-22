"""
MCP command for database restore (rebuild) from configuration.

This command implements the "recovery" workflow described by the project rules:
- create a PostgreSQL backup (pg_dump) of the database;
- reset the PostgreSQL public schema (fresh schema);
- read a configuration file that contains a list of directories;
- sequentially run analysis/indexing for each configured directory into the SAME DB,
  separating data by project_id/root_dir inside the database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .base_mcp_command_open_db import _schema_def_to_driver_format
from .database_restore_mcp_commands_helpers import (
    extract_restore_dirs_from_config,
    iter_python_files,
)
from .database_restore_mcp_commands_metadata import get_restore_database_metadata
from ..core.config import get_driver_config
from ..core.constants import DEFAULT_MAX_FILE_LINES, DEFAULT_REQUEST_TIMEOUT
from ..core.database.base import get_schema_definition
from ..core.database_client.factory import create_database_client_from_config_path
from ..core.postgres_cli_backup import (
    PostgresCliBackupError,
    backup_postgres_custom_format,
    reset_postgres_public_schema,
)
from ..core.shared_database import close_shared_database, set_shared_database
from ..core.storage_paths import load_raw_config
from ..core.worker_manager import get_worker_manager

logger = logging.getLogger(__name__)


class RestoreDatabaseFromConfigMCPCommand(BaseMCPCommand):
    """
    Restore (rebuild) PostgreSQL database by sequentially indexing directories from config.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "restore_database"
    version = "1.0.0"
    descr = (
        "Restore (rebuild) PostgreSQL database: resets schema then re-indexes "
        "(requires pg_dump + psycopg)"
    )
    category = "database_integrity"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @classmethod
    def get_schema(cls: type["RestoreDatabaseFromConfigMCPCommand"]) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": (
                "Restore database from config.json: auto-backup DB, recreate DB, "
                "then sequentially index each configured directory into the same DB."
            ),
            "properties": {
                "config_file": {
                    "type": "string",
                    "description": "Path to JSON config file (absolute or relative to server config directory).",
                    "default": "config.json",
                    "examples": ["config.json"],
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines per file threshold (for reporting).",
                    "default": 400,
                    "examples": [400],
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If True, only resolve dirs and show plan; do not recreate DB or index.",
                    "default": False,
                    "examples": [False],
                },
            },
            "required": [],
            "additionalProperties": False,
            "examples": [
                {},
                {"config_file": "config.json"},
            ],
        }

    async def execute(
        self: "RestoreDatabaseFromConfigMCPCommand",
        config_file: str = "config.json",
        max_lines: int | None = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute restore command. Config and DB path from server config.

        Args:
            self: Command instance.
            config_file: JSON config path (relative to server config dir or absolute).
            max_lines: Maximum lines per file threshold (for reporting).
            dry_run: If True, do not modify DB.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with restore summary or ErrorResult on failure.
        """
        if max_lines is None:
            max_lines = DEFAULT_MAX_FILE_LINES

        try:
            server_root = self._resolve_config_path().parent.resolve()
            cfg_path = Path(config_file)
            if not cfg_path.is_absolute():
                cfg_path = (server_root / cfg_path).resolve()

            if not cfg_path.exists() or not cfg_path.is_file():
                return ErrorResult(
                    code="CONFIG_NOT_FOUND",
                    message=f"Config file not found: {cfg_path}",
                    details={"config_file": str(cfg_path)},
                )

            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if not isinstance(cfg, dict):
                return ErrorResult(
                    code="INVALID_CONFIG",
                    message="Config must be a JSON object",
                    details={"config_file": str(cfg_path)},
                )

            restore_dirs = extract_restore_dirs_from_config(cfg)
            if not restore_dirs:
                return ErrorResult(
                    code="NO_DIRS",
                    message=(
                        "No directories found in config. Expected `code_analysis.dirs` "
                        "or `code_analysis.worker.watch_dirs`."
                    ),
                    details={"config_file": str(cfg_path)},
                )

            # Resolve dirs to absolute paths (relative to config file directory)
            cfg_root = cfg_path.parent.resolve()
            scan_roots: list[Path] = []
            for d in restore_dirs:
                p = Path(d)
                if not p.is_absolute():
                    p = (cfg_root / p).resolve()
                scan_roots.append(p)

            storage = BaseMCPCommand._get_shared_storage()
            server_cfg_path = BaseMCPCommand._resolve_config_path()
            raw_server = load_raw_config(server_cfg_path)
            driver = get_driver_config(raw_server) or {}
            driver_type = str(driver.get("type") or "postgres").lower()

            plan = {
                "driver": driver_type,
                "config_file": str(cfg_path),
                "dirs": [str(p) for p in scan_roots],
                "max_lines": max_lines,
            }
            if dry_run:
                return SuccessResult(data={"dry_run": True, "plan": plan})

            # Step 1: stop all workers
            workers_stopped = get_worker_manager().stop_all_workers(timeout=10.0)

            dcfg = driver.get("config") or {}
            if not isinstance(dcfg, dict):
                return ErrorResult(
                    message="Invalid PostgreSQL driver config",
                    code="RESTORE_DATABASE_ERROR",
                    details={"driver_type": driver_type},
                )
            try:
                backup_paths = list(
                    backup_postgres_custom_format(dcfg, backup_dir=storage.backup_dir)
                )
            except PostgresCliBackupError as e:
                return ErrorResult(
                    message=str(e),
                    code="RESTORE_DATABASE_ERROR",
                    details={"step": "pg_dump_backup"},
                )
            close_shared_database()
            try:
                reset_postgres_public_schema(dcfg)
            except PostgresCliBackupError as e:
                return ErrorResult(
                    message=str(e),
                    code="RESTORE_DATABASE_ERROR",
                    details={
                        "step": "reset_schema",
                        "db_backup_paths": backup_paths,
                    },
                )
            try:
                # Already connected: create_database_client_from_config_path runs
                # driver.connect(config) internally (stage 2 flip - no separate
                # .connect() call needed or supported on the returned object).
                new_db = create_database_client_from_config_path(
                    server_cfg_path.resolve(),
                    timeout=DEFAULT_REQUEST_TIMEOUT,
                )
                schema_def = get_schema_definition()
                schema_def = _schema_def_to_driver_format(schema_def)
                new_db.sync_schema(
                    schema_def,
                    backup_dir=(
                        str(storage.backup_dir) if storage.backup_dir else None
                    ),
                )
                set_shared_database(new_db)
            except Exception as e:
                return ErrorResult(
                    message=f"Reconnect/sync_schema after reset failed: {e}",
                    code="RESTORE_DATABASE_ERROR",
                    details={"step": "reconnect", "db_backup_paths": backup_paths},
                )

            # Step 4: sequentially analyze configured directories into the same DB
            # Use DatabaseClient via BaseMCPCommand
            # Use first directory as root_dir for database connection
            if not scan_roots:
                return ErrorResult(
                    message="No scan directories found",
                    code="NO_SCAN_DIRS",
                )

            db = BaseMCPCommand._open_database_from_config(auto_analyze=False)
            try:
                from .update_indexes_analyzer import analyze_file

                totals = {
                    "files_total": 0,
                    "files_processed": 0,
                    "errors": 0,
                    "syntax_errors": 0,
                    "classes": 0,
                    "functions": 0,
                    "methods": 0,
                    "imports": 0,
                }
                per_dir: list[dict[str, Any]] = []

                for scan_root in scan_roots:
                    if not scan_root.exists() or not scan_root.is_dir():
                        per_dir.append(
                            {
                                "root_dir": str(scan_root),
                                "status": "skipped",
                                "reason": "not_found_or_not_dir",
                            }
                        )
                        continue

                    project_id = BaseMCPCommand._get_project_id(db, scan_root)
                    py_files = list(iter_python_files(scan_root))
                    dir_stats = {
                        "root_dir": str(scan_root),
                        "project_id": project_id,
                        "files_discovered": len(py_files),
                        "files_processed": 0,
                        "errors": 0,
                        "syntax_errors": 0,
                    }
                    totals["files_total"] += len(py_files)

                    for file_path in py_files:
                        res = analyze_file(
                            database=db,
                            file_path=file_path,
                            project_id=project_id,
                            root_path=scan_root,
                        )
                        status = res.get("status")
                        if status == "success":
                            dir_stats["files_processed"] += 1
                            totals["files_processed"] += 1
                            totals["classes"] += int(res.get("classes", 0) or 0)
                            totals["functions"] += int(res.get("functions", 0) or 0)
                            totals["methods"] += int(res.get("methods", 0) or 0)
                            totals["imports"] += int(res.get("imports", 0) or 0)
                        elif status == "syntax_error":
                            dir_stats["syntax_errors"] += 1
                            totals["syntax_errors"] += 1
                        else:
                            dir_stats["errors"] += 1
                            totals["errors"] += 1

                    per_dir.append(dir_stats)

                return SuccessResult(
                    data={
                        "plan": plan,
                        "workers_stopped": workers_stopped,
                        "db_backup_paths": backup_paths,
                        "dirs_processed": per_dir,
                        "totals": totals,
                        "message": "Database restored and directories indexed",
                    }
                )
            finally:
                try:
                    if hasattr(db, "disconnect"):
                        db.disconnect()
                except Exception:
                    pass

        except Exception as e:
            return self._handle_error(e, "RESTORE_DATABASE_ERROR", "restore_database")

    @classmethod
    def metadata(cls: type["RestoreDatabaseFromConfigMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_restore_database_metadata(
            cls.name,
            cls.version,
            cls.descr,
            cls.category,
            cls.author,
            cls.email,
        )
