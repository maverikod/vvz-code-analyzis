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
                                "Runtime lock session id from runtime_lock_sessions. "
                                "By default it must match this server process session."
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
                    "When false, only the current process runtime session may be used. "
                    "When true, any existing runtime_lock_sessions row is accepted."
                ),
            },
        },
        "required": ["items"],
        "additionalProperties": False,
    }
