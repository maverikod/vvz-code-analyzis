"""
Schema for project_file_advisory_lock_batch.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict


def get_project_file_advisory_lock_batch_schema() -> Dict[str, Any]:
    """Machine-readable schema for batch advisory lock operations."""
    return {
        "type": "object",
        "description": (
            "Acquire or release DB-visible runtime advisory file locks in a batch. "
            "Each ``file_path`` is relative to the registered watched project's ``root_path`` "
            "(``list_projects``), not the analysis server install. Each item is processed "
            "independently; item failures do not roll back successful items."
        ),
        "properties": {
            "items": {
                "type": "array",
                "description": (
                    "Lock/unlock operations. Each item needs session_id, project_id, "
                    "file_path, and action. lock_mode is used for action=lock."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": (
                                "Lock owner session id. Accepts a client_sessions id "
                                "(from session_create) or a runtime_lock_sessions id "
                                "for this daemon process. Non-client runtime ids must "
                                "match the current process session unless "
                                "allow_foreign_session=true."
                            ),
                        },
                        "project_id": {
                            "type": "string",
                            "description": "Project UUID.",
                        },
                        "file_path": {
                            "type": "string",
                            "description": (
                                "Path relative to the registered project's root_path "
                                "(list_projects, under a watch_dir), not the analysis server "
                                "install root."
                            ),
                        },
                        "action": {
                            "type": "string",
                            "enum": ["lock", "unlock"],
                            "description": "Acquire or release the lease.",
                        },
                        "lock_mode": {
                            "type": "string",
                            "enum": ["block_write", "full"],
                            "default": "full",
                            "description": (
                                "Mode for action=lock. block_write uses a shared flock; "
                                "full uses an exclusive flock."
                            ),
                        },
                    },
                    "required": ["session_id", "project_id", "file_path", "action"],
                    "additionalProperties": False,
                },
            },
            "allow_foreign_session": {
                "type": "boolean",
                "default": False,
                "description": (
                    "When false, only the current process runtime session may be used "
                    "for non-client session_id values. When true, any existing "
                    "runtime_lock_sessions row is accepted. Client session ids from "
                    "session_create are always allowed when present in client_sessions."
                ),
            },
            "timeout_seconds": {
                "type": "number",
                "minimum": 0,
                "description": (
                    "Optional flock acquisition timeout in seconds for action=lock. "
                    "When omitted, flock blocks until the lock is available. Applies "
                    "to the OS sidecar lock only (Unix); Windows flock is a no-op."
                ),
            },
        },
        "required": ["items"],
        "additionalProperties": False,
    }
