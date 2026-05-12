"""
Metadata for project_file_advisory_lock_batch.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_project_file_advisory_lock_batch_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Documentation-oriented metadata for batch advisory locks."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Batch helper for the runtime advisory lock service. Each item either acquires "
            "or releases a lease for one project file under the **registered watched project** "
            "(``list_projects`` → ``root_path`` in a configured watch_dir), not relative to the "
            "analysis server's own codebase. The command uses the shared ``file.lock`` sidecar "
            "convention and mirrors ownership in ``runtime_file_lock_leases``. Processing is "
            "per item: failures are returned inside ``results`` and do not roll back earlier "
            "successful items.\n\n"
            "For safety, arbitrary session ids are rejected by default. Use the current "
            "process ``runtime_lock_sessions.session_id`` unless ``allow_foreign_session`` "
            "is explicitly true for diagnostics. Unlock is idempotent: a missing lease is "
            "reported as success."
        ),
        "parameters": {
            "items": {
                "description": (
                    "Array of lock/unlock operations. Order is preserved in the result."
                ),
                "type": "array",
                "required": True,
                "items": {
                    "session_id": "Existing runtime lock session id.",
                    "project_id": "Project UUID.",
                    "file_path": (
                        "Path relative to that project's root_path (watched tree), not the server install."
                    ),
                    "action": "lock or unlock.",
                    "lock_mode": "block_write or full for action=lock; default full.",
                },
            },
            "allow_foreign_session": {
                "description": (
                    "Allow an existing session id owned by another process. Default false."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
        },
        "return_value": {
            "success": {
                "description": (
                    "Batch processed. Check per-item ``ok`` flags; outer success does not "
                    "mean every item succeeded."
                ),
                "data": {
                    "results": "List of per-item results with index, action, session_id, project_id, file_path, ok, and optional code/message/details.",
                    "total": "Number of input items.",
                    "succeeded": "Number of ok item results.",
                    "failed": "Number of failed item results.",
                },
                "example": {
                    "results": [
                        {
                            "index": 0,
                            "ok": True,
                            "action": "unlock",
                            "session_id": "11111111-1111-1111-1111-111111111111",
                            "project_id": "22222222-2222-2222-2222-222222222222",
                            "file_path": "src/app.py",
                        },
                        {
                            "index": 1,
                            "ok": False,
                            "action": "lock",
                            "code": "FILE_NOT_FOUND",
                            "message": "Indexed file not found: missing.py",
                        },
                    ],
                    "total": 2,
                    "succeeded": 1,
                    "failed": 1,
                },
            },
            "error": {
                "description": "Top-level validation failure before batch execution.",
                "code": "VALIDATION_ERROR",
                "message": "Invalid items array or unexpected parameter.",
                "details": "Field-level diagnostic information.",
            },
        },
        "usage_examples": [
            {
                "description": "Lock then unlock one indexed file",
                "command": {
                    "items": [
                        {
                            "session_id": "11111111-1111-1111-1111-111111111111",
                            "project_id": "22222222-2222-2222-2222-222222222222",
                            "file_path": "src/app.py",
                            "action": "lock",
                            "lock_mode": "full",
                        },
                        {
                            "session_id": "11111111-1111-1111-1111-111111111111",
                            "project_id": "22222222-2222-2222-2222-222222222222",
                            "file_path": "src/app.py",
                            "action": "unlock",
                        },
                    ]
                },
                "explanation": "Both items are attempted; the second unlock is idempotent.",
            }
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": {
                "description": "session_id has no runtime_lock_sessions row.",
                "message": "Runtime lock session not found: {session_id}",
                "solution": "Register/use the current runtime session or enable it through the daemon.",
            },
            "FOREIGN_SESSION_FORBIDDEN": {
                "description": "session_id does not match the current process and allow_foreign_session=false.",
                "message": "Foreign runtime lock session is not allowed",
                "solution": "Use the current session id or set allow_foreign_session=true for diagnostics.",
            },
            "FILE_NOT_FOUND": {
                "description": "Lock item target has no non-deleted files row.",
                "message": "Indexed file not found: {file_path}",
                "solution": "Refresh indexes or use an indexed file path.",
            },
            "PATH_ERROR": {
                "description": "Path escapes the registered project's root_path or is not a regular file.",
                "message": "Resolver validation message.",
                "solution": (
                    "Pass a path relative to list_projects.root_path (watched project), not the server root."
                ),
            },
        },
        "best_practices": [
            "Use paths from the watched project's root (list_projects), not from the analysis repo.",
            "Inspect each result entry; the outer SuccessResult only means the batch ran.",
            "Use unlock freely in cleanup paths; missing leases are treated as successful unlocks.",
            "Keep allow_foreign_session=false unless debugging lock cleanup across processes.",
            "Use block_write for read-like transfers and full for writes or exclusive maintenance.",
        ],
    }
