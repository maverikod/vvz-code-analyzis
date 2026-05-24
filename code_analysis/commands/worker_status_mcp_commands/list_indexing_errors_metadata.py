"""
Metadata for list_indexing_errors MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Type


def get_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return full metadata dict for ListIndexingErrorsMCPCommand."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "The list_indexing_errors command returns rows from the indexing_errors table. "
            "That table records failures when the indexing worker (index_file) fails to index a file "
            "(e.g. syntax error, missing table, I/O error). Each row is kept until the file is "
            "successfully indexed again; successful index_file or update_file_data clears the row.\n\n"
            "Operation flow:\n"
            "1. Opens database from server config (same DB as get_database_status)\n"
            "2. If table indexing_errors does not exist, returns empty list and table_missing: true\n"
            "3. Builds SELECT with optional filters (project_id, file_path substring)\n"
            "4. Orders by created_at DESC, applies limit (default 200, max 1000)\n"
            "5. Returns data.total (number of rows) and data.list (list of error rows)\n\n"
            "Output fields per row (data.list[].):\n"
            "- id: Row primary key\n"
            "- project_id: Project UUID the file belongs to\n"
            "- file_path: Relative path of the file that failed indexing\n"
            "- error_type: 'index_error' (result.success False) or 'index_exception' (exception)\n"
            "- error_message: Human-readable error (e.g. parse error, exception message)\n"
            "- created_at: ISO timestamp when the error was recorded\n\n"
            "Response top-level:\n"
            "- total: Length of list (number of rows returned)\n"
            "- list: Array of row objects\n"
            "- table_missing: Present and true only when indexing_errors table does not exist (older DB)\n\n"
            "Use cases:\n"
            "- Inspect why certain files are not indexed or vectorized\n"
            "- Filter by file path to find errors for one file or directory\n"
            "- Filter by project_id to see errors for one project\n"
            "- Monitor indexing health and fix syntax/import errors in source files\n"
            "- After fixing a file, re-run indexer and confirm the error row is gone (success clears it)\n\n"
            "Important notes:\n"
            "- Database path is taken from server config; no root_dir parameter\n"
            "- file_path_filter uses SQL LIKE '%value%' (substring, case-sensitive)\n"
            "- limit must be 1–1000; out-of-range values are rejected in validate_params\n"
            "- If the table does not exist, the command does not fail; it returns total: 0, list: [], table_missing: true\n"
            "- Read-only; no database modifications"
        ),
        "parameters": {
            "file_path_filter": {
                "description": (
                    "Optional. Only errors whose file_path contains this string "
                    "(substring, case-sensitive). Examples: 'test_ftp', 'vast_srv/commands', 'tests/'"
                ),
                "type": "string",
                "required": False,
                "examples": ["test_ftp", "vast_srv/commands", "tests/"],
            },
            "project_id": {
                "description": "Optional. Only errors for this project UUID. Use list_projects to get IDs.",
                "type": "string",
                "required": False,
            },
            "limit": {
                "description": (
                    "Max rows to return. Default 200 (1–1000). Order: newest first (created_at DESC)."
                ),
                "type": "integer",
                "required": False,
                "default": 200,
            },
        },
        "usage_examples": [
            {
                "description": "List all indexing errors",
                "command": {},
                "explanation": "Returns up to 200 most recent errors (default limit).",
            },
            {
                "description": "Filter by file path substring",
                "command": {"file_path_filter": "test_ftp"},
                "explanation": "Returns only errors whose file_path contains 'test_ftp'.",
            },
            {
                "description": "Filter by project",
                "command": {"project_id": "123e4567-e89b-12d3-a456-426614174000"},
                "explanation": "Returns errors for the given project only.",
            },
            {
                "description": "More rows and path filter",
                "command": {"file_path_filter": "tests/", "limit": 500},
                "explanation": "Up to 500 errors for paths containing 'tests/'.",
            },
        ],
        "error_cases": {
            "LIST_INDEXING_ERRORS_ERROR": {
                "description": "Error while opening DB or executing query (e.g. non-table DB error)",
                "examples": [
                    {
                        "case": "Database connection error",
                        "message": "Error connecting to database",
                        "solution": "Verify server config and database path. Use get_database_status to check DB availability.",
                    },
                    {
                        "case": "Query error (other than missing table)",
                        "message": "Error executing query",
                        "solution": "If table exists but query fails, check schema. Missing table returns success with table_missing: true, not this error.",
                    },
                ],
            },
        },
        "return_value": {
            "success": {
                "description": "Errors listed successfully or table missing (graceful)",
                "data": {
                    "total": "Number of rows in list",
                    "list": "Array of objects: id, project_id, file_path, error_type, error_message, created_at",
                    "table_missing": "Optional. Present and true only when indexing_errors table does not exist",
                },
                "example": {
                    "total": 2,
                    "list": [
                        {
                            "id": 1,
                            "project_id": "123e4567-e89b-12d3-a456-426614174000",
                            "file_path": "src/test_ftp.py",
                            "error_type": "index_error",
                            "error_message": "SyntaxError: invalid syntax (line 42)",
                            "created_at": "2024-01-15T14:30:00",
                        },
                        {
                            "id": 2,
                            "project_id": "123e4567-e89b-12d3-a456-426614174000",
                            "file_path": "legacy/old.py",
                            "error_type": "index_exception",
                            "error_message": "ModuleNotFoundError: No module named 'foo'",
                            "created_at": "2024-01-15T14:25:00",
                        },
                    ],
                },
                "example_table_missing": {
                    "total": 0,
                    "list": [],
                    "table_missing": True,
                },
            },
            "error": {
                "description": "Command failed (e.g. LIST_INDEXING_ERRORS_ERROR)",
                "code": "Error code",
                "message": "Human-readable error message",
            },
        },
        "best_practices": [
            "Use file_path_filter to narrow down to one file or directory when debugging",
            "Use project_id to see errors per project after list_projects",
            "Check error_message and error_type to fix source (syntax, imports); then re-run indexer",
            "When table_missing is true, DB is older and indexing_errors are not recorded yet",
            "Combine with get_database_status to see needing_indexing count and list_indexing_errors for causes",
            "Limit to 200–500 unless you need a full export; default 200 is usually enough",
        ],
    }
