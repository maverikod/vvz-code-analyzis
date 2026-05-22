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
            "convention and mirrors ownership in ``file_advisory_lock_leases``. Processing is "
            "per item: failures are returned inside ``results`` and do not roll back earlier "
            "successful items.\n\n"
            "Session ids may be client sessions (``session_create`` / ``client_sessions``) "
            "or daemon runtime sessions (``runtime_lock_sessions``). Client ids are "
            "registered into ``runtime_lock_sessions`` on demand and are not subject to "
            "``allow_foreign_session``. For daemon runtime ids, only the current process "
            "session is accepted unless ``allow_foreign_session`` is true. Unlock is "
            "idempotent: a missing lease is reported as success."
        ),
        "parameters": {
            "items": {
                "description": (
                    "Array of lock/unlock operations. Order is preserved in the result."
                ),
                "type": "array",
                "required": True,
                "items": {
                    "session_id": (
                        "Client session id (session_create) or runtime lock session id."
                    ),
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
                    "Allow a runtime_lock_sessions id owned by another process. "
                    "Does not restrict client_sessions ids. Default false."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "timeout_seconds": {
                "description": (
                    "Optional seconds to wait for flock on action=lock. Omitted means "
                    "block until available."
                ),
                "type": "number",
                "required": False,
            },
        },
        "return_value": {
            "success": {
                "description": (
                    "Batch processed. Check per-item ``ok`` flags; outer success does not "
                    "mean every item succeeded."
                ),
                "data": {
                    "results": (
                        "List of per-item results with index, action, session_id, "
                        "project_id, file_path, ok, and optional lock_mode, lock_path, "
                        "code, message, details."
                    ),
                    "total": "Number of input items.",
                    "succeeded": "Number of ok item results.",
                    "failed": "Number of failed item results.",
                    "current_session_id": (
                        "Runtime lock session id for this server process (daemon role)."
                    ),
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
                "description": (
                    "session_id is absent from client_sessions (when used as client id) "
                    "or from runtime_lock_sessions (when used as runtime id)."
                ),
                "message": (
                    "Client session not found: {session_id} or "
                    "Runtime lock session not found: {session_id}"
                ),
                "solution": (
                    "Use session_create for client workflows, the current runtime session "
                    "id, or set allow_foreign_session=true for foreign runtime ids."
                ),
            },
            "FOREIGN_SESSION_FORBIDDEN": {
                "description": (
                    "Non-client runtime session_id does not match the current process "
                    "and allow_foreign_session=false."
                ),
                "message": "Foreign runtime lock session is not allowed",
                "solution": "Use the current session id or set allow_foreign_session=true for diagnostics.",
            },
            "PROJECT_NOT_FOUND": {
                "description": "project_id is missing from the database.",
                "message": "Project {project_id} not found",
                "solution": "Call list_projects and retry with a valid project_id.",
            },
            "ITEM_ERROR": {
                "description": "Unexpected exception while processing one batch item.",
                "message": "Exception text in the item message field.",
                "solution": "Inspect server logs and retry the failing item.",
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
