"""
Metadata for restore_database MCP command (for AI/man page style docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict


def get_restore_database_metadata(
    name: str,
    version: str,
    description: str,
    category: str,
    author: str,
    email: str,
) -> Dict[str, Any]:
    """Build full metadata dict for restore_database command."""
    return {
        "name": name,
        "version": version,
        "description": description,
        "category": category,
        "author": author,
        "email": email,
        "detailed_description": (
            "The restore_database command rebuilds the **shared** PostgreSQL database "
            "(from active server config) and re-indexes directories from the JSON config "
            "file you pass. Flow: ``pg_dump -Fc`` backup, ``close_shared_database``, "
            "``DROP SCHEMA public CASCADE`` + ``CREATE SCHEMA public`` (via psycopg), "
            "new ``DatabaseClient`` + ``sync_schema``, then index. "
            "Requires ``pg_dump`` on PATH (or ``pg_dump_path``) and psycopg for the schema reset.\n\n"
            "Operation flow:\n"
            "1. Loads and parses the given config file (JSON) for directory list\n"
            "2. Resolves directory paths (code_analysis.dirs or code_analysis.worker.watch_dirs); "
            "if both are empty, falls back to every currently registered watch_dirs-table "
            "absolute path\n"
            "3. If dry_run=True, returns plan without executing\n"
            "4. Stops all workers to prevent concurrent access\n"
            "5. Backs up current database via PostgreSQL pg_dump\n"
            "6. Resets public schema + sync_schema\n"
            "7. Sequentially indexes each configured directory\n"
            "8. Returns summary with statistics\n\n"
            "Config File Format:\n"
            "- JSON file (typically config.json)\n"
            "- Looks for directories in:\n"
            "  1. code_analysis.dirs (array of directory paths)\n"
            "  2. code_analysis.worker.watch_dirs (array of directory paths)\n"
            "  3. Fallback (only when both above are empty/missing): every absolute "
            "path currently registered in the watch_dirs table\n"
            "- Directories can be absolute or relative to config file location\n"
            "- Empty directories are skipped\n"
            "- plan.dirs_source reports which source was used: 'config' or "
            "'watch_dirs_table'\n\n"
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
                "description": (
                    "No directories found in config, and no watch directories "
                    "registered in the watch_dirs table"
                ),
                "message": (
                    "No directories found in config (code_analysis.dirs or "
                    "code_analysis.worker.watch_dirs) and no watch directories "
                    "registered in the watch_dirs table."
                ),
                "solution": (
                    "Add directories array to config file:\n"
                    '- code_analysis.dirs: ["/path/to/dir1", "/path/to/dir2"]\n'
                    '- OR code_analysis.worker.watch_dirs: ["/path/to/dir1"]\n'
                    "- OR register at least one watch directory (create_project / "
                    "watch_dir management commands) so the watch_dirs-table "
                    "fallback has something to restore."
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
                        "driver": "Always 'postgres'",
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
                        "driver": "postgres",
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
                        "driver": "postgres",
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
