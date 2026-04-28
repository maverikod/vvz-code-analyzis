"""
Metadata for get_database_status MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Type


def get_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return full metadata dict for GetDatabaseStatusMCPCommand."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "The get_database_status command provides comprehensive monitoring of the "
            "database state (SQLite file or PostgreSQL per server config), statistics, and "
            "pending work. It reports file statistics, chunk statistics, project information, "
            "and recent activity to help monitor database health and identify work that needs "
            "to be done.\n\n"
            "Operation flow:\n"
            "1. Loads server config and resolves storage paths\n"
            "2. Uses the shared long-lived database connection (same as other MCP commands)\n"
            "3. For SQLite: reports db_path file size when the file exists; for PostgreSQL: "
            "database_driver is postgres and file_size_mb is not applicable\n"
            "4. Opens database connection\n"
            "6. Queries project statistics\n"
            "7. Queries file statistics (total, deleted, indexed, needing indexing, needing chunking)\n"
            "8. Queries chunk statistics (total, vectorized, not vectorized)\n"
            "9. Queries recent activity (last 24 hours)\n"
            "10. Gets samples of files needing indexing and needing chunking\n"
            "11. Gets samples of chunks needing vectorization\n"
            "12. Returns comprehensive status report\n\n"
            "File Statistics:\n"
            "- total: Total number of files in database\n"
            "- deleted: Number of deleted files\n"
            "- active: Number of active (non-deleted) files\n"
            "- with_docstring: Files that have docstrings\n"
            "- indexed: Files indexed by indexing worker (needs_chunking=0)\n"
            "- indexed_percent: Percentage of active files indexed\n"
            "- needing_indexing: Active files with needs_chunking=1 (pending indexer)\n"
            "- needing_indexing_sample: Sample of files needing indexing (up to 10)\n"
            "- needing_chunking: Active files without chunks\n"
            "- needing_chunking_sample: Sample of files needing chunking (up to 10)\n\n"
            "Chunk Statistics:\n"
            "- total: Total number of code chunks\n"
            "- vectorized: Chunks with embedding vectors\n"
            "- not_vectorized: Chunks without embedding vectors\n"
            "- vectorization_percent: Percentage of chunks that are vectorized\n"
            "- needing_vectorization_sample: Sample of chunks needing vectorization (up to 10)\n\n"
            "Project Statistics:\n"
            "- total: Total number of projects\n"
            "- sample: Sample of projects (up to 10) with id and name\n\n"
            "Recent Activity:\n"
            "- files_updated_24h: Files updated in last 24 hours\n"
            "- chunks_updated_24h: Chunks created in last 24 hours\n\n"
            "Use cases:\n"
            "- Monitor database health and size\n"
            "- Check pending work (files needing chunking, chunks needing vectorization)\n"
            "- Track project and file statistics\n"
            "- Monitor recent activity\n"
            "- Identify files that need processing\n"
            "- Verify vectorization progress\n"
            "- Database capacity planning\n\n"
            "Important notes:\n"
            "- Uses the same database as the server (from config); shared DB must be initialized\n"
            "- Statistics are calculated from database queries\n"
            "- Samples are limited to 10 items each\n"
            "- Recent activity uses Julian-day thresholds: SQLite julianday(), PostgreSQL EXTRACT(JULIAN ...)\n"
            "- File size (SQLite only) is reported in megabytes\n"
            "- All statistics are read-only (no database modifications)"
        ),
        "parameters": {
            "root_dir": {
                "description": (
                    "Project root directory path. Can be absolute or relative. "
                    "Must contain data/code_analysis.db file."
                ),
                "type": "string",
                "required": True,
                "examples": ["/home/user/projects/my_project", ".", "./code_analysis"],
            },
        },
        "usage_examples": [
            {
                "description": "Check database status",
                "command": {"root_dir": "/home/user/projects/my_project"},
                "explanation": (
                    "Returns comprehensive database statistics including files, chunks, "
                    "projects, and recent activity."
                ),
            },
            {
                "description": "Monitor database health",
                "command": {"root_dir": "."},
                "explanation": (
                    "Checks database status in current directory to monitor health and pending work."
                ),
            },
        ],
        "error_cases": {
            "DATABASE_STATUS_ERROR": {
                "description": "Error during database status check",
                "examples": [
                    {
                        "case": "Database file not found",
                        "message": "Database file not found",
                        "solution": (
                            "Verify root_dir is correct and database exists. "
                            "Run update_indexes to create database if needed."
                        ),
                    },
                    {
                        "case": "Database connection error",
                        "message": "Error connecting to database",
                        "solution": (
                            "Check database file permissions. "
                            "Verify database is not corrupted (use get_database_corruption_status)."
                        ),
                    },
                    {
                        "case": "Query error",
                        "message": "Error executing query",
                        "solution": (
                            "Database schema may be outdated. "
                            "Check database integrity and consider repair if needed."
                        ),
                    },
                ],
            },
        },
        "return_value": {
            "success": {
                "description": "Database status retrieved successfully",
                "data": {
                    "db_path": "Path to database file",
                    "timestamp": "ISO timestamp of status check",
                    "exists": "True if database file exists",
                    "file_size_mb": "Database file size in megabytes",
                    "projects": {
                        "total": "Total number of projects",
                        "sample": "List of project samples (up to 10) with id and name",
                    },
                    "files": {
                        "total": "Total number of files",
                        "deleted": "Number of deleted files",
                        "active": "Number of active (non-deleted) files",
                        "with_docstring": "Files with docstrings",
                        "indexed": "Files indexed by indexing worker (needs_chunking=0)",
                        "indexed_percent": "Percentage of active files indexed",
                        "needing_indexing": "Active files with needs_chunking=1 (pending indexer)",
                        "needing_indexing_sample": (
                            "Sample of files needing indexing (up to 10). Each contains: id (UUID "
                            "string files.pk), path, has_docstring, last_modified"
                        ),
                        "needing_chunking": "Active files without chunks",
                        "needing_chunking_sample": (
                            "Sample of files needing chunking (up to 10). Each contains: id (UUID "
                            "string files.pk), path, has_docstring, last_modified"
                        ),
                    },
                    "chunks": {
                        "total": "Total number of chunks",
                        "vectorized": "Chunks with embedding vectors",
                        "not_vectorized": "Chunks without embedding vectors",
                        "vectorization_percent": "Percentage of vectorized chunks",
                        "needing_vectorization_sample": (
                            "Sample of chunks needing vectorization (up to 10). Each contains: "
                            "id (code_chunks.pk UUID string), file_id (files.pk UUID string), "
                            "chunk_preview, created_at"
                        ),
                    },
                    "recent_activity": {
                        "files_updated_24h": "Files updated in last 24 hours",
                        "chunks_updated_24h": "Chunks created in last 24 hours",
                    },
                    "error": "Error message if status check failed (optional)",
                },
                "example": {
                    "db_path": "/home/user/projects/my_project/data/code_analysis.db",
                    "timestamp": "2024-01-15T14:30:25",
                    "exists": True,
                    "file_size_mb": 125.5,
                    "projects": {
                        "total": 3,
                        "sample": [
                            {
                                "id": "123e4567-e89b-12d3-a456-426614174000",
                                "name": "project1",
                            },
                            {
                                "id": "223e4567-e89b-12d3-a456-426614174001",
                                "name": "project2",
                            },
                        ],
                    },
                    "files": {
                        "total": 1500,
                        "deleted": 50,
                        "active": 1450,
                        "with_docstring": 1200,
                        "indexed": 1400,
                        "indexed_percent": 96.55,
                        "needing_indexing": 50,
                        "needing_indexing_sample": [
                            {
                                "id": "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee",
                                "path": "src/new_file.py",
                                "has_docstring": False,
                                "last_modified": "2024-01-15T10:00:00",
                            }
                        ],
                        "needing_chunking": 25,
                        "needing_chunking_sample": [
                            {
                                "id": "bbbbbbbb-cccc-4ddd-eeee-ffffffffffff",
                                "path": "src/unchunked.py",
                                "has_docstring": True,
                                "last_modified": "2024-01-15T10:00:00",
                            }
                        ],
                    },
                    "chunks": {
                        "total": 5000,
                        "vectorized": 4800,
                        "not_vectorized": 200,
                        "vectorization_percent": 96.0,
                        "needing_vectorization_sample": [
                            {
                                "id": "cccccccc-dddd-4eee-ffff-000011112222",
                                "file_id": "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee",
                                "chunk_preview": "def new_function(): ...",
                                "created_at": "2024-01-15T10:00:00",
                            }
                        ],
                    },
                    "recent_activity": {
                        "files_updated_24h": 45,
                        "chunks_updated_24h": 120,
                    },
                },
                "example_not_found": {
                    "db_path": "/home/user/projects/my_project/data/code_analysis.db",
                    "timestamp": "2024-01-15T14:30:25",
                    "exists": False,
                    "file_size_mb": 0,
                    "error": "Database file not found",
                    "projects": {},
                    "files": {},
                    "chunks": {},
                    "recent_activity": {},
                },
            },
            "error": {
                "description": "Command failed",
                "code": "Error code (e.g., DATABASE_STATUS_ERROR)",
                "message": "Human-readable error message",
            },
        },
        "best_practices": [
            "Check exists field first to verify database exists",
            "Monitor file_size_mb to track database growth",
            "Check files.indexed and files.indexed_percent to track indexing progress",
            "Check files.needing_indexing and needing_indexing_sample for indexer backlog",
            "Check files.needing_chunking to identify chunking backlog",
            "Check chunks.not_vectorized to see vectorization backlog",
            "Use indexed_percent and vectorization_percent to track progress",
            "Review needing_indexing_sample and needing_vectorization_sample for specific items",
            "Monitor recent_activity to see database update frequency",
            "Use this command regularly to monitor database health",
            "Check projects.total to verify project registration",
        ],
    }
