"""
Schema and metadata for update_indexes command (for AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Type


def get_schema() -> Dict[str, Any]:
    """Return JSON schema for update_indexes command parameters."""
    return {
        "type": "object",
        "description": (
            "Analyze Python project by project_id and update code indexes in SQLite. "
            "Long-running; executed via queue. project_id is required (from create_project or list_projects)."
        ),
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project UUID (from create_project or list_projects).",
                "examples": ["550e8400-e29b-41d4-a716-446655440000"],
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum lines per file threshold.",
                "default": 400,
                "examples": [400],
            },
        },
        "required": ["project_id"],
        "additionalProperties": False,
        "examples": [
            {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "max_lines": 400,
            },
            {"project_id": "550e8400-e29b-41d4-a716-446655440000"},
        ],
    }


def get_metadata(command_cls: Type[Any]) -> Dict[str, Any]:
    """Return detailed command metadata for update_indexes (for AI models)."""
    return {
        "name": command_cls.name,
        "version": command_cls.version,
        "description": command_cls.descr,
        "category": command_cls.category,
        "author": command_cls.author,
        "email": command_cls.email,
        "detailed_description": (
            "The update_indexes command analyzes Python project files and updates code indexes "
            "in the SQLite database. This is a long-running command executed via queue that "
            "parses Python files, extracts code entities, and stores them in the database for "
            "fast retrieval and analysis.\n\n"
            "Operation flow:\n"
            "1. Resolves project root_path from shared database by project_id\n"
            "2. Validates root_path exists and is a directory\n"
            "3. Checks database integrity (if corrupted, enters safe mode)\n"
            "4. Scans root_path for Python files (excludes .git, __pycache__, node_modules, data, logs; "
            "optional code_analysis.venv_site_packages_index_allowlisted_distributions may include "
            "allowlisted pip distributions only under .venv/venv site-packages per dist-info RECORD)\n"
            "5. For each Python file:\n"
            "   - Reads file content and parses AST\n"
            "   - Saves AST tree to database\n"
            "   - Saves CST (source code) to database\n"
            "   - Extracts classes, functions, methods, imports\n"
            "   - Calculates cyclomatic complexity for functions/methods\n"
            "   - Stores entities in database\n"
            "   - Adds content to full-text search index\n"
            "   - Marks file for chunking\n"
            "6. Updates progress tracker during processing\n"
            "7. Returns summary statistics\n\n"
            "Database Safety:\n"
            "- Checks database integrity before starting\n"
            "- If corruption detected:\n"
            "  - Creates backup of database files\n"
            "  - Writes corruption marker\n"
            "  - Stops workers\n"
            "  - Enters safe mode (only backup/restore/repair commands allowed)\n"
            "- Returns error if database is in safe mode\n\n"
            "Indexed Information:\n"
            "- Files: Path, line count, modification time, docstring status\n"
            "- Classes: Name, line, docstring, base classes\n"
            "- Functions: Name, line, parameters, docstring, complexity\n"
            "- Methods: Name, line, parameters, docstring, complexity, class context\n"
            "- Imports: Module, name, type, line\n"
            "- AST trees: Full AST JSON for each file\n"
            "- CST trees: Full source code for each file\n"
            "- Full-text search: Code content indexed for search\n\n"
            "Use cases:\n"
            "- Initial project indexing\n"
            "- Re-indexing after code changes\n"
            "- Updating indexes after adding new files\n"
            "- Rebuilding database indexes\n\n"
            "Important notes:\n"
            "- This is a long-running command (use_queue=True)\n"
            "- Progress is tracked and can be monitored via queue_get_job_status\n"
            "- Skips files with syntax errors (continues with other files)\n"
            "- Files are processed sequentially\n"
            "- Database must not be corrupted (check integrity first)\n"
            "- Excludes hidden directories and common build/cache directories"
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "Project UUID from create_project or list_projects. "
                    "Root path is resolved from the shared database."
                ),
                "type": "string",
                "required": True,
            },
            "max_lines": {
                "description": (
                    "Maximum lines per file threshold. Default is 400. "
                    "Used for reporting long files (does not affect indexing)."
                ),
                "type": "integer",
                "required": False,
                "default": 400,
            },
        },
        "usage_examples": [
            {
                "description": "Update indexes for project",
                "command": {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                "explanation": (
                    "Resolves project root from database by project_id, then analyzes "
                    "all Python files and updates indexes. Long-running; use queue_get_job_status to check progress."
                ),
            },
            {
                "description": "Update indexes with custom line threshold",
                "command": {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "max_lines": 500,
                },
                "explanation": (
                    "Updates indexes and uses 500 lines as threshold for long file reporting."
                ),
            },
        ],
        "error_cases": {
            "DATABASE_CORRUPTED": {
                "description": "Database is corrupted and in safe mode",
                "example": "Database integrity check failed or corruption marker exists",
                "solution": (
                    "Database is in safe mode. Run restore_database from backup, "
                    "then re-run update_indexes."
                ),
            },
            "INDEX_UPDATE_ERROR": {
                "description": "General error during index update",
                "example": "File access error, AST parsing error, or database error",
                "solution": (
                    "Check file permissions, verify Python files are valid, check database integrity. "
                    "Syntax errors in files are skipped automatically."
                ),
            },
        },
        "return_value": {
            "success": {
                "description": "Command executed successfully",
                "data": {
                    "project_id": "Project UUID",
                    "root_path": "Project root path that was analyzed (from database)",
                    "files_processed": "Number of files successfully processed",
                    "files_total": "Total number of files analyzed",
                    "files_discovered": "Total number of Python files discovered",
                    "errors": "Number of files with errors",
                    "syntax_errors": "Number of files with syntax errors",
                    "classes": "Total number of classes indexed",
                    "functions": "Total number of functions indexed",
                    "methods": "Total number of methods indexed",
                    "imports": "Total number of imports indexed",
                    "db_repaired": "Whether database was repaired (always False)",
                    "db_backup_paths": "List of backup paths (empty if no backup)",
                    "workers_restarted": "Dictionary of restarted workers (empty)",
                    "message": "Summary message",
                },
                "example": {
                    "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    "root_path": "/home/user/projects/my_project",
                    "files_processed": 42,
                    "files_total": 45,
                    "files_discovered": 45,
                    "errors": 2,
                    "syntax_errors": 1,
                    "classes": 25,
                    "functions": 50,
                    "methods": 100,
                    "imports": 200,
                    "db_repaired": False,
                    "db_backup_paths": [],
                    "workers_restarted": {},
                    "message": "Indexes updated: 42/45 files processed, 2 errors, 1 syntax errors",
                },
            },
            "error": {
                "description": "Command failed",
                "code": "Error code (e.g., DATABASE_CORRUPTED, INDEX_UPDATE_ERROR)",
                "message": "Human-readable error message",
                "details": "Additional error details (e.g., db_path, marker_path, backup_paths)",
            },
        },
        "best_practices": [
            "Run this command after adding new files or making significant code changes",
            "Use queue_get_job_status to monitor progress for large projects",
            "Check database integrity before running (query pg_stat_database / backup_database)",
            "Run regularly to keep indexes up-to-date",
            "If database is corrupted, repair or restore before re-indexing",
            "Review error counts in results to identify problematic files",
            "This command is required before using most other analysis commands",
        ],
    }
