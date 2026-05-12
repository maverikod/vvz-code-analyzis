"""
Metadata for project_file_lock_status.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_project_file_lock_status_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Extended documentation for MCP / help."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Reports advisory lock leases for the given ``project_id`` and ``file_path``. "
            "Paths are **only** relative to the **registered watched project** root "
            "(`root_path` from ``list_projects`` — the project directory under a configured "
            "**watch_dir**). They are **not** relative to the code-analysis server's own "
            "repository or config directory. Same convention as ``project_file_advisory_lock_batch``. "
            "The response ``file_path`` is the canonical POSIX path under that ``root_path``.\n\n"
            "**lock_status values**\n\n"
            "- ``free`` — no leases (RU: свободен).\n"
            "- ``fully_locked`` — at least one exclusive lease (RU: полностью заблокирован).\n"
            "- ``write_locked`` — only shared leases, no exclusive (RU: заблокирован для записи; "
            "shared / block_write mode).\n\n"
            "OS-level ``flock`` on ``.lock`` sidecars is not probed here; if a process "
            "locks without writing a lease, this command may still report ``free``."
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID.",
                "type": "string",
                "required": True,
                "examples": ["550e8400-e29b-41d4-a716-446655440000"],
            },
            "file_path": {
                "description": (
                    "Path relative to the project's ``root_path`` (watched tree), not absolute "
                    "on the host and not relative to the analysis server install. "
                    "Normalized to POSIX in the response."
                ),
                "type": "string",
                "required": True,
                "examples": ["src/module.py", "tests/test_foo.py"],
            },
        },
        "return_value": {
            "success": {
                "description": "Query succeeded.",
                "data": {
                    "success": "True.",
                    "project_id": "Project UUID.",
                    "file_path": "Canonical path relative to the project's root_path (POSIX), used for lease lookup.",
                    "lock_status": "free | write_locked | fully_locked",
                    "leases": (
                        "Breakdown: exclusive_total_refcount, shared_total_refcount, "
                        "exclusive_sessions, shared_sessions (session_id + refcount per row)."
                    ),
                },
                "example": {
                    "success": True,
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "file_path": "app/main.py",
                    "lock_status": "free",
                    "leases": {
                        "exclusive_total_refcount": 0,
                        "shared_total_refcount": 0,
                        "exclusive_sessions": [],
                        "shared_sessions": [],
                    },
                },
            },
            "error": {
                "description": "Validation or resolution failure.",
                "code": "PROJECT_NOT_FOUND | FILE_NOT_FOUND | VALIDATION_ERROR",
                "message": "Human-readable message.",
            },
        },
        "usage_examples": [
            {
                "description": "Check lock before editing",
                "command": {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "file_path": "src/service.py",
                },
                "explanation": "Returns lock_status and per-session lease refcount details.",
            },
        ],
        "error_cases": {
            "PROJECT_NOT_FOUND": {
                "description": "project_id is missing from the database.",
                "message": "Project with ID ... not found",
                "solution": "Call list_projects and retry with a valid UUID.",
            },
            "FILE_NOT_FOUND": {
                "description": "Path missing, escapes root, or not a file.",
                "solution": "Use list_project_files to confirm the relative path.",
            },
        },
        "best_practices": [
            "Resolve paths from list_projects.root_path (watched project), not from the server codebase.",
            "Use the same path convention as project_file_advisory_lock_batch.",
            "Treat write_locked as 'no exclusive holder but shared readers'; defer writes.",
            "After acquiring locks in tests, release them to avoid stale lease rows.",
        ],
    }
