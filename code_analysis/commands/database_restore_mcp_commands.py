"""
MCP command for database restore (rebuild) from configuration.

This command implements the "recovery" workflow described by the project rules:
- create an automatic filesystem backup of the SQLite DB file;
- recreate the DB file (fresh schema);
- read a configuration file that contains a list of directories;
- sequentially run analysis/indexing for each configured directory into the SAME DB,
  separating data by project_id/root_dir inside the database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.database import CodeDatabase
from ..core.db_integrity import (
    backup_sqlite_files,
    clear_corruption_marker,
    recreate_sqlite_database_file,
)
from ..core.worker_manager import get_worker_manager

logger = logging.getLogger(__name__)


def _extract_restore_dirs_from_config(cfg: dict[str, Any]) -> list[str]:
    """
    Extract directories list for restore from config.

    Args:
        cfg: Parsed config dict.

    Returns:
        List of directory paths (as strings). May be empty.
    """
    code_cfg = (
        cfg.get("code_analysis") if isinstance(cfg.get("code_analysis"), dict) else {}
    )
    dirs = code_cfg.get("dirs")
    if isinstance(dirs, list) and all(isinstance(x, str) for x in dirs):
        non_empty_dirs = [x for x in dirs if x]
        if non_empty_dirs:
            return non_empty_dirs

    worker_cfg = (
        code_cfg.get("worker") if isinstance(code_cfg.get("worker"), dict) else {}
    )
    watch_dirs = worker_cfg.get("watch_dirs")
    if isinstance(watch_dirs, list) and all(isinstance(x, str) for x in watch_dirs):
        non_empty_watch_dirs = [x for x in watch_dirs if x]
        if non_empty_watch_dirs:
            return non_empty_watch_dirs

    return []


def _iter_python_files(root_path: Path) -> Iterable[Path]:
    """
    Iterate python files under root_path.

    Args:
        root_path: Root directory to scan.

    Yields:
        Paths to .py files.
    """
    for walk_root, dirs, files in os.walk(root_path):
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".")
            and d not in ["__pycache__", "node_modules", ".git", "data", "logs"]
        ]
        for fn in files:
            if fn.endswith(".py"):
                yield Path(walk_root) / fn


class RestoreDatabaseFromConfigMCPCommand(BaseMCPCommand):
    """
    Restore (rebuild) SQLite database by sequentially indexing directories from config.

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
        "Restore (rebuild) database by indexing all configured directories sequentially"
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
                "root_dir": {
                    "type": "string",
                    "description": "Server/project root directory (contains config and data/code_analysis.db).",
                    "examples": ["/abs/path/to/server_root"],
                },
                "config_file": {
                    "type": "string",
                    "description": "Path to JSON config file (absolute or relative to root_dir).",
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
            "required": ["root_dir"],
            "additionalProperties": False,
            "examples": [
                {"root_dir": "/abs/path/to/server_root"},
                {"root_dir": "/abs/path/to/server_root", "config_file": "config.json"},
            ],
        }

    async def execute(
        self: "RestoreDatabaseFromConfigMCPCommand",
        root_dir: str,
        config_file: str = "config.json",
        max_lines: int = 400,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute restore command.

        Args:
            self: Command instance.
            root_dir: Server/project root directory (DB location).
            config_file: JSON config path.
            max_lines: Maximum lines per file threshold (for reporting).
            dry_run: If True, do not modify DB.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with restore summary or ErrorResult on failure.
        """
        try:
            server_root = self._validate_root_dir(root_dir)
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

            restore_dirs = _extract_restore_dirs_from_config(cfg)
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

            db_path = (server_root / "data" / "code_analysis.db").resolve()

            plan = {
                "db_path": str(db_path),
                "config_file": str(cfg_path),
                "dirs": [str(p) for p in scan_roots],
                "max_lines": max_lines,
            }
            if dry_run:
                return SuccessResult(data={"dry_run": True, "plan": plan})

            # Step 1: stop all workers
            workers_stopped = get_worker_manager().stop_all_workers(timeout=10.0)

            # Step 2: auto-backup DB file (+ sidecars)
            backup_paths = list(backup_sqlite_files(db_path, backup_dir=db_path.parent))

            # Step 3: recreate DB file from scratch + clear marker
            recreate_sqlite_database_file(db_path)
            clear_corruption_marker(db_path)

            # Step 4: sequentially analyze configured directories into the same DB
            from ..database import create_driver_config_for_worker

            driver_config = create_driver_config_for_worker(db_path)
            db = CodeDatabase(driver_config=driver_config)
            cmd = None
            try:
                from .code_mapper_mcp_command import UpdateIndexesMCPCommand

                cmd = UpdateIndexesMCPCommand()

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

                    project_id = db.get_or_create_project(
                        str(scan_root), name=scan_root.name
                    )
                    py_files = list(_iter_python_files(scan_root))
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
                        res = cmd._analyze_file(  # noqa: SLF001
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
                    if hasattr(db, "close"):
                        db.close()
                except Exception:
                    pass

        except Exception as e:
            return self._handle_error(e, "RESTORE_DATABASE_ERROR", "restore_database")
