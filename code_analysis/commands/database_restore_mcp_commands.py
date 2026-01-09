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
from typing import Any, Dict, Iterable

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.constants import DEFAULT_MAX_FILE_LINES
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
    from ..core.constants import DATA_DIR_NAME, DEFAULT_IGNORE_PATTERNS, LOGS_DIR_NAME

    ignore_dirs = DEFAULT_IGNORE_PATTERNS | {DATA_DIR_NAME, LOGS_DIR_NAME}
    for walk_root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ignore_dirs]
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
        max_lines: int | None = None,
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
                If None, uses DEFAULT_MAX_FILE_LINES from constants.
            dry_run: If True, do not modify DB.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with restore summary or ErrorResult on failure.
        """
        if max_lines is None:
            max_lines = DEFAULT_MAX_FILE_LINES

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

    @classmethod
    def metadata(cls: type["RestoreDatabaseFromConfigMCPCommand"]) -> Dict[str, Any]:
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
                "The restore_database command rebuilds a SQLite database by sequentially "
                "indexing all configured directories. It implements a complete recovery workflow: "
                "backup existing database, recreate fresh database, then index all configured "
                "directories into the same database.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Loads and parses config file (JSON)\n"
                "3. Extracts directory list from config (code_analysis.dirs or code_analysis.worker.watch_dirs)\n"
                "4. Resolves all directories to absolute paths\n"
                "5. If dry_run=True, returns plan without executing\n"
                "6. Stops all workers to prevent concurrent access\n"
                "7. Creates automatic backup of existing database\n"
                "8. Recreates database file from scratch (fresh schema)\n"
                "9. Clears corruption marker\n"
                "10. Sequentially indexes each configured directory\n"
                "11. Returns summary with statistics\n\n"
                "Config File Format:\n"
                "- JSON file (typically config.json)\n"
                "- Looks for directories in:\n"
                "  1. code_analysis.dirs (array of directory paths)\n"
                "  2. code_analysis.worker.watch_dirs (array of directory paths)\n"
                "- Directories can be absolute or relative to config file location\n"
                "- Empty directories are skipped\n\n"
                "Indexing Process:\n"
                "- Each directory is processed sequentially\n"
                "- Python files are discovered recursively\n"
                "- Each file is analyzed and indexed into database\n"
                "- Project ID is created/retrieved for each directory\n"
                "- Statistics are collected per directory and total\n\n"
                "Statistics Collected:\n"
                "- files_total: Total Python files discovered\n"
                "- files_processed: Successfully indexed files\n"
                "- errors: Files with analysis errors\n"
                "- syntax_errors: Files with syntax errors\n"
                "- classes: Total classes indexed\n"
                "- functions: Total functions indexed\n"
                "- methods: Total methods indexed\n"
                "- imports: Total imports indexed\n\n"
                "Use cases:\n"
                "- Rebuild database after corruption\n"
                "- Restore database from configuration\n"
                "- Re-index all projects from scratch\n"
                "- Migrate database to new structure\n"
                "- Recover from database loss\n"
                "- Initialize database for new setup\n\n"
                "Important notes:\n"
                "- ⚠️ DESTRUCTIVE: Existing database is recreated (all data lost)\n"
                "- Automatic backup is created before recreation\n"
                "- All workers are stopped during restore\n"
                "- Process is sequential (one directory at a time)\n"
                "- Use dry_run=True to preview plan without executing\n"
                "- This is a long-running operation (use_queue=True)\n"
                "- Directories are indexed into same database (separated by project_id)"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Server/project root directory. Contains config file and "
                        "data/code_analysis.db. Can be absolute or relative."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/my_project",
                        ".",
                        "./code_analysis",
                    ],
                },
                "config_file": {
                    "description": (
                        "Path to JSON configuration file. Can be absolute or relative to root_dir. "
                        "Must contain code_analysis.dirs or code_analysis.worker.watch_dirs array."
                    ),
                    "type": "string",
                    "required": False,
                    "default": "config.json",
                    "examples": [
                        "config.json",
                        "/home/user/projects/my_project/config.json",
                    ],
                },
                "max_lines": {
                    "description": (
                        "Maximum lines per file threshold for reporting. "
                        "Used for long file detection in statistics."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 400,
                    "examples": [400, 500],
                },
                "dry_run": {
                    "description": (
                        "If True, only resolves directories and shows plan without executing. "
                        "No database modifications are made. Useful for previewing restore operation."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [False, True],
                },
            },
            "usage_examples": [
                {
                    "description": "Preview restore plan without executing",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "config_file": "config.json",
                        "dry_run": True,
                    },
                    "explanation": (
                        "Shows which directories will be indexed without modifying database."
                    ),
                },
                {
                    "description": "Restore database from config",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "config_file": "config.json",
                    },
                    "explanation": (
                        "Rebuilds database by indexing all directories from config. "
                        "This is a long-running operation."
                    ),
                },
                {
                    "description": "Restore with custom config file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "config_file": "/path/to/custom_config.json",
                    },
                    "explanation": (
                        "Uses custom config file instead of default config.json."
                    ),
                },
            ],
            "error_cases": {
                "CONFIG_NOT_FOUND": {
                    "description": "Config file not found",
                    "message": "Config file not found: {config_file}",
                    "solution": (
                        "Verify config_file path is correct. "
                        "Ensure file exists and is readable."
                    ),
                },
                "INVALID_CONFIG": {
                    "description": "Config file is not valid JSON object",
                    "message": "Config must be a JSON object",
                    "solution": (
                        "Check config file format. Must be valid JSON with object structure."
                    ),
                },
                "NO_DIRS": {
                    "description": "No directories found in config",
                    "message": (
                        "No directories found in config. Expected code_analysis.dirs "
                        "or code_analysis.worker.watch_dirs."
                    ),
                    "solution": (
                        "Add directories array to config file:\n"
                        '- code_analysis.dirs: ["/path/to/dir1", "/path/to/dir2"]\n'
                        '- OR code_analysis.worker.watch_dirs: ["/path/to/dir1"]'
                    ),
                },
                "RESTORE_DATABASE_ERROR": {
                    "description": "Error during restore operation",
                    "examples": [
                        {
                            "case": "Permission error",
                            "message": "Permission denied",
                            "solution": (
                                "Check file and directory permissions. "
                                "Ensure write access to database and read access to source directories."
                            ),
                        },
                        {
                            "case": "Workers cannot be stopped",
                            "message": "Failed to stop workers",
                            "solution": (
                                "Manually stop workers or wait for operations to complete."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "Restore completed successfully",
                    "data": {
                        "plan": {
                            "db_path": "Path to database file",
                            "config_file": "Path to config file used",
                            "dirs": "List of directories to index",
                            "max_lines": "Maximum lines threshold",
                        },
                        "workers_stopped": "Result of stopping workers",
                        "db_backup_paths": "List of created backup file paths",
                        "dirs_processed": (
                            "List of per-directory statistics. Each contains:\n"
                            "- root_dir: Directory path\n"
                            "- project_id: Project UUID\n"
                            "- files_discovered: Number of Python files found\n"
                            "- files_processed: Successfully indexed files\n"
                            "- errors: Files with errors\n"
                            "- syntax_errors: Files with syntax errors\n"
                            "- status: Processing status (or 'skipped' with reason)"
                        ),
                        "totals": {
                            "files_total": "Total Python files discovered",
                            "files_processed": "Successfully indexed files",
                            "errors": "Files with errors",
                            "syntax_errors": "Files with syntax errors",
                            "classes": "Total classes indexed",
                            "functions": "Total functions indexed",
                            "methods": "Total methods indexed",
                            "imports": "Total imports indexed",
                        },
                        "message": "Human-readable success message",
                        "dry_run": "True if dry_run mode (only present if True)",
                    },
                    "example_dry_run": {
                        "dry_run": True,
                        "plan": {
                            "db_path": "/home/user/projects/my_project/data/code_analysis.db",
                            "config_file": "/home/user/projects/my_project/config.json",
                            "dirs": [
                                "/home/user/projects/project1",
                                "/home/user/projects/project2",
                            ],
                            "max_lines": 400,
                        },
                    },
                    "example_full_restore": {
                        "plan": {
                            "db_path": "/home/user/projects/my_project/data/code_analysis.db",
                            "config_file": "/home/user/projects/my_project/config.json",
                            "dirs": [
                                "/home/user/projects/project1",
                                "/home/user/projects/project2",
                            ],
                            "max_lines": 400,
                        },
                        "workers_stopped": {"stopped": True, "count": 2},
                        "db_backup_paths": [
                            "/home/user/projects/my_project/data/code_analysis.db.corrupt-backup.20240115-143025",
                        ],
                        "dirs_processed": [
                            {
                                "root_dir": "/home/user/projects/project1",
                                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                                "files_discovered": 150,
                                "files_processed": 148,
                                "errors": 0,
                                "syntax_errors": 2,
                            },
                            {
                                "root_dir": "/home/user/projects/project2",
                                "project_id": "223e4567-e89b-12d3-a456-426614174001",
                                "files_discovered": 200,
                                "files_processed": 200,
                                "errors": 0,
                                "syntax_errors": 0,
                            },
                        ],
                        "totals": {
                            "files_total": 350,
                            "files_processed": 348,
                            "errors": 0,
                            "syntax_errors": 2,
                            "classes": 45,
                            "functions": 120,
                            "methods": 300,
                            "imports": 500,
                        },
                        "message": "Database restored and directories indexed",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": (
                        "Error code (e.g., CONFIG_NOT_FOUND, INVALID_CONFIG, "
                        "NO_DIRS, RESTORE_DATABASE_ERROR)"
                    ),
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "best_practices": [
                "⚠️ WARNING: This operation destroys all existing database data",
                "Use dry_run=True first to preview the restore plan",
                "Ensure config file contains correct directory paths",
                "Verify all directories exist and are accessible",
                "This is a long-running operation - use queue for execution",
                "Check totals.files_processed to verify indexing success",
                "Review dirs_processed to see per-directory statistics",
                "Use backup_database manually before restore for extra safety",
                "After restore, database is ready for use (no update_indexes needed)",
                "Monitor syntax_errors and errors in statistics",
            ],
        }
